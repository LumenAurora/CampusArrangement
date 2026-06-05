from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
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

from app.application.activity_service import ActivityService
from app.application.registration_service import RegistrationService
from app.domain.exceptions import CapacityExceeded, ConflictError, ValidationError
from app.domain.models import ActivityStatus, RegistrationStatus, SignupMode, User
from app.infrastructure.notifications import notify
from app.infrastructure.repositories import RegistrationRepository
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, set_banner, set_table_empty, CountdownLabel, format_status


class RegistrationPanel(QWidget):
    def __init__(
        self,
        activity_service: ActivityService,
        registration_service: RegistrationService,
        user: User,
        reg_repo: RegistrationRepository,
    ) -> None:
        super().__init__()
        self._activity_service = activity_service
        self._registration_service = registration_service
        self._user = user
        self._reg_repo = reg_repo

        self._activity_selector = QComboBox()
        self._activity_selector.setMinimumWidth(220)
        self._slot_selector = QComboBox()
        self._slot_selector.setMinimumWidth(220)
        self._message = QLabel("")
        set_banner(self._message, "info", "")

        self._countdown_label = CountdownLabel("", "")

        self._slot_table = QTableWidget(0, 6)
        self._slot_table.setHorizontalHeaderLabels(["ID", "开始", "结束", "容量", "已用", "剩余"])
        configure_table(self._slot_table)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow("活动", self._activity_selector)
        form.addRow(self._countdown_label)
        form.addRow("时段", self._slot_selector)
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

        self._my_reg_table = QTableWidget(0, 5)
        self._my_reg_table.setHorizontalHeaderLabels(["报名ID", "活动", "时段", "状态", "操作"])
        configure_table(self._my_reg_table)

        my_reg_group = QGroupBox("我的报名")
        my_reg_layout = QVBoxLayout()
        my_reg_layout.setContentsMargins(12, 12, 12, 12)
        my_reg_layout.addWidget(self._my_reg_table)
        my_reg_group.setLayout(my_reg_layout)

        table_group = QGroupBox("时段详情")
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.addWidget(self._slot_table)
        table_group.setLayout(table_layout)

        header = make_page_header("报名", "选择活动和时段完成报名")

        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        right_col.addWidget(table_group, 1)
        right_col.addWidget(my_reg_group, 1)
        right_widget = QWidget()
        right_widget.setLayout(right_col)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(16)
        body_layout.addWidget(form_group, 1)
        body_layout.addWidget(right_widget, 2)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addLayout(body_layout, 1)
        self.setLayout(layout)

        self._activity_selector.currentIndexChanged.connect(self._load_slots)
        self.refresh()

    def refresh(self) -> None:
        activities = self._activity_service.list_activities()
        self._activity_selector.clear()
        if not activities:
            set_table_empty(self._slot_table, 6, "暂无活动，请等待管理员创建活动")
            self._load_my_registrations()
            return
        open_activities = [a for a in activities if a.get("status") == ActivityStatus.OPEN.value]
        other_activities = [a for a in activities if a.get("status") != ActivityStatus.OPEN.value]
        for activity in open_activities:
            self._activity_selector.addItem(f"{activity['name']} (报名中)", activity["id"])
        if other_activities:
            self._activity_selector.insertSeparator(self._activity_selector.count())
            for activity in other_activities:
                status_text = format_status(activity.get("status", "draft"))
                self._activity_selector.addItem(f"{activity['name']} ({status_text})", activity["id"])
        self._load_slots()
        self._load_my_registrations()

    def _load_slots(self) -> None:
        activity_id = self._activity_selector.currentData()
        self._slot_selector.clear()
        if not activity_id:
            self._countdown_label.set_times("", "")
            return
        activity = self._activity_service.get_activity(activity_id)
        if activity:
            self._countdown_label.set_times(activity.get("signup_start", ""), activity.get("signup_end", ""))
        signup_mode = activity.get("signup_mode") if activity else SignupMode.REALTIME.value
        is_open = activity.get("status") == ActivityStatus.OPEN.value if activity else False
        slots = self._activity_service.list_slots(activity_id)
        if not slots:
            set_table_empty(self._slot_table, 6, "暂无时段")
            return
        self._slot_table.setRowCount(len(slots))
        for row_index, slot in enumerate(slots):
            self._slot_table.setItem(row_index, 0, QTableWidgetItem(str(slot["id"])))
            self._slot_table.setItem(row_index, 1, QTableWidgetItem(format_datetime(slot["start_time"])))
            self._slot_table.setItem(row_index, 2, QTableWidgetItem(format_datetime(slot["end_time"])))
            capacity = int(slot["capacity"])
            used = int(slot["used_count"])
            remaining = capacity - used
            capacity_item = QTableWidgetItem(str(capacity))
            capacity_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
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

            # Add slot to selector - show remaining in realtime mode
            if signup_mode == SignupMode.REALTIME.value:
                slot_label = f"{format_datetime(slot['start_time'])} - {format_datetime(slot['end_time'])} (剩余{remaining}名)"
            else:
                slot_label = f"{format_datetime(slot['start_time'])} - {format_datetime(slot['end_time'])}"
            self._slot_selector.addItem(slot_label, slot["id"])

        self._slot_table.setColumnHidden(0, True)

        # Disable submit if activity is not open
        if not is_open:
            self._slot_selector.setEnabled(False)
        else:
            self._slot_selector.setEnabled(True)

    def _load_my_registrations(self) -> None:
        try:
            regs = self._registration_service.list_user_registrations(self._user.id)
        except Exception:
            regs = []
        if not regs:
            set_table_empty(self._my_reg_table, 5, "暂无报名记录")
            return
        activities = {a["id"]: a["name"] for a in self._activity_service.list_activities()}
        slots = {s["id"]: s for s_list in [self._activity_service.list_slots(aid) for aid in activities] if s_list for s in s_list}
        self._my_reg_table.setRowCount(len(regs))
        for row_index, reg in enumerate(regs):
            self._my_reg_table.setItem(row_index, 0, QTableWidgetItem(str(reg["id"])))
            activity_name = activities.get(reg["activity_id"], "未知活动")
            self._my_reg_table.setItem(row_index, 1, QTableWidgetItem(activity_name))
            slot = slots.get(reg["slot_id"])
            slot_text = f"{format_datetime(slot['start_time'])} - {format_datetime(slot['end_time'])}" if slot else "-"
            self._my_reg_table.setItem(row_index, 2, QTableWidgetItem(slot_text))
            status_text = format_status(reg["status"])
            self._my_reg_table.setItem(row_index, 3, QTableWidgetItem(status_text))
            if reg["status"] in (RegistrationStatus.PENDING.value, RegistrationStatus.CONFIRMED.value, RegistrationStatus.NOT_ASSIGNED.value):
                cancel_btn = QPushButton("取消")
                cancel_btn.setObjectName("dangerButton")
                cancel_btn.setCursor(Qt.PointingHandCursor)
                cancel_btn.clicked.connect(lambda checked, rid=reg["id"]: self._cancel_registration(rid))
                self._my_reg_table.setCellWidget(row_index, 4, cancel_btn)
            else:
                self._my_reg_table.setItem(row_index, 4, QTableWidgetItem("-"))
        self._my_reg_table.setColumnHidden(0, True)

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
                priority=1,
            )
            set_banner(self._message, "success", "报名成功")
            notify(f"报名成功：用户 {self._user.username}")
            self._load_slots()
            self._load_my_registrations()
        except (CapacityExceeded, ConflictError, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))

    def _cancel_registration(self, registration_id: str) -> None:
        reply = QMessageBox.question(
            self,
            "确认取消",
            "确定要取消此报名吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._registration_service.cancel(user_id=self._user.id, registration_id=registration_id)
            set_banner(self._message, "success", "报名已取消")
            self._load_slots()
            self._load_my_registrations()
        except (ConflictError, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))
