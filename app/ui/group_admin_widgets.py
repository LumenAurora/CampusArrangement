from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QTextEdit,
)

from app.application.group_service import GroupService
from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import MemberStatus, User
from app.infrastructure.repositories import GroupRepository
from app.ui.style import get_palette
from app.ui.ui_utils import (
    StyledComboBox,
    configure_table,
    make_page_header,
    set_banner,
    set_table_empty,
)


def _p():
    return get_palette()


class GroupAdminPanel(QWidget):
    def __init__(self, group_service: GroupService, group_repo: GroupRepository, user: User) -> None:
        super().__init__()
        self._service = group_service
        self._repo = group_repo
        self._user = user
        self._selected_group_id: str | None = None
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        p = _p()
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = make_page_header("小组管理", "创建、管理小组，审核成员申请")
        layout.addWidget(header)

        # ── 创建小组 ──────────────────────────────────────
        create_group = QGroupBox("创建小组")
        create_layout = QVBoxLayout()
        create_layout.setContentsMargins(12, 12, 12, 12)
        create_layout.setSpacing(8)

        form = QFormLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("小组名称")
        self._desc_input = QTextEdit()
        self._desc_input.setPlaceholderText("小组描述（可选）")
        self._desc_input.setMaximumHeight(60)
        form.addRow("名称", self._name_input)
        form.addRow("描述", self._desc_input)
        create_layout.addLayout(form)

        btn_row = QHBoxLayout()
        self._create_btn = QPushButton("创建小组")
        self._create_btn.setObjectName("primaryButton")
        self._create_btn.clicked.connect(self._create_group)
        self._delete_btn = QPushButton("删除选中小组")
        self._delete_btn.setObjectName("dangerButton")
        self._delete_btn.clicked.connect(self._delete_group)
        self._delete_btn.setEnabled(False)
        btn_row.addWidget(self._create_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch(1)
        create_layout.addLayout(btn_row)

        self._create_msg = QLabel("")
        set_banner(self._create_msg, "info", "")
        create_layout.addWidget(self._create_msg)
        create_group.setLayout(create_layout)
        layout.addWidget(create_group)

        # ── 小组列表 ──────────────────────────────────────
        self._group_table = QTableWidget(0, 4)
        self._group_table.setHorizontalHeaderLabels(["ID", "名称", "描述", "创建者"])
        configure_table(self._group_table)
        self._group_table.setColumnHidden(0, True)
        self._group_table.itemSelectionChanged.connect(self._on_group_selected)
        layout.addWidget(self._group_table)

        # ── 成员管理 ──────────────────────────────────────
        member_group = QGroupBox("成员管理")
        member_layout = QVBoxLayout()
        member_layout.setContentsMargins(12, 12, 12, 12)

        self._member_table = QTableWidget(0, 5)
        self._member_table.setHorizontalHeaderLabels(["用户名", "角色", "状态", "加入时间", "操作"])
        configure_table(self._member_table)

        self._member_label = QLabel("请先选择一个小组")
        self._member_label.setStyleSheet(f"color: {p.text_tertiary};")
        member_layout.addWidget(self._member_label)
        member_layout.addWidget(self._member_table)

        # 待审批申请
        pending_group = QGroupBox("待审批申请")
        pending_layout = QVBoxLayout()
        self._pending_table = QTableWidget(0, 5)
        self._pending_table.setHorizontalHeaderLabels(["小组", "用户名", "角色", "申请时间", "操作"])
        configure_table(self._pending_table)
        pending_layout.addWidget(self._pending_table)
        pending_group.setLayout(pending_layout)

        member_layout.addWidget(pending_group)
        member_group.setLayout(member_layout)
        layout.addWidget(member_group)

        self.setLayout(layout)

    def refresh(self) -> None:
        self._load_groups()
        self._load_pending()
        if self._selected_group_id:
            self._load_members(self._selected_group_id)

    def _load_groups(self) -> None:
        groups = self._service.list_all_groups()
        self._group_table.clearSpans()
        if not groups:
            set_table_empty(self._group_table, 4, "暂无小组")
            return
        self._group_table.setRowCount(len(groups))
        for i, g in enumerate(groups):
            self._group_table.setItem(i, 0, QTableWidgetItem(g["id"]))
            self._group_table.setItem(i, 1, QTableWidgetItem(g["name"]))
            self._group_table.setItem(i, 2, QTableWidgetItem(g.get("description", "")))
            owner = g.get("owner_id", "")
            self._group_table.setItem(i, 3, QTableWidgetItem(owner[:8] + "..."))

    def _load_members(self, group_id: str) -> None:
        members = self._repo.list_members(group_id)
        self._member_table.clearSpans()
        if not members:
            set_table_empty(self._member_table, 5, "暂无成员")
            return
        self._member_table.setRowCount(len(members))
        for i, m in enumerate(members):
            self._member_table.setItem(i, 0, QTableWidgetItem(m.get("username", "-")))
            self._member_table.setItem(i, 1, QTableWidgetItem(m.get("role", "member")))
            status_map = {"pending": "待审批", "approved": "已通过", "rejected": "已拒绝"}
            self._member_table.setItem(i, 2, QTableWidgetItem(status_map.get(m.get("status", ""), m.get("status", ""))))
            self._member_table.setItem(i, 3, QTableWidgetItem(m.get("joined_at", "")[:16]))
            if m.get("status") == "pending":
                approve_btn = QPushButton("通过")
                approve_btn.setObjectName("primaryButton")
                approve_btn.clicked.connect(lambda checked, uid=m["user_id"]: self._approve_member(uid))
                self._member_table.setCellWidget(i, 4, approve_btn)
            elif m.get("user_id") != self._selected_group_owner_id:
                remove_btn = QPushButton("移除")
                remove_btn.setObjectName("dangerButton")
                remove_btn.clicked.connect(lambda checked, uid=m["user_id"]: self._remove_member(uid))
                self._member_table.setCellWidget(i, 4, remove_btn)
            else:
                self._member_table.setItem(i, 4, QTableWidgetItem("创建者"))

    def _load_pending(self) -> None:
        pending = self._service.list_pending_applications(self._user)
        self._pending_table.clearSpans()
        if not pending:
            set_table_empty(self._pending_table, 5, "暂无待审批申请")
            return
        self._pending_table.setRowCount(len(pending))
        for i, app in enumerate(pending):
            self._pending_table.setItem(i, 0, QTableWidgetItem(app.get("group_name", "-")))
            self._pending_table.setItem(i, 1, QTableWidgetItem(app.get("username", "-")))
            self._pending_table.setItem(i, 2, QTableWidgetItem(app.get("role", "member")))
            self._pending_table.setItem(i, 3, QTableWidgetItem(app.get("joined_at", "")[:16]))
            btn_widget = QWidget()
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(0, 0, 0, 0)
            approve_btn = QPushButton("通过")
            approve_btn.setObjectName("primaryButton")
            approve_btn.clicked.connect(lambda checked, gid=app["group_id"], uid=app["user_id"]: self._approve_pending(gid, uid))
            reject_btn = QPushButton("拒绝")
            reject_btn.setObjectName("dangerButton")
            reject_btn.clicked.connect(lambda checked, gid=app["group_id"], uid=app["user_id"]: self._reject_pending(gid, uid))
            btn_layout.addWidget(approve_btn)
            btn_layout.addWidget(reject_btn)
            btn_widget.setLayout(btn_layout)
            self._pending_table.setCellWidget(i, 4, btn_widget)

    def _create_group(self) -> None:
        try:
            set_banner(self._create_msg, "info", "")
            name = self._name_input.text().strip()
            desc = self._desc_input.toPlainText().strip()
            self._service.create_group(self._user, name, desc)
            set_banner(self._create_msg, "success", f"小组 '{name}' 创建成功")
            self._name_input.clear()
            self._desc_input.clear()
            self.refresh()
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._create_msg, "error", str(exc))

    def _delete_group(self) -> None:
        if not self._selected_group_id:
            return
        reply = QMessageBox.question(self, "确认删除", "确定要删除此小组吗？所有成员将被移除。",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            self._service.delete_group(self._user, self._selected_group_id)
            self._selected_group_id = None
            self._selected_group_owner_id = None
            self._delete_btn.setEnabled(False)
            self._member_label.setText("请先选择一个小组")
            set_table_empty(self._member_table, 5, "")
            self.refresh()
        except (PermissionDenied, ValidationError) as exc:
            QMessageBox.warning(self, "错误", str(exc))

    def _on_group_selected(self) -> None:
        rows = self._group_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        group_id = self._group_table.item(row, 0).text()
        group = self._repo.get(group_id)
        if group:
            self._selected_group_id = group_id
            self._selected_group_owner_id = group.get("owner_id", "")
            self._delete_btn.setEnabled(True)
            self._member_label.setText(f"小组：{group['name']}")
            self._load_members(group_id)

    def _approve_member(self, member_user_id: str) -> None:
        try:
            self._service.approve_member(self._user, self._selected_group_id, member_user_id)
            self._load_members(self._selected_group_id)
            self._load_pending()
        except (PermissionDenied, ValidationError) as exc:
            QMessageBox.warning(self, "错误", str(exc))

    def _remove_member(self, member_user_id: str) -> None:
        try:
            self._service.remove_member(self._user, self._selected_group_id, member_user_id)
            self._load_members(self._selected_group_id)
        except (PermissionDenied, ValidationError) as exc:
            QMessageBox.warning(self, "错误", str(exc))

    def _approve_pending(self, group_id: str, user_id: str) -> None:
        try:
            self._service.approve_member(self._user, group_id, user_id)
            self._load_pending()
            if self._selected_group_id == group_id:
                self._load_members(group_id)
        except (PermissionDenied, ValidationError) as exc:
            QMessageBox.warning(self, "错误", str(exc))

    def _reject_pending(self, group_id: str, user_id: str) -> None:
        try:
            self._service.reject_member(self._user, group_id, user_id)
            self._load_pending()
        except (PermissionDenied, ValidationError) as exc:
            QMessageBox.warning(self, "错误", str(exc))
