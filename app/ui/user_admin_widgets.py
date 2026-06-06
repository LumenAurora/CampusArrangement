from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
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
from app.domain.models import Role, User, UserStatus
from app.infrastructure.repositories import (
    RegistrationRepository,
    ScheduleRepository,
    UserRepository,
)
from app.ui.style import get_palette
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, set_banner, set_table_empty


# ─── 辅助函数：创建带颜色的角色/状态表格项 ──────────────────────────

def _make_role_item(role_value: str) -> QTableWidgetItem:
    """创建角色徽章表格项，使用调色板着色。"""
    p = get_palette()
    role_map = {
        Role.SUPER_ADMIN.value: ("超级管理员", p.accent, p.accent_soft),
        Role.ORGANIZER.value: ("组织者", p.warning_fg, p.warning_bg),
        Role.USER.value: ("普通用户", p.text_secondary, p.bg_sidebar),
    }
    text, fg, bg = role_map.get(role_value, (role_value, p.text_secondary, p.bg_sidebar))
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignCenter)
    item.setForeground(QBrush(QColor(fg)))
    item.setBackground(QBrush(QColor(bg)))
    return item


def _make_user_status_item(status_value: str) -> QTableWidgetItem:
    """创建用户状态徽章表格项，使用调色板着色。"""
    p = get_palette()
    status_map = {
        UserStatus.APPROVED.value: ("已通过", p.success_fg, p.success_bg),
        UserStatus.PENDING_REVIEW.value: ("待审批", p.accent, p.accent_soft),
        UserStatus.REJECTED.value: ("已拒绝", p.error_fg, p.error_bg),
    }
    text, fg, bg = status_map.get(status_value, (status_value, p.text_secondary, p.bg_sidebar))
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignCenter)
    item.setForeground(QBrush(QColor(fg)))
    item.setBackground(QBrush(QColor(bg)))
    return item


# ─── 统计卡片 ──────────────────────────────────────────────────────

class _StatCard(QFrame):
    def __init__(self, label: str, value: int, accent_color: str) -> None:
        super().__init__()
        self.setObjectName("statCard")
        self.setFixedHeight(100)

        p = get_palette()
        self.setStyleSheet(f"""
            QFrame#statCard {{
                background: {p.bg_card};
                border: 1px solid {p.border_light};
                border-left: 4px solid {accent_color};
                border-radius: 16px;
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        name_label = QLabel(label)
        name_label.setObjectName("statLabel")
        layout.addWidget(name_label)

        value_label = QLabel(str(value))
        value_label.setObjectName("statValue")
        layout.addWidget(value_label)

        layout.addStretch(1)
        self.setLayout(layout)


# ─── 用户管理面板 ──────────────────────────────────────────────────

class UserAdminPanel(QWidget):
    def __init__(self, user_service: UserService, user_repo: UserRepository, current_user: User) -> None:
        super().__init__()
        self._user_service = user_service
        self._user_repo = user_repo
        self._current_user = current_user
        self._reg_repo = RegistrationRepository()
        self._schedule_repo = ScheduleRepository()

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["ID", "用户名", "角色"])
        configure_table(self._table)
        self._table.cellDoubleClicked.connect(self._show_user_detail)

        self._init_create_form()
        self._init_pending_section()

        # ── 统计卡片区域 ───────────────────────────────────────
        self._stats_grid = QGridLayout()
        self._stats_grid.setSpacing(12)
        self._stats_grid.setContentsMargins(0, 0, 0, 0)

        # ── 用户列表 ───────────────────────────────────────────
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

        # 左侧：创建用户 + 待审批
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        left_layout.addWidget(self._create_group)
        if self._current_user.role != Role.USER:
            left_layout.addWidget(self._pending_group)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(16)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        left_widget.setFixedWidth(320)
        body_layout.addWidget(left_widget)
        body_layout.addWidget(list_group, 2)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addLayout(self._stats_grid)
        layout.addLayout(body_layout)
        self.setLayout(layout)

        self.refresh()

    # ── 创建用户表单 ───────────────────────────────────────────

    def _init_create_form(self) -> None:
        self._username = QLineEdit()
        self._username.setPlaceholderText("用户名")
        self._password = QLineEdit()
        self._password.setPlaceholderText("初始密码")
        self._password.setEchoMode(QLineEdit.Password)
        self._role = QComboBox()

        # 根据角色显示可选角色
        if self._current_user.role == Role.SUPER_ADMIN:
            self._role.addItem("超级管理员", Role.SUPER_ADMIN)
            self._role.addItem("组织者", Role.ORGANIZER)
            self._role.addItem("普通用户", Role.USER)
        elif self._current_user.role == Role.ORGANIZER:
            self._role.addItem("普通用户", Role.USER)
            self._role.setCurrentIndex(0)
            self._role.setEnabled(False)  # 组织者只能创建普通用户，固定选项

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

        # 普通用户不能创建用户
        if self._current_user.role == Role.USER:
            self._create_group.setEnabled(False)
            set_banner(self._message, "info", "普通用户无权创建用户")

    # ── 待审批用户区域 ─────────────────────────────────────────

    def _init_pending_section(self) -> None:
        """初始化待审批用户区域"""
        self._pending_table = QTableWidget(0, 4)
        self._pending_table.setHorizontalHeaderLabels(["ID", "用户名", "状态", "创建时间"])
        configure_table(self._pending_table)
        self._pending_table.setMaximumHeight(200)

        btn_layout = QHBoxLayout()
        self._approve_btn = QPushButton("通过")
        self._approve_btn.setObjectName("primaryButton")
        self._approve_btn.clicked.connect(self._approve_user)
        self._reject_btn = QPushButton("拒绝")
        self._reject_btn.setObjectName("dangerButton")
        self._reject_btn.clicked.connect(self._reject_user)
        btn_layout.addWidget(self._approve_btn)
        btn_layout.addWidget(self._reject_btn)

        self._pending_message = QLabel("")
        set_banner(self._pending_message, "info", "")

        pending_layout = QVBoxLayout()
        pending_layout.setContentsMargins(12, 12, 12, 12)
        pending_layout.addWidget(self._pending_table)
        pending_layout.addLayout(btn_layout)
        pending_layout.addWidget(self._pending_message)

        self._pending_group = QGroupBox("待审批用户")
        self._pending_group.setLayout(pending_layout)

    # ── 刷新统计卡片 ───────────────────────────────────────────

    def _refresh_stats(self, users: list[dict]) -> None:
        """刷新用户统计卡片。"""
        p = get_palette()
        total = len(users)
        super_admin_count = sum(1 for u in users if u.get("role") == Role.SUPER_ADMIN.value)
        organizer_count = sum(1 for u in users if u.get("role") == Role.ORGANIZER.value)
        user_count = sum(1 for u in users if u.get("role") == Role.USER.value)

        # 清除旧卡片
        while self._stats_grid.count():
            item = self._stats_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cards = [
            ("用户总数", total, p.accent),
            ("超级管理员", super_admin_count, p.accent),
            ("组织者", organizer_count, p.warning_fg),
            ("普通用户", user_count, p.text_secondary),
        ]
        for index, (label, value, color) in enumerate(cards):
            card = _StatCard(label, value, color)
            self._stats_grid.addWidget(card, 0, index)

    # ── 刷新待审批用户列表 ─────────────────────────────────────

    def _refresh_pending(self) -> None:
        """刷新待审批用户列表"""
        if self._current_user.role == Role.USER:
            return
        try:
            pending_users = self._user_service.list_pending_users(self._current_user)
        except Exception:
            pending_users = []
        if not pending_users:
            set_table_empty(self._pending_table, 4, "暂无待审批用户")
            return
        self._pending_table.setRowCount(len(pending_users))
        for row_index, user in enumerate(pending_users):
            self._pending_table.setItem(row_index, 0, QTableWidgetItem(str(user.get("id", ""))))
            self._pending_table.setItem(row_index, 1, QTableWidgetItem(user.get("username", "")))
            # 状态指示器
            self._pending_table.setItem(row_index, 2, _make_user_status_item(user.get("status", UserStatus.PENDING_REVIEW.value)))
            self._pending_table.setItem(row_index, 3, QTableWidgetItem(format_datetime(user.get("created_at", ""))))
        self._pending_table.setColumnHidden(0, True)

    # ── 主刷新 ─────────────────────────────────────────────────

    def refresh(self) -> None:
        users = self._user_repo.list_all()

        # 刷新统计卡片
        self._refresh_stats(users)

        if not users:
            set_table_empty(self._table, 3, "暂无用户")
        else:
            self._table.setRowCount(len(users))
            for row_index, user in enumerate(users):
                self._table.setItem(row_index, 0, QTableWidgetItem(str(user.get("id", ""))))
                self._table.setItem(row_index, 1, QTableWidgetItem(user["username"]))
                # 角色徽章
                self._table.setItem(row_index, 2, _make_role_item(user["role"]))
            self._table.setColumnHidden(0, True)
        self._refresh_pending()

    # ── 用户详情弹窗 ───────────────────────────────────────────

    def _show_user_detail(self, row: int, _col: int) -> None:
        """双击用户行时弹出详细信息对话框。"""
        user_id_item = self._table.item(row, 0)
        if not user_id_item:
            return
        user_id = user_id_item.text()
        user = self._user_repo.get_by_id(user_id)
        if not user:
            return

        p = get_palette()
        dialog = QDialog(self)
        dialog.setWindowTitle(f"用户详情 - {user.get('username', '')}")
        dialog.setMinimumWidth(380)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 标题
        title = QLabel(user.get("username", ""))
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {p.text_primary};")
        layout.addWidget(title)

        # 详细信息表单
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # 角色
        role_value = user.get("role", "")
        role_map = {
            Role.SUPER_ADMIN.value: "超级管理员",
            Role.ORGANIZER.value: "组织者",
            Role.USER.value: "普通用户",
        }
        role_label = QLabel(role_map.get(role_value, role_value))
        role_label.setStyleSheet(f"color: {p.accent}; font-weight: 600;")
        form.addRow("角色", role_label)

        # 状态
        status_value = user.get("status", "")
        status_map = {
            UserStatus.APPROVED.value: ("已通过", p.success_fg),
            UserStatus.PENDING_REVIEW.value: ("待审批", p.accent),
            UserStatus.REJECTED.value: ("已拒绝", p.error_fg),
        }
        status_text, status_color = status_map.get(status_value, (status_value, p.text_secondary))
        status_label = QLabel(status_text)
        status_label.setStyleSheet(f"color: {status_color}; font-weight: 600;")
        form.addRow("状态", status_label)

        # 创建时间
        created_at = user.get("created_at", "")
        form.addRow("创建时间", QLabel(format_datetime(created_at) if created_at else "未知"))

        # 关联数据
        reg_count = self._reg_repo.count_by_user(user_id)
        schedule_count = self._schedule_repo.count_by_user(user_id)
        form.addRow("报名记录", QLabel(f"{reg_count} 条"))
        form.addRow("排班结果", QLabel(f"{schedule_count} 条"))

        layout.addLayout(form)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {p.border_light};")
        layout.addWidget(sep)

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryButton")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec()

    # ── 创建用户 ───────────────────────────────────────────────

    def _create_user(self) -> None:
        if self._current_user.role == Role.USER:
            set_banner(self._message, "error", "普通用户无权创建用户")
            return
        try:
            set_banner(self._message, "info", "")
            user = self._user_service.register(
                current_user=self._current_user,
                username=self._username.text().strip(),
                password=self._password.text(),
                role=Role(self._role.currentData()),
            )
            set_banner(self._message, "success", f"已创建用户：{user.username}")
            self.refresh()
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))

    # ── 审批用户 ───────────────────────────────────────────────

    def _approve_user(self) -> None:
        selected_rows = self._pending_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要审批的用户")
            return
        row = selected_rows[0].row()
        user_id_item = self._pending_table.item(row, 0)
        username_item = self._pending_table.item(row, 1)
        if not user_id_item:
            return
        user_id = user_id_item.text()
        username = username_item.text() if username_item else ""
        try:
            self._user_service.approve_user(self._current_user, user_id)
            set_banner(self._pending_message, "success", f"已通过用户：{username}")
            self.refresh()
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._pending_message, "error", str(exc))

    def _reject_user(self) -> None:
        selected_rows = self._pending_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要拒绝的用户")
            return
        row = selected_rows[0].row()
        user_id_item = self._pending_table.item(row, 0)
        username_item = self._pending_table.item(row, 1)
        if not user_id_item:
            return
        user_id = user_id_item.text()
        username = username_item.text() if username_item else ""
        try:
            self._user_service.reject_user(self._current_user, user_id)
            set_banner(self._pending_message, "success", f"已拒绝用户：{username}")
            self.refresh()
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._pending_message, "error", str(exc))

    # ── 删除用户（含详细信息确认） ─────────────────────────────

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

        # 查询关联数据
        reg_count = self._reg_repo.count_by_user(user_id)
        schedule_count = self._schedule_repo.count_by_user(user_id)

        # 构建详细确认信息
        detail_lines = [f"确定要删除用户「{username}」吗？"]
        if reg_count > 0 or schedule_count > 0:
            detail_lines.append("")
            detail_lines.append("该用户存在以下关联数据：")
            if reg_count > 0:
                detail_lines.append(f"  · 报名记录：{reg_count} 条")
            if schedule_count > 0:
                detail_lines.append(f"  · 排班结果：{schedule_count} 条")
            detail_lines.append("")
            detail_lines.append("删除后关联数据将一并清除，且无法恢复。")
        else:
            detail_lines.append("删除后无法恢复。")

        reply = QMessageBox.question(
            self,
            "确认删除",
            "\n".join(detail_lines),
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
