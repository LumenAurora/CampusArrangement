from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from app.application.user_service import UserService
from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import Role, User
from app.infrastructure.repositories import UserRepository
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, set_banner, set_table_empty


class UserAdminPanel(QWidget):
    def __init__(self, user_service: UserService, user_repo: UserRepository, current_user: User) -> None:
        super().__init__()
        self._user_service = user_service
        self._user_repo = user_repo
        self._current_user = current_user

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["ID", "用户名", "角色", "创建时间"])
        configure_table(self._table)

        self._init_create_form()

        list_group = QGroupBox("用户列表")
        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(12, 12, 12, 12)
        list_layout.addWidget(self._table)

        # 删除按钮
        delete_btn_layout = QHBoxLayout()
        delete_btn_layout.addStretch(1)
        self._delete_btn = QPushButton("删除选中用户")
        self._delete_btn.setObjectName("dangerButton")
        self._delete_btn.clicked.connect(self._delete_user)
        delete_btn_layout.addWidget(self._delete_btn)
        list_layout.addLayout(delete_btn_layout)

        list_group.setLayout(list_layout)

        header = make_page_header("用户管理", "创建账号并查看用户列表")

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(16)
        body_layout.addWidget(self._create_group, 1)
        body_layout.addWidget(list_group, 2)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addLayout(body_layout)
        self.setLayout(layout)

        self.refresh()

    def _init_create_form(self) -> None:
        self._username = QLineEdit()
        self._username.setPlaceholderText("用户名")
        self._password = QLineEdit()
        self._password.setPlaceholderText("初始密码")
        self._password.setEchoMode(QLineEdit.Password)
        self._role = QComboBox()
        self._role.addItem("组织者", Role.ORGANIZER)
        self._role.addItem("普通用户", Role.USER)
        self._message = QLabel("")
        set_banner(self._message, "info", "")

        create_btn = QPushButton("创建用户")
        create_btn.setObjectName("primaryButton")
        create_btn.clicked.connect(self._create_user)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow("用户名", self._username)
        form.addRow("密码", self._password)
        form.addRow("角色", self._role)
        form.addRow(create_btn)
        form.addRow(self._message)

        self._create_group = QGroupBox("创建用户")
        self._create_group.setLayout(form)

        if self._current_user.role != Role.SUPER_ADMIN:
            self._create_group.setEnabled(False)
            set_banner(self._message, "info", "仅超级管理员可创建用户")

    def refresh(self) -> None:
        users = self._user_repo.list_all()
        if not users:
            set_table_empty(self._table, 4, "暂无用户")
            return
        role_map = {
            Role.SUPER_ADMIN.value: "超级管理员",
            Role.ORGANIZER.value: "组织者",
            Role.USER.value: "普通用户",
        }
        self._table.setRowCount(len(users))
        for row_index, user in enumerate(users):
            self._table.setItem(row_index, 0, QTableWidgetItem(str(user.get("id", ""))))
            self._table.setItem(row_index, 1, QTableWidgetItem(user["username"]))
            role_text = role_map.get(user["role"], user["role"])
            role_item = QTableWidgetItem(role_text)
            role_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row_index, 2, role_item)
            self._table.setItem(row_index, 3, QTableWidgetItem(format_datetime(user["created_at"])))
        self._table.setColumnHidden(0, True)

    def _create_user(self) -> None:
        if self._current_user.role != Role.SUPER_ADMIN:
            set_banner(self._message, "error", "无权限创建用户")
            return
        try:
            set_banner(self._message, "info", "")
            user = self._user_service.register(
                username=self._username.text().strip(),
                password=self._password.text(),
                role=Role(self._role.currentData()),
            )
            set_banner(self._message, "success", f"已创建用户：{user.username}")
            self.refresh()
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))

    def _delete_user(self) -> None:
        if self._current_user.role != Role.SUPER_ADMIN:
            set_banner(self._message, "error", "无权限删除用户")
            return

        # 获取当前选中的行
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要删除的用户")
            return

        row = selected_rows[0].row()
        user_id_item = self._table.item(row, 0)
        username_item = self._table.item(row, 1)
        if not user_id_item or not username_item:
            QMessageBox.warning(self, "提示", "数据异常")
            return

        user_id = user_id_item.text()
        username = username_item.text()

        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除用户「{username}」吗？\n删除后无法恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                self._user_service.delete_user(current_user=self._current_user, user_id=user_id)
                set_banner(self._message, "success", f"已删除用户：{username}")
                self.refresh()
            except (PermissionDenied, ValidationError) as exc:
                set_banner(self._message, "error", str(exc))
