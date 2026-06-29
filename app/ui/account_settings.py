from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBitmap, QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.domain.models import NotificationMode, User
from app.infrastructure.repositories import UserRepository
from app.ui.style import get_palette
from app.ui.ui_utils import StyledComboBox

# 头像存储根目录：app/resources/uploads/
_AVATAR_ROOT = Path(__file__).resolve().parent.parent / "resources" / "uploads"
_AVATAR_DIR = _AVATAR_ROOT / "avatars"
# 允许的图片扩展名与最大字节数（与 api_server 保持一致）
_ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MAX_BYTES = 2 * 1024 * 1024  # 2MB


def make_circular_pixmap(src: QPixmap, size: int) -> QPixmap:
    """将原始图片裁剪为指定尺寸的圆形头像。"""
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    # 等比缩放并居中裁剪到正方形
    scaled = src.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = (scaled.width() - size) // 2
    y = (scaled.height() - size) // 2
    cropped = scaled.copy(x, y, size, size)
    # 创建圆形 mask 用于裁剪
    mask = QBitmap(size, size)
    mask.fill(Qt.color0)
    painter = QPainter(mask)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(Qt.color1)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    cropped.setMask(mask)
    return cropped


def make_initial_pixmap(letter: str, size: int, bg_color: str, fg_color: str) -> QPixmap:
    """生成首字母占位头像：圆形背景 + 居中字母。"""
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    # 绘制圆形背景
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(bg_color))
    painter.drawEllipse(0, 0, size, size)
    # 绘制首字母
    painter.setPen(QColor(fg_color))
    font = QFont()
    font.setPointSize(int(size * 0.4))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(out.rect(), Qt.AlignCenter, (letter or "?")[:1].upper())
    painter.end()
    # 应用圆形 mask 裁剪
    mask = QBitmap(size, size)
    mask.fill(Qt.color0)
    m = QPainter(mask)
    m.setRenderHint(QPainter.Antialiasing)
    m.setBrush(Qt.color1)
    m.drawEllipse(0, 0, size, size)
    m.end()
    out.setMask(mask)
    return out


class AccountSettingsDialog(QDialog):
    """账号设置对话框：头像上传 + 通知偏好。

    构造函数签名：AccountSettingsDialog(user: User, user_repo: UserRepository, parent=None)
    不修改调用方构造函数，由外部注入 user 与 user_repo。
    """

    def __init__(self, user: User, user_repo: UserRepository, parent=None) -> None:
        super().__init__(parent)
        self._user = user
        self._user_repo = user_repo
        self.setWindowTitle("账号设置")
        self.setMinimumWidth(440)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        # === 头像区 ===
        avatar_group = QGroupBox("头像")
        avatar_layout = QHBoxLayout()
        avatar_layout.setSpacing(16)
        avatar_layout.setContentsMargins(16, 16, 16, 16)

        # 头像预览 QLabel（圆形裁剪，无头像时显示用户名首字母）
        self._avatar_label = QLabel()
        self._avatar_label.setFixedSize(72, 72)
        self._refresh_avatar()
        avatar_layout.addWidget(self._avatar_label)

        # 用户名与格式提示
        info_col = QVBoxLayout()
        info_col.setSpacing(6)
        info_col.addWidget(QLabel(f"用户名：{self._user.username}"))
        hint = QLabel("支持 PNG/JPG/JPEG/GIF/WEBP，最大 2MB")
        p = get_palette()
        hint.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px;")
        info_col.addWidget(hint)
        info_col.addStretch()
        avatar_layout.addLayout(info_col, 1)

        # 选择图片按钮
        select_btn = QPushButton("选择图片...")
        select_btn.setObjectName("secondaryButton")
        select_btn.setCursor(Qt.PointingHandCursor)
        select_btn.clicked.connect(self._on_select_avatar)
        avatar_layout.addWidget(select_btn)

        avatar_group.setLayout(avatar_layout)
        layout.addWidget(avatar_group)

        # === 通知偏好区 ===
        notif_group = QGroupBox("通知偏好")
        notif_form = QFormLayout()
        notif_form.setContentsMargins(16, 16, 16, 16)
        notif_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._notif_combo = StyledComboBox()
        self._notif_combo.addItem("应用内通知", NotificationMode.IN_APP.value)
        self._notif_combo.addItem("邮件", NotificationMode.EMAIL.value)
        self._notif_combo.addItem("不提醒", NotificationMode.NONE.value)
        # 从数据库读取当前通知偏好（User 对象可能未携带 DB 中的实际值）
        current_value = self._fetch_current_notification_mode()
        for i in range(self._notif_combo.count()):
            if self._notif_combo.itemData(i) == current_value:
                self._notif_combo.setCurrentIndex(i)
                break
        self._notif_combo.currentIndexChanged.connect(self._on_notif_changed)
        notif_form.addRow("提醒方式", self._notif_combo)
        notif_group.setLayout(notif_form)
        layout.addWidget(notif_group)

        layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)

    def _fetch_current_notification_mode(self) -> str:
        """从数据库读取当前用户的通知偏好（返回字符串值）。"""
        try:
            record = self._user_repo.get_by_id(self._user.id)
            if record:
                return str(record.get("notification_mode", NotificationMode.IN_APP.value))
        except Exception:
            pass
        # 兜底：使用 User 对象上的值
        mode = self._user.notification_mode
        return mode.value if hasattr(mode, "value") else str(mode)

    def _refresh_avatar(self) -> None:
        """根据当前用户头像路径刷新头像预览。"""
        try:
            record = self._user_repo.get_by_id(self._user.id)
            avatar_path = record.get("avatar_path", "") if record else ""
        except Exception:
            avatar_path = ""
        if avatar_path:
            # 本地模式头像存相对路径，显示时拼接 app/resources/uploads/ 前缀
            full = _AVATAR_ROOT / avatar_path
            pix = QPixmap(str(full))
            if not pix.isNull():
                self._avatar_label.setPixmap(make_circular_pixmap(pix, 72))
                return
        # 无头像或加载失败：用用户名首字母做圆形占位
        p = get_palette()
        initial = self._user.username[:1] if self._user.username else "?"
        self._avatar_label.setPixmap(make_initial_pixmap(initial, 72, p.accent, p.text_on_accent))

    def _on_select_avatar(self) -> None:
        """通过 QFileDialog 选择图片并上传为头像。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择头像图片", "", "图片文件 (*.png *.jpg *.jpeg *.gif *.webp)"
        )
        if not path:
            return
        src = Path(path)
        ext = src.suffix.lower()
        if ext not in _ALLOWED_EXTS:
            QMessageBox.warning(self, "格式不支持", f"不支持的图片格式，仅支持 {', '.join(sorted(_ALLOWED_EXTS))}")
            return
        if src.stat().st_size > _MAX_BYTES:
            QMessageBox.warning(self, "文件过大", f"头像大小不能超过 {_MAX_BYTES // 1024}KB")
            return
        # 复制到 app/resources/uploads/avatars/{user_id}.{ext}
        _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        dest = _AVATAR_DIR / f"{self._user.id}{ext}"
        # 关键修复（P1-6）：原代码先删旧文件再拷贝，若拷贝失败用户将失去头像。
        # 改为先拷贝到临时文件，成功后再清理旧文件并原子重命名。
        tmp_dest = _AVATAR_DIR / f"{self._user.id}.tmp{ext}"
        try:
            shutil.copyfile(str(src), str(tmp_dest))
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", f"复制头像失败：{exc}")
            return
        # 拷贝成功后清理同 user_id 的旧文件（可能扩展名不同，排除刚写入的临时文件）
        for old in _AVATAR_DIR.glob(f"{self._user.id}.*"):
            if old == tmp_dest:
                continue
            try:
                old.unlink()
            except OSError:
                pass
        # 原子重命名临时文件为最终文件
        try:
            tmp_dest.replace(dest)
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", f"重命名头像失败：{exc}")
            return
        # 存相对路径 "avatars/{user_id}.{ext}"，便于本地/远程统一
        rel_path = f"avatars/{self._user.id}{ext}"
        try:
            self._user_repo.update_avatar(self._user.id, rel_path)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", f"更新头像失败：{exc}")
            return
        self._refresh_avatar()

    def _on_notif_changed(self, _index: int) -> None:
        """通知偏好变化时立即写入数据库。"""
        mode = self._notif_combo.currentData()
        try:
            self._user_repo.update_notification_mode(self._user.id, mode)
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", f"通知偏好保存失败：{exc}")
