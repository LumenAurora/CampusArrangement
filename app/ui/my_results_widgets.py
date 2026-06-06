from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from app.application.activity_service import ActivityService
from app.domain.models import User
from app.infrastructure.repositories import ScheduleRepository
from app.ui.style import get_palette
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, set_table_empty


class ResultDetailDialog(QDialog):
    """排班/分配结果详情对话框。"""

    def __init__(self, result: dict, activity: dict | None, slot: dict | None, parent=None) -> None:
        super().__init__(parent)
        p = get_palette()
        self.setWindowTitle("排班详情")
        self.setMinimumWidth(400)
        self.setStyleSheet(f"background: {p.bg_card}; border-radius: 16px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # 标题
        activity_name = activity.get("name", "未知活动") if activity else "未知活动"
        title_label = QLabel(activity_name)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {p.border_light};")
        layout.addWidget(sep)

        # 活动信息
        if activity:
            activity_fields = [
                ("活动名称", activity.get("name", "—")),
                ("活动地点", activity.get("location", "—")),
                ("报名开始", format_datetime(activity.get("signup_start", ""))),
                ("报名结束", format_datetime(activity.get("signup_end", ""))),
                ("活动类型", activity.get("activity_type", "—")),
            ]
            section_label = QLabel("活动信息")
            section_label.setStyleSheet(f"color: {p.accent}; font-weight: 700; font-size: 13px;")
            layout.addWidget(section_label)
            for label_text, value in activity_fields:
                row = QHBoxLayout()
                lbl = QLabel(f"{label_text}:")
                lbl.setStyleSheet(f"color: {p.text_secondary}; font-weight: 600;")
                lbl.setFixedWidth(80)
                val = QLabel(str(value) if value else "—")
                val.setWordWrap(True)
                row.addWidget(lbl)
                row.addWidget(val, 1)
                layout.addLayout(row)

        # Slot 信息
        if slot:
            slot_type = slot.get("slot_type", "time_slot")
            type_text = {
                "time_slot": "时段",
                "topic": "选题",
                "course": "课程",
                "custom_option": "自定义",
            }.get(slot_type, "其他")

            slot_section = QLabel("分配信息")
            slot_section.setStyleSheet(f"color: {p.accent}; font-weight: 700; font-size: 13px;")
            layout.addWidget(slot_section)

            slot_name = slot.get("name", "")
            start_time = format_datetime(slot.get("start_time", "")) if slot.get("start_time") else ""
            end_time = format_datetime(slot.get("end_time", "")) if slot.get("end_time") else ""

            slot_fields = [
                ("选项类型", type_text),
                ("选项名称", slot_name or "—"),
                ("开始时间", start_time or "—"),
                ("结束时间", end_time or "—"),
                ("容量", f"{slot.get('used_count', 0)}/{slot.get('capacity', 0)}"),
            ]
            for label_text, value in slot_fields:
                row = QHBoxLayout()
                lbl = QLabel(f"{label_text}:")
                lbl.setStyleSheet(f"color: {p.text_secondary}; font-weight: 600;")
                lbl.setFixedWidth(80)
                val = QLabel(str(value) if value else "—")
                val.setWordWrap(True)
                row.addWidget(lbl)
                row.addWidget(val, 1)
                layout.addLayout(row)

        # 生成时间
        if result.get("created_at"):
            time_section = QLabel("记录信息")
            time_section.setStyleSheet(f"color: {p.accent}; font-weight: 700; font-size: 13px;")
            layout.addWidget(time_section)
            row = QHBoxLayout()
            lbl = QLabel("生成时间:")
            lbl.setStyleSheet(f"color: {p.text_secondary}; font-weight: 600;")
            lbl.setFixedWidth(80)
            val = QLabel(format_datetime(result["created_at"]))
            row.addWidget(lbl)
            row.addWidget(val, 1)
            layout.addLayout(row)

        layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)


class MyResultsPanel(QWidget):
    def __init__(self, schedule_repo: ScheduleRepository, activity_service: ActivityService, user: User) -> None:
        super().__init__()
        self._schedule_repo = schedule_repo
        self._activity_service = activity_service
        self._user = user

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["活动名称", "时间", "地点", "分配结果", ""])
        configure_table(self._table)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)

        group = QGroupBox("排班/分配结果列表")
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

        # 缓存数据供详情对话框使用
        self._activity_map: dict[str, dict] = {}
        self._slot_map: dict[str, dict] = {}
        self._rows_data: list[dict] = []

        self.refresh()

    def refresh(self) -> None:
        activities = self._activity_service.list_activities()
        self._activity_map = {activity["id"]: activity for activity in activities}
        rows = self._schedule_repo.list_by_user(self._user.id)
        self._rows_data = rows

        if not rows:
            set_table_empty(self._table, 5, "暂无排班/分配结果")
            return

        activity_ids = {row["activity_id"] for row in rows}
        self._slot_map: dict[str, dict] = {}
        for activity_id in activity_ids:
            for slot in self._activity_service.list_slots(activity_id):
                self._slot_map[slot["id"]] = slot

        self._table.clearSpans()
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            activity = self._activity_map.get(row["activity_id"])
            activity_name = activity.get("name", "未知活动") if activity else "未知活动"
            activity_location = activity.get("location", "") if activity else ""

            self._table.setItem(row_index, 0, QTableWidgetItem(activity_name))

            # 时间信息
            slot = self._slot_map.get(row["slot_id"])
            time_text = ""
            if slot:
                start = slot.get("start_time", "")
                end = slot.get("end_time", "")
                if start:
                    time_text = format_datetime(start)
                    if end:
                        time_text += f" - {format_datetime(end)}"
                elif slot.get("name"):
                    time_text = slot["name"]
            self._table.setItem(row_index, 1, QTableWidgetItem(time_text or "—"))

            # 地点
            self._table.setItem(row_index, 2, QTableWidgetItem(activity_location or "—"))

            # 分配结果
            if slot:
                slot_type = slot.get("slot_type", "time_slot")
                type_text = {
                    "time_slot": "时段",
                    "topic": "选题",
                    "course": "课程",
                    "custom_option": "自定义",
                }.get(slot_type, "其他")
                if slot.get("name"):
                    result_text = f"[{type_text}] {slot['name']}"
                else:
                    result_text = f"[{type_text}] {format_datetime(slot.get('start_time', ''))}"
                self._table.setItem(row_index, 3, QTableWidgetItem(result_text))
            else:
                self._table.setItem(row_index, 3, QTableWidgetItem("—"))

        self._table.setColumnHidden(4, True)

    def _on_row_double_clicked(self, row: int, _col: int) -> None:
        if row < 0 or row >= len(self._rows_data):
            return
        result = self._rows_data[row]
        activity = self._activity_map.get(result.get("activity_id"))
        slot = self._slot_map.get(result.get("slot_id"))
        dlg = ResultDetailDialog(result, activity, slot, self)
        dlg.exec()
