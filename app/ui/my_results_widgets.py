from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.application.activity_service import ActivityService
from app.domain.models import User
from app.infrastructure.repositories import ScheduleRepository
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, set_table_empty


class MyResultsPanel(QWidget):
    def __init__(self, schedule_repo: ScheduleRepository, activity_service: ActivityService, user: User) -> None:
        super().__init__()
        self._schedule_repo = schedule_repo
        self._activity_service = activity_service
        self._user = user

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["活动", "时段", "生成时间", "活动ID"])
        configure_table(self._table)

        group = QGroupBox("排班结果列表")
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(12, 12, 12, 12)

        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self.refresh)
        btn_layout.addStretch(1)
        btn_layout.addWidget(refresh_btn)
        group_layout.addLayout(btn_layout)

        group_layout.addWidget(self._table)
        group.setLayout(group_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(make_page_header("我的结果", "查看我的排班与分配记录"))
        layout.addWidget(group)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        activities = {activity["id"]: activity["name"] for activity in self._activity_service.list_activities()}
        rows = self._schedule_repo.list_by_user(self._user.id)
        if not rows:
            set_table_empty(self._table, 4, "暂无排班结果")
            return
        activity_ids = {row["activity_id"] for row in rows}
        slot_map: dict[str, str] = {}
        for activity_id in activity_ids:
            for slot in self._activity_service.list_slots(activity_id):
                slot_map[slot["id"]] = f"{format_datetime(slot['start_time'])} - {format_datetime(slot['end_time'])}"
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            activity_name = activities.get(row["activity_id"], "未知活动")
            self._table.setItem(row_index, 0, QTableWidgetItem(activity_name))
            slot_label = slot_map.get(row["slot_id"], row["slot_id"])
            self._table.setItem(row_index, 1, QTableWidgetItem(slot_label))
            self._table.setItem(row_index, 2, QTableWidgetItem(format_datetime(row["created_at"])))
            self._table.setItem(row_index, 3, QTableWidgetItem(row["activity_id"]))
        self._table.setColumnHidden(3, True)
