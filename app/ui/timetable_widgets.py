from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.application.activity_service import ActivityService
from app.application.checkin_service import CheckInService
from app.domain.models import User
from app.infrastructure.repositories import ScheduleRepository
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, set_table_empty


class TimetablePanel(QWidget):
    def __init__(self, schedule_repo: ScheduleRepository, checkin_service: CheckInService, activity_service: ActivityService, user: User) -> None:
        super().__init__()
        self._schedule_repo = schedule_repo
        self._checkin_service = checkin_service
        self._activity_service = activity_service
        self._user = user

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(["活动名称", "选项类型", "选项名称", "开始时间", "结束时间", "地点", "签到状态"])
        configure_table(self._table)

        group = QGroupBox("我的课表/日程")
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
        layout.addWidget(make_page_header("课表", "查看我的排班时间表"))
        layout.addWidget(group)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        activities = {activity["id"]: activity for activity in self._activity_service.list_activities()}
        rows = self._schedule_repo.list_by_user(self._user.id)
        if not rows:
            set_table_empty(self._table, 7, "暂无排班/日程结果")
            return
        slot_map: dict[str, dict] = {}
        activity_ids = {row["activity_id"] for row in rows}
        for activity_id in activity_ids:
            for slot in self._activity_service.list_slots(activity_id):
                slot_map[slot["id"]] = slot
        checkins = self._checkin_service.list_by_user(self._user.id)
        checkin_map: dict[str, str] = {}
        for ci in checkins:
            checkin_map[ci["slot_id"]] = ci["status"]
        sorted_rows = sorted(rows, key=lambda r: (r["activity_id"], slot_map.get(r["slot_id"], {}).get("start_time", "")))
        self._table.setRowCount(len(sorted_rows))
        for row_index, row in enumerate(sorted_rows):
            activity = activities.get(row["activity_id"])
            activity_name = activity["name"] if activity else "未知活动"
            self._table.setItem(row_index, 0, QTableWidgetItem(activity_name))
            slot = slot_map.get(row["slot_id"])
            if slot:
                # 显示选项类型
                slot_type = slot.get("slot_type", "time_slot")
                type_text = {
                    "time_slot": "时段",
                    "topic": "选题",
                    "course": "课程",
                    "custom_option": "自定义"
                }.get(slot_type, "其他")
                self._table.setItem(row_index, 1, QTableWidgetItem(type_text))
                
                # 显示选项名称
                slot_name = slot.get("name", "")
                self._table.setItem(row_index, 2, QTableWidgetItem(slot_name))
                
                # 显示时间
                start_time = format_datetime(slot["start_time"]) if slot.get("start_time") else "-"
                self._table.setItem(row_index, 3, QTableWidgetItem(start_time))
                end_time = format_datetime(slot["end_time"]) if slot.get("end_time") else "-"
                self._table.setItem(row_index, 4, QTableWidgetItem(end_time))
                
                # 显示地点
                location = activity.get("location", "") if activity else ""
                self._table.setItem(row_index, 5, QTableWidgetItem(location))
            else:
                self._table.setItem(row_index, 1, QTableWidgetItem(""))
                self._table.setItem(row_index, 2, QTableWidgetItem(""))
                self._table.setItem(row_index, 3, QTableWidgetItem(""))
                self._table.setItem(row_index, 4, QTableWidgetItem(""))
                self._table.setItem(row_index, 5, QTableWidgetItem(""))
                
            status_raw = checkin_map.get(row["slot_id"], "")
            if status_raw == "checked_in":
                status_text = "已签到"
            elif status_raw == "absent":
                status_text = "缺勤"
            else:
                status_text = "未签到"
            self._table.setItem(row_index, 6, QTableWidgetItem(status_text))
