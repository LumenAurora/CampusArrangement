from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.activity_service import ActivityService
from app.application.checkin_service import CheckInService
from app.domain.exceptions import ConflictError, PermissionDenied, ValidationError
from app.domain.models import User
from app.infrastructure.repositories import ScheduleRepository, UserRepository
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, set_banner, set_table_empty, format_status


class CheckInPanel(QWidget):
    def __init__(self, checkin_service: CheckInService, activity_service: ActivityService, schedule_repo: ScheduleRepository, user_repo: UserRepository, user: User) -> None:
        super().__init__()
        self._checkin_service = checkin_service
        self._activity_service = activity_service
        self._schedule_repo = schedule_repo
        self._user_repo = user_repo
        self._user = user

        self._activity_selector = QComboBox()
        self._activity_selector.setMinimumWidth(220)
        self._message = QLabel("")
        set_banner(self._message, "info", "")

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["用户名", "时段", "签到状态", "user_id", "slot_id"])
        configure_table(self._table)

        checkin_btn = QPushButton("签到")
        checkin_btn.setObjectName("primaryButton")
        checkin_btn.clicked.connect(self._check_in)

        absent_btn = QPushButton("标记缺勤")
        absent_btn.setObjectName("dangerButton")
        absent_btn.clicked.connect(self._mark_absent)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self._load_results)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addWidget(checkin_btn)
        btn_layout.addWidget(absent_btn)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()

        selector_layout = QHBoxLayout()
        selector_layout.setSpacing(12)
        selector_layout.addWidget(QLabel("活动"))
        selector_layout.addWidget(self._activity_selector)
        selector_layout.addStretch()

        group = QGroupBox("签到管理")
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(12, 12, 12, 12)
        group_layout.addLayout(selector_layout)
        group_layout.addWidget(self._table)
        group_layout.addLayout(btn_layout)
        group_layout.addWidget(self._message)
        group.setLayout(group_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(make_page_header("签到", "管理活动签到与缺勤标记"))
        layout.addWidget(group)
        self.setLayout(layout)

        self._activity_selector.currentIndexChanged.connect(self._load_results)
        self.refresh()

    def refresh(self) -> None:
        activities = self._activity_service.list_activities()
        self._activity_selector.clear()
        if not activities:
            set_table_empty(self._table, 5, "暂无活动")
            return
        for activity in activities:
            status_text = format_status(activity.get("status", "draft"))
            self._activity_selector.addItem(f"{activity['name']} ({status_text})", activity["id"])
        self._load_results()

    def _load_results(self) -> None:
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            set_table_empty(self._table, 5, "请选择活动")
            return
        rows = self._schedule_repo.list_by_activity(activity_id)
        if not rows:
            set_table_empty(self._table, 5, "暂无排班结果")
            return
        slot_map: dict[str, str] = {}
        for slot in self._activity_service.list_slots(activity_id):
            slot_map[slot["id"]] = f"{format_datetime(slot['start_time'])} - {format_datetime(slot['end_time'])}"
        checkins = self._checkin_service.list_by_activity(activity_id)
        checkin_map: dict[str, str] = {}
        for ci in checkins:
            checkin_map[ci["user_id"] + ":" + ci["slot_id"]] = ci["status"]
        user_cache: dict[str, str] = {}
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            uid = row["user_id"]
            if uid not in user_cache:
                u = self._user_repo.get_by_id(uid)
                user_cache[uid] = u["username"] if u else uid
            self._table.setItem(row_index, 0, QTableWidgetItem(user_cache[uid]))
            slot_label = slot_map.get(row["slot_id"], row["slot_id"])
            self._table.setItem(row_index, 1, QTableWidgetItem(slot_label))
            status_raw = checkin_map.get(uid + ":" + row["slot_id"], "")
            if status_raw == "checked_in":
                status_text = "已签到"
            elif status_raw == "absent":
                status_text = "缺勤"
            else:
                status_text = "未签到"
            self._table.setItem(row_index, 2, QTableWidgetItem(status_text))
            self._table.setItem(row_index, 3, QTableWidgetItem(uid))
            self._table.setItem(row_index, 4, QTableWidgetItem(row["slot_id"]))
        self._table.setColumnHidden(3, True)
        self._table.setColumnHidden(4, True)

    def _check_in(self) -> None:
        try:
            set_banner(self._message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                set_banner(self._message, "error", "请先选择活动")
                return
            current_row = self._table.currentRow()
            if current_row < 0:
                set_banner(self._message, "error", "请选择一行进行签到")
                return
            user_id_item = self._table.item(current_row, 3)
            slot_id_item = self._table.item(current_row, 4)
            if not user_id_item or not slot_id_item:
                set_banner(self._message, "error", "数据异常")
                return
            self._checkin_service.check_in(
                user=self._user,
                activity_id=activity_id,
                user_id=user_id_item.text(),
                slot_id=slot_id_item.text(),
            )
            set_banner(self._message, "success", "签到成功")
            self._load_results()
        except (ConflictError, PermissionDenied, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))

    def _mark_absent(self) -> None:
        try:
            set_banner(self._message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                set_banner(self._message, "error", "请先选择活动")
                return
            current_row = self._table.currentRow()
            if current_row < 0:
                set_banner(self._message, "error", "请选择一行进行标记")
                return
            user_id_item = self._table.item(current_row, 3)
            slot_id_item = self._table.item(current_row, 4)
            if not user_id_item or not slot_id_item:
                set_banner(self._message, "error", "数据异常")
                return
            checkins = self._checkin_service.list_by_activity(activity_id)
            target_checkin_id = None
            for ci in checkins:
                if ci["user_id"] == user_id_item.text() and ci["slot_id"] == slot_id_item.text():
                    target_checkin_id = ci["id"]
                    break
            if not target_checkin_id:
                set_banner(self._message, "error", "该用户尚未签到，无法标记缺勤")
                return
            self._checkin_service.mark_absent(user=self._user, checkin_id=target_checkin_id)
            set_banner(self._message, "success", "已标记缺勤")
            self._load_results()
        except (ConflictError, PermissionDenied, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))
