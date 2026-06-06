from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.group_service import GroupService
from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import MemberStatus, User
from app.infrastructure.repositories import GroupRepository
from app.ui.style import get_palette
from app.ui.ui_utils import configure_table, make_page_header, set_table_empty


def _p():
    return get_palette()


class GroupClientPanel(QWidget):
    def __init__(self, group_service: GroupService, group_repo: GroupRepository, user: User) -> None:
        super().__init__()
        self._service = group_service
        self._repo = group_repo
        self._user = user
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        p = _p()
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = make_page_header("小组", "浏览和加入小组，获取活动报名资格")
        layout.addWidget(header)

        # ── 我的小组 ──────────────────────────────────────
        my_group = QGroupBox("我的小组")
        my_layout = QVBoxLayout()
        my_layout.setContentsMargins(12, 12, 12, 12)
        self._my_table = QTableWidget(0, 4)
        self._my_table.setHorizontalHeaderLabels(["名称", "描述", "状态", "操作"])
        configure_table(self._my_table)
        my_layout.addWidget(self._my_table)
        my_group.setLayout(my_layout)
        layout.addWidget(my_group)

        # ── 所有小组 ──────────────────────────────────────
        all_group = QGroupBox("浏览小组")
        all_layout = QVBoxLayout()
        all_layout.setContentsMargins(12, 12, 12, 12)

        self._all_table = QTableWidget(0, 5)
        self._all_table.setHorizontalHeaderLabels(["ID", "名称", "描述", "创建者", "操作"])
        configure_table(self._all_table)
        self._all_table.setColumnHidden(0, True)
        all_layout.addWidget(self._all_table)
        all_group.setLayout(all_layout)
        layout.addWidget(all_group)

        self.setLayout(layout)

    def refresh(self) -> None:
        self._load_my_groups()
        self._load_all_groups()

    def _load_my_groups(self) -> None:
        my_apps = self._service.get_user_pending_applications(self._user.id)
        self._my_table.clearSpans()
        if not my_apps:
            set_table_empty(self._my_table, 4, "暂未加入任何小组，请在下方的可浏览小组中选择申请")
            return
        self._my_table.setRowCount(len(my_apps))
        for i, item in enumerate(my_apps):
            g = item["group"]
            m = item["member"]
            self._my_table.setItem(i, 0, QTableWidgetItem(g["name"]))
            self._my_table.setItem(i, 1, QTableWidgetItem(g.get("description", "")))
            status_map = {"pending": "待审批", "approved": "已通过", "rejected": "已拒绝"}
            self._my_table.setItem(i, 2, QTableWidgetItem(status_map.get(m["status"], m["status"])))
            if m["status"] == "approved":
                leave_btn = QPushButton("退出")
                leave_btn.setObjectName("dangerButton")
                leave_btn.clicked.connect(lambda checked, gid=g["id"]: self._leave_group(gid))
                self._my_table.setCellWidget(i, 3, leave_btn)
            else:
                self._my_table.setItem(i, 3, QTableWidgetItem("-"))

    def _load_all_groups(self) -> None:
        groups = self._service.list_all_groups()
        my_apps = {item["group"]["id"]: item["member"] for item in self._service.get_user_pending_applications(self._user.id)}
        self._all_table.clearSpans()
        if not groups:
            set_table_empty(self._all_table, 5, "暂无小组")
            return
        self._all_table.setRowCount(len(groups))
        for i, g in enumerate(groups):
            self._all_table.setItem(i, 0, QTableWidgetItem(g["id"]))
            self._all_table.setItem(i, 1, QTableWidgetItem(g["name"]))
            self._all_table.setItem(i, 2, QTableWidgetItem(g.get("description", "")))
            self._all_table.setItem(i, 3, QTableWidgetItem(g.get("owner_id", "")[:8] + "..."))

            existing = my_apps.get(g["id"])
            if existing:
                status_text = {
                    "approved": "已加入",
                    "pending": "审核中",
                    "rejected": "已拒绝（可重新申请）",
                }.get(existing["status"], existing["status"])
                self._all_table.setItem(i, 4, QTableWidgetItem(status_text))
            else:
                join_btn = QPushButton("申请加入")
                join_btn.setObjectName("primaryButton")
                join_btn.clicked.connect(lambda checked, gid=g["id"]: self._join_group(gid))
                self._all_table.setCellWidget(i, 4, join_btn)

    def _join_group(self, group_id: str) -> None:
        try:
            self._service.join_group(self._user.id, group_id)
            QMessageBox.information(self, "申请成功", "已提交加入申请，请等待小组管理员审批")
            self.refresh()
        except ValidationError as exc:
            QMessageBox.warning(self, "提示", str(exc))

    def _leave_group(self, group_id: str) -> None:
        reply = QMessageBox.question(self, "确认退出", "确定要退出此小组吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            self._repo.remove_member(group_id, self._user.id)
            QMessageBox.information(self, "成功", "已退出小组")
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "错误", str(exc))
