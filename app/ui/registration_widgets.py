from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.activity_service import ActivityService
from app.application.registration_service import RegistrationService
from app.domain.exceptions import CapacityExceeded, ValidationError
from app.domain.models import SignupMode, User
from app.infrastructure.notifications import notify
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, set_banner, set_table_empty


class RegistrationPanel(QWidget):
    def __init__(
        self,
        activity_service: ActivityService,
        registration_service: RegistrationService,
        user: User,
    ) -> None:
        super().__init__()
        self._activity_service = activity_service
        self._registration_service = registration_service
        self._user = user

        self._activity_selector = QComboBox()
        self._activity_selector.setMinimumWidth(220)
        self._slot_selector = QComboBox()
        self._slot_selector.setMinimumWidth(220)
        self._priority = QSpinBox()
        self._priority.setRange(1, 3)
        self._priority.setSuffix(" 志愿")
        self._message = QLabel("")
        set_banner(self._message, "info", "")

        self._slot_table = QTableWidget(0, 6)
        self._slot_table.setHorizontalHeaderLabels(["ID", "开始", "结束", "容量", "已用", "剩余"])
        configure_table(self._slot_table)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow("活动", self._activity_selector)
        form.addRow("时段", self._slot_selector)
        form.addRow("志愿优先级", self._priority)
        submit_btn = QPushButton("提交报名")
        submit_btn.setObjectName("primaryButton")
        submit_btn.clicked.connect(self._register)
        form.addRow(submit_btn)
        form.addRow(self._message)

        form_group = QGroupBox("报名操作")
        form_layout = QVBoxLayout()
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.addLayout(form)
        form_group.setLayout(form_layout)

        table_group = QGroupBox("时段详情")
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.addWidget(self._slot_table)
        table_group.setLayout(table_layout)

        header = make_page_header("报名", "选择活动和时段完成报名")

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(16)
        body_layout.addWidget(form_group, 1)
        body_layout.addWidget(table_group, 2)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addLayout(body_layout)
        self.setLayout(layout)

        self._activity_selector.currentIndexChanged.connect(self._load_slots)
        self.refresh()

    def refresh(self) -> None:
        activities = self._activity_service.list_activities()
        self._activity_selector.clear()
        if not activities:
            set_table_empty(self._slot_table, 6, "暂无活动，请等待管理员创建活动")
            return
        for activity in activities:
            self._activity_selector.addItem(activity["name"], activity["id"])
        self._load_slots()

    def _load_slots(self) -> None:
        activity_id = self._activity_selector.currentData()
        self._slot_selector.clear()
        if not activity_id:
            return
        activity = self._activity_service.get_activity(activity_id)
        signup_mode = activity.get("signup_mode") if activity else SignupMode.REALTIME.value
        slots = self._activity_service.list_slots(activity_id)
        if not slots:
            set_table_empty(self._slot_table, 6, "暂无时段")
            return
        self._slot_table.setRowCount(len(slots))
        for row_index, slot in enumerate(slots):
            self._slot_table.setItem(row_index, 0, QTableWidgetItem(slot["id"]))
            self._slot_table.setItem(row_index, 1, QTableWidgetItem(format_datetime(slot["start_time"])))
            self._slot_table.setItem(row_index, 2, QTableWidgetItem(format_datetime(slot["end_time"])))
            capacity = int(slot["capacity"])
            used = int(slot["used_count"])
            remaining = capacity - used
            capacity_item = QTableWidgetItem(str(capacity))
            for item in (capacity_item,):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._slot_table.setItem(row_index, 3, capacity_item)
            if signup_mode == SignupMode.BLIND.value:
                used_text = "保密"
                remaining_text = "保密"
            else:
                used_text = str(used)
                remaining_text = str(remaining)
            used_item = QTableWidgetItem(used_text)
            remaining_item = QTableWidgetItem(remaining_text)
            for item in (used_item, remaining_item):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._slot_table.setItem(row_index, 4, used_item)
            self._slot_table.setItem(row_index, 5, remaining_item)
            self._slot_selector.addItem(
                f"{format_datetime(slot['start_time'])} - {format_datetime(slot['end_time'])}",
                slot["id"],
            )
        self._slot_table.setColumnHidden(0, True)

    def _register(self) -> None:
        try:
            set_banner(self._message, "info", "")
            activity_id = self._activity_selector.currentData()
            slot_id = self._slot_selector.currentData()
            if not activity_id or not slot_id:
                raise ValidationError("请选择活动与时段")
            self._registration_service.register(
                user_id=self._user.id,
                activity_id=activity_id,
                slot_id=slot_id,
                priority=self._priority.value(),
            )
            set_banner(self._message, "success", "报名成功")
            notify(f"报名成功：用户 {self._user.username}")
            self._load_slots()
        except (CapacityExceeded, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))
