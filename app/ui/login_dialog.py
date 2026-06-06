from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.application.user_service import UserService
from app.domain.exceptions import DomainError
from app.ui.style import get_palette
from app.ui.ui_utils import set_banner


class LoginDialog(QDialog):
    def __init__(self, user_service: UserService) -> None:
        super().__init__()
        self._user_service = user_service
        self.user = None

        self.setWindowTitle("Campus Scheduler")
        self.setFixedSize(420, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        p = get_palette()

        # 主卡片
        card = QFrame()
        card.setObjectName("loginCard")
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(40, 48, 40, 36)
        card_layout.setSpacing(0)

        # Logo 区域 — 纯文字
        title = QLabel("Campus Scheduler")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"font-size: 22px; font-weight: 700; letter-spacing: -0.5px;"
            f"color: {p.text_primary}; margin-bottom: 4px;"
        )
        card_layout.addWidget(title)

        subtitle = QLabel("校园报名与排班系统")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            f"font-size: 13px; color: {p.text_tertiary}; margin-bottom: 36px;"
        )
        card_layout.addWidget(subtitle)

        # 用户名
        user_label = QLabel("用户名")
        user_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {p.text_secondary}; margin-bottom: 6px;"
        )
        card_layout.addWidget(user_label)

        self._username = QLineEdit()
        self._username.setPlaceholderText("输入用户名")
        self._username.setFixedHeight(42)
        card_layout.addWidget(self._username)

        card_layout.addSpacing(16)

        # 密码
        pwd_label = QLabel("密码")
        pwd_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {p.text_secondary}; margin-bottom: 6px;"
        )
        card_layout.addWidget(pwd_label)

        self._password = QLineEdit()
        self._password.setPlaceholderText("输入密码")
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setFixedHeight(42)
        self._password.returnPressed.connect(self._handle_login)
        card_layout.addWidget(self._password)

        card_layout.addSpacing(8)

        # 消息
        self._message = QLabel("")
        self._message.setObjectName("bannerInfo")
        self._message.setWordWrap(True)
        card_layout.addWidget(self._message)

        card_layout.addSpacing(20)

        # 登录按钮
        login_btn = QPushButton("登 录")
        login_btn.setObjectName("primaryButton")
        login_btn.setFixedHeight(44)
        login_btn.setCursor(Qt.PointingHandCursor)
        login_btn.clicked.connect(self._handle_login)
        card_layout.addWidget(login_btn)

        card_layout.addSpacing(8)

        # 注册按钮
        register_btn = QPushButton("注册账号")
        register_btn.setObjectName("secondaryButton")
        register_btn.setFixedHeight(36)
        register_btn.setCursor(Qt.PointingHandCursor)
        register_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {p.accent};"
            f" border: 1px solid {p.accent}; border-radius: 6px; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {p.accent_soft}; }}"
        )
        register_btn.clicked.connect(self._handle_register)
        card_layout.addWidget(register_btn)

        card_layout.addStretch(1)

        # 底部提示
        hint = QLabel("默认管理员：admin / admin")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(
            f"font-size: 11px; color: {p.text_tertiary}; margin-top: 16px;"
        )
        card_layout.addWidget(hint)

        card.setLayout(card_layout)

        # 外层布局
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card, 0, Qt.AlignCenter)
        self.setLayout(outer)

        # 回车登录
        self._username.returnPressed.connect(lambda: self._password.setFocus())

    def _handle_login(self) -> None:
        try:
            user = self._user_service.authenticate(
                self._username.text().strip(),
                self._password.text(),
            )
        except DomainError as exc:
            set_banner(self._message, "error", str(exc))
            return
        self.user = user
        self.accept()

    def _handle_register(self) -> None:
        username = self._username.text().strip()
        password = self._password.text()
        if not username:
            set_banner(self._message, "error", "请输入用户名")
            return
        if not password or len(password) < 4:
            set_banner(self._message, "error", "密码长度不能少于4位")
            return
        try:
            self._user_service.self_register(username, password)
            set_banner(self._message, "success", "注册成功，请等待管理员审批后登录")
        except DomainError as exc:
            set_banner(self._message, "error", str(exc))
