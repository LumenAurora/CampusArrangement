from __future__ import annotations

import logging
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from PySide6.QtCore import QObject, QSettings, Signal

from app.domain.models import Notification as NotificationModel
from app.infrastructure.repositories import NotificationRepository

_logger = logging.getLogger(__name__)

_SETTINGS_ORG = "CampusScheduler"
_SETTINGS_APP = "CampusScheduler"


def _settings() -> QSettings:
    return QSettings(_SETTINGS_ORG, _SETTINGS_APP)


# ── SMTP 配置持久化 ────────────────────────────────────────────

def get_smtp_config() -> dict:
    """从 QSettings 读取 SMTP 配置（仅限主线程调用）。"""
    s = _settings()
    raw_use_tls = str(s.value("email/use_tls", True)).lower()
    try:
        port = int(s.value("email/port", 587))
    except (ValueError, TypeError):
        port = 587
    return {
        "host": s.value("email/host", ""),
        "port": port,
        "username": s.value("email/username", ""),
        "password": s.value("email/password", ""),
        "use_tls": raw_use_tls in ("true", "1", "yes"),
    }


def set_smtp_config(host: str, port: int, username: str, password: str, use_tls: bool = True) -> None:
    """持久化 SMTP 配置到 QSettings。"""
    s = _settings()
    s.setValue("email/host", host)
    s.setValue("email/port", port)
    s.setValue("email/username", username)
    s.setValue("email/password", password)
    s.setValue("email/use_tls", use_tls)
    s.sync()


# ── 邮件发送 ──────────────────────────────────────────────────

def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    host: str | None = None,
    port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    use_tls: bool | None = None,
    html: bool = False,
) -> tuple[bool, str]:
    """发送邮件（线程安全 — 不访问 QSettings）。

    所有 SMTP 参数必须显式传入，本函数不从 QSettings 读取。
    """
    if not host or not username or not password:
        return False, "邮件服务器未配置，请在设置中填写 SMTP 信息"

    tls = use_tls if use_tls is not None else True

    try:
        msg = MIMEMultipart()
        msg["From"] = username
        msg["To"] = to
        msg["Subject"] = subject
        subtype = "html" if html else "plain"
        msg.attach(MIMEText(body, subtype, "utf-8"))

        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            if tls:
                server.starttls()
                server.ehlo()
            server.login(username, password)
            server.send_message(msg)

        return True, "邮件已发送"
    except smtplib.SMTPAuthenticationError:
        return False, "邮箱认证失败，请检查用户名和密码"
    except smtplib.SMTPConnectError:
        return False, f"无法连接到邮件服务器 {host}:{port}"
    except smtplib.SMTPException as exc:
        return False, f"邮件发送失败：{exc}"
    except OSError as exc:
        return False, f"网络错误：{exc}"


# ── 异步发送 ──────────────────────────────────────────────────

class _EmailSignals(QObject):
    """邮件发送结果信号 — 用于跨线程回调到主线程。"""
    done = Signal(bool, str)


def send_email_async(
    to: str,
    subject: str,
    body: str,
    *,
    html: bool = False,
    on_done: callable | None = None,
) -> None:
    """异步发送邮件（不阻塞 UI 线程）。

    在启动工作线程前从 QSettings 读取 SMTP 配置（主线程安全），
    使用 Qt Signal 将结果安全地回调到主线程。
    """
    # 在主线程中读取配置（QSettings 不是线程安全的）
    cfg = get_smtp_config()
    host = cfg["host"]
    port = cfg["port"]
    username = cfg["username"]
    password = cfg["password"]
    use_tls = cfg["use_tls"]

    signals = _EmailSignals()

    if on_done:
        signals.done.connect(on_done)

    def _worker() -> None:
        try:
            ok, msg = send_email(
                to, subject, body,
                host=host, port=port, username=username, password=password,
                use_tls=use_tls, html=html,
            )
        except Exception as exc:
            ok, msg = False, f"邮件发送异常：{exc}"
            _logger.exception("邮件发送异常: %s", exc)

        _logger.info("邮件发送%s: %s → %s: %s", "成功" if ok else "失败", subject, to, msg)

        # 通过 Signal 回调主线程（Qt 自动处理跨线程调度）
        signals.done.emit(ok, msg)

    threading.Thread(target=_worker, daemon=True).start()


# ── 统一通知入口 ──────────────────────────────────────────────

def notify(message: str) -> None:
    """本地通知占位符。后续可接入系统托盘、桌面通知等。"""
    _logger.info("通知: %s", message)
    print(message)


def notify_by_preference(
    user_id: str,
    user_email: str,
    user_notification_mode: str,
    subject: str,
    body: str,
    sender_id: str = "",
    related_link: str = "",
) -> None:
    """根据用户通知偏好发送通知并持久化应用内通知。

    当偏好为 in_app 或 email 时，始终持久化一条应用内通知记录。
    偏好为 email 时额外发送邮件。偏好为 none 时完全跳过。
    """
    mode = (user_notification_mode or "").lower().strip()
    if mode == "none":
        return

    # 始终持久化应用内通知（除非偏好为 none）
    notify_user(user_id, subject, body, sender_id, related_link)

    if mode == "email":
        if not user_email:
            _logger.warning("用户 %s 未设置邮箱，无法发送邮件通知", user_id)
            return
        send_email_async(user_email, subject, body)
    elif mode == "in_app":
        _logger.info("应用内通知: [%s] %s -> %s", subject, body[:50], user_id)
    elif mode not in ("", "none"):
        _logger.warning("未知通知模式: %s，跳过通知", user_notification_mode)


def notify_user(
    user_id: str,
    subject: str,
    body: str = "",
    sender_id: str = "",
    related_link: str = "",
) -> NotificationModel | None:
    """创建并持久化一条应用内通知。返回 Notification 对象，失败时返回 None。

    这是所有应用内通知的单一入口：管理员群发、系统自动触发（报名成功/排班结果等）。
    """
    notification = NotificationModel.create(
        user_id=user_id,
        subject=subject,
        body=body,
        sender_id=sender_id,
        related_link=related_link,
    )
    try:
        repo = NotificationRepository()
        repo.create(notification)
        _logger.info("通知已保存: [%s] %s -> %s", subject, body[:50], user_id)
        return notification
    except Exception as exc:
        _logger.exception("通知保存失败: %s", exc)
        return None
