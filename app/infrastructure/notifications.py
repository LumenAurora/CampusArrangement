from __future__ import annotations

import logging
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from PySide6.QtCore import QSettings

_logger = logging.getLogger(__name__)

_SETTINGS_ORG = "CampusScheduler"
_SETTINGS_APP = "CampusScheduler"


def _settings() -> QSettings:
    return QSettings(_SETTINGS_ORG, _SETTINGS_APP)


# ── SMTP 配置持久化 ────────────────────────────────────────────

def get_smtp_config() -> dict:
    """从 QSettings 读取 SMTP 配置。"""
    s = _settings()
    return {
        "host": s.value("email/host", ""),
        "port": int(s.value("email/port", 587)),
        "username": s.value("email/username", ""),
        "password": s.value("email/password", ""),
        "use_tls": s.value("email/use_tls", True) in (True, "true", "1"),
    }


def set_smtp_config(host: str, port: int, username: str, password: str, use_tls: bool = True) -> None:
    """持久化 SMTP 配置到 QSettings。"""
    s = _settings()
    s.setValue("email/host", host)
    s.setValue("email/port", port)
    s.setValue("email/username", username)
    s.setValue("email/password", password)  # 注意：明文存储，生产环境建议加密
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
    """发送邮件。返回 (成功, 消息)。

    如未提供 SMTP 参数，从 QSettings 读取已保存的配置。
    """
    cfg = get_smtp_config()
    host = host or cfg["host"]
    port = port or cfg["port"]
    username = username or cfg["username"]
    password = password or cfg["password"]
    use_tls = use_tls if use_tls is not None else cfg["use_tls"]

    if not host or not username or not password:
        return False, "邮件服务器未配置，请在设置中填写 SMTP 信息"

    try:
        msg = MIMEMultipart()
        msg["From"] = username
        msg["To"] = to
        msg["Subject"] = subject
        subtype = "html" if html else "plain"
        msg.attach(MIMEText(body, subtype, "utf-8"))

        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            if use_tls:
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


def send_email_async(
    to: str,
    subject: str,
    body: str,
    *,
    html: bool = False,
    on_done: callable | None = None,
) -> None:
    """异步发送邮件（不阻塞 UI 线程）。on_done(success, message) 在主线程回调。"""

    def _worker() -> None:
        ok, msg = send_email(to, subject, body, html=html)
        _logger.info("邮件发送%s: %s → %s: %s", "成功" if ok else "失败", subject, to, msg)
        if on_done:
            # 结果回主线程
            from PySide6.QtCore import QTimer

            def _callback() -> None:
                on_done(ok, msg)

            QTimer.singleShot(0, _callback)

    threading.Thread(target=_worker, daemon=True).start()


# ── 统一通知入口 ──────────────────────────────────────────────

def notify(message: str) -> None:
    """本地通知占位符。后续可接入系统托盘、桌面通知等。"""
    _logger.info("通知: %s", message)
    print(message)


def notify_by_preference(user_email: str, user_notification_mode: str, subject: str, body: str) -> None:
    """根据用户通知偏好发送通知。

    user_notification_mode: "in_app" | "email" | "none"
    """
    if user_notification_mode == "email":
        if not user_email:
            _logger.warning("用户未设置邮箱，无法发送邮件通知")
            return
        send_email_async(user_email, subject, body)
    elif user_notification_mode == "in_app":
        notify(f"[{subject}] {body}")
    # "none" 不发送任何通知
