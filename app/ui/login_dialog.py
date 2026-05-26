from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from app.application.user_service import UserService
from app.domain.exceptions import ValidationError
from app.ui.ui_utils import make_page_header, set_banner


class LoginDialog(QDialog):
    def __init__(self, user_service: UserService) -> None:
        super().__init__()
        self._user_service = user_service
        self.user = None

        self.setWindowTitle("登录")
        self.setMinimumWidth(360)
        self._username = QLineEdit()
        self._username.setPlaceholderText("输入用户名")
        self._password = QLineEdit()
        self._password.setPlaceholderText("输入密码")
        self._password.setEchoMode(QLineEdit.Password)
        self._message = QLabel("")
        set_banner(self._message, "info", "")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow("用户名", self._username)
        form.addRow("密码", self._password)

        buttons = QHBoxLayout()
        login_btn = QPushButton("登录")
        login_btn.clicked.connect(self._handle_login)
        buttons.addStretch(1)
        buttons.addWidget(login_btn)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(make_page_header("欢迎回来", "登录以继续"))
        layout.addLayout(form)
        layout.addWidget(self._message)
        layout.addLayout(buttons)
        self.setLayout(layout)

    def _handle_login(self) -> None:
        try:
            user = self._user_service.authenticate(self._username.text().strip(), self._password.text())
        except ValidationError as exc:
            set_banner(self._message, "error", str(exc))
            return
        self.user = user
        self.accept()
