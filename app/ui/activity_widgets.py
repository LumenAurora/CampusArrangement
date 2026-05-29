from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from app.application.activity_service import ActivityService
from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import AllocationMode, SignupMode, User
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, make_status_item, set_banner, set_table_empty


class ActivityPanel(QWidget):
    def __init__(self, activity_service: ActivityService, user: User) -> None:
        super().__init__()
        self._service = activity_service
        self._user = user

        self._activity_table = QTableWidget(0, 7)
        self._activity_table.setHorizontalHeaderLabels(["ID", "名称", "报名开始", "报名截止", "名额显示", "分配策略", "状态"])
        configure_table(self._activity_table)

        self._slot_table = QTableWidget(0, 6)
        self._slot_table.setHorizontalHeaderLabels(["ID", "开始", "结束", "容量", "已用", "剩余"])
        configure_table(self._slot_table)

        self._activity_selector = QComboBox()
        self._activity_selector.setMinimumWidth(240)

        self._init_activity_form()
        self._init_slot_form()

        self._activity_list_group = QGroupBox("活动列表")
        activity_list_layout = QVBoxLayout()
        activity_list_layout.setContentsMargins(12, 12, 12, 12)
        activity_list_layout.addWidget(self._activity_table)

        # 删除按钮
        delete_btn_layout = QHBoxLayout()
        delete_btn_layout.addStretch(1)
        self._delete_btn = QPushButton("删除选中活动")
        self._delete_btn.setObjectName("dangerButton")
        self._delete_btn.clicked.connect(self._delete_activity)
        delete_btn_layout.addWidget(self._delete_btn)
        activity_list_layout.addLayout(delete_btn_layout)

        self._activity_list_group.setLayout(activity_list_layout)

        self._slot_list_group = QGroupBox("时段列表")
        slot_list_layout = QVBoxLayout()
        slot_list_layout.setContentsMargins(12, 12, 12, 12)
        slot_list_layout.addWidget(self._slot_table)
        self._slot_list_group.setLayout(slot_list_layout)

        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        left_col.addWidget(self._activity_group)
        left_col.addWidget(self._slot_group)
        left_col.addStretch(1)
        left_widget = QWidget()
        left_widget.setLayout(left_col)

        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        right_col.addWidget(self._activity_list_group)
        right_col.addWidget(self._slot_list_group)
        right_widget = QWidget()
        right_widget.setLayout(right_col)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(16)
        body_layout.addWidget(left_widget, 1)
        body_layout.addWidget(right_widget, 2)

        header = make_page_header("活动管理", "创建活动、配置时段与报名策略")

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addLayout(body_layout)
        self.setLayout(layout)

        self._activity_selector.currentIndexChanged.connect(self._load_slots)
        self.refresh()

    def _init_activity_form(self) -> None:
        self._activity_name = QLineEdit()
        self._activity_name.setPlaceholderText("例如：志愿服务（图书馆）")
        self._signup_start = QDateTimeEdit(QDateTime.currentDateTime())
        self._signup_start.setCalendarPopup(True)
        self._signup_start.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._signup_end = QDateTimeEdit(QDateTime.currentDateTime().addDays(1))
        self._signup_end.setCalendarPopup(True)
        self._signup_end.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._details = QLineEdit()
        self._details.setPlaceholderText("简要说明活动内容与要求")
        self._signup_mode = QComboBox()
        self._signup_mode.addItem("实时显示名额", SignupMode.REALTIME)
        self._signup_mode.addItem("非实时显示名额", SignupMode.BLIND)
        self._allocation_mode = QComboBox()
        self._allocation_mode.addItem("志愿优先(贪心)", AllocationMode.GREEDY)
        self._allocation_mode.addItem("先到先得", AllocationMode.FIRST_COME)
        self._allocation_mode.addItem("抽签随机", AllocationMode.LOTTERY)
        self._activity_message = QLabel("")
        set_banner(self._activity_message, "info", "")
        create_btn = QPushButton("创建活动")
        create_btn.setObjectName("primaryButton")
        create_btn.clicked.connect(self._create_activity)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow("名称", self._activity_name)
        form.addRow("报名开始", self._signup_start)
        form.addRow("报名截止", self._signup_end)
        form.addRow("详情", self._details)
        form.addRow("名额显示", self._signup_mode)
        form.addRow("分配策略", self._allocation_mode)
        form.addRow(create_btn)
        form.addRow(self._activity_message)

        self._activity_group = QGroupBox("创建活动")
        self._activity_group.setLayout(form)

    def _init_slot_form(self) -> None:
        self._slot_start = QDateTimeEdit(QDateTime.currentDateTime())
        self._slot_start.setCalendarPopup(True)
        self._slot_start.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._slot_end = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self._slot_end.setCalendarPopup(True)
        self._slot_end.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._slot_capacity = QSpinBox()
        self._slot_capacity.setRange(1, 1000)
        self._slot_message = QLabel("")
        set_banner(self._slot_message, "info", "")
        add_btn = QPushButton("新增时段")
        add_btn.setObjectName("secondaryButton")
        add_btn.clicked.connect(self._add_slot)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow("活动", self._activity_selector)
        form.addRow("开始时间", self._slot_start)
        form.addRow("结束时间", self._slot_end)
        form.addRow("容量", self._slot_capacity)
        form.addRow(add_btn)
        form.addRow(self._slot_message)

        self._slot_group = QGroupBox("新增时段")
        self._slot_group.setLayout(form)

    def refresh(self) -> None:
        activities = self._service.list_activities()
        if not activities:
            set_table_empty(self._activity_table, 7, "暂无活动，请先创建活动")
            self._activity_selector.clear()
            self._load_slots()
            return
        self._activity_table.setRowCount(len(activities))
        self._activity_selector.clear()
        for row_index, activity in enumerate(activities):
            self._activity_table.setItem(row_index, 0, QTableWidgetItem(activity["id"]))
            self._activity_table.setItem(row_index, 1, QTableWidgetItem(activity["name"]))
            self._activity_table.setItem(row_index, 2, QTableWidgetItem(format_datetime(activity["signup_start"])))
            self._activity_table.setItem(row_index, 3, QTableWidgetItem(format_datetime(activity["signup_end"])))
            signup_mode_text = "实时" if activity.get("signup_mode") == SignupMode.REALTIME.value else "非实时"
            allocation_mode = activity.get("allocation_mode", AllocationMode.GREEDY.value)
            allocation_text = {
                AllocationMode.GREEDY.value: "志愿优先",
                AllocationMode.FIRST_COME.value: "先到先得",
                AllocationMode.LOTTERY.value: "抽签",
            }.get(allocation_mode, "志愿优先")
            self._activity_table.setItem(row_index, 4, QTableWidgetItem(signup_mode_text))
            self._activity_table.setItem(row_index, 5, QTableWidgetItem(allocation_text))
            status_text = self._format_status(activity["signup_start"], activity["signup_end"])
            self._activity_table.setItem(row_index, 6, make_status_item(status_text))
            self._activity_selector.addItem(activity["name"], activity["id"])

        self._activity_table.setColumnHidden(0, True)
        self._load_slots()

    def _load_slots(self) -> None:
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            self._slot_table.setRowCount(0)
            return
        slots = self._service.list_slots(activity_id)
        if not slots:
            set_table_empty(self._slot_table, 6, "暂无时段，请添加时段")
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
            used_item = QTableWidgetItem(str(used))
            remaining_item = QTableWidgetItem(str(remaining))
            for item in (capacity_item, used_item, remaining_item):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._slot_table.setItem(row_index, 3, capacity_item)
            self._slot_table.setItem(row_index, 4, used_item)
            self._slot_table.setItem(row_index, 5, remaining_item)

        self._slot_table.setColumnHidden(0, True)

    def _create_activity(self) -> None:
        try:
            set_banner(self._activity_message, "info", "")
            activity = self._service.create_activity(
                user=self._user,
                name=self._activity_name.text().strip(),
                signup_start=self._signup_start.dateTime().toPython(),
                signup_end=self._signup_end.dateTime().toPython(),
                details=self._details.text().strip(),
                signup_mode=SignupMode(self._signup_mode.currentData()),
                allocation_mode=AllocationMode(self._allocation_mode.currentData()),
            )
            self.refresh()
            set_banner(self._activity_message, "success", f"已创建活动：{activity.name}")
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._activity_message, "error", str(exc))

    def _delete_activity(self) -> None:
        # 获取当前选中的活动
        selected_rows = self._activity_table.selectedItems()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要删除的活动")
            return

        # 获取选中行的活动 ID（第 0 列）
        row = selected_rows[0].row()
        activity_id = self._activity_table.item(row, 0).text()
        activity_name = self._activity_table.item(row, 1).text()

        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除活动「{activity_name}」吗？\n删除后无法恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                self._service.delete_activity(user=self._user, activity_id=activity_id)
                self.refresh()
                set_banner(self._activity_message, "success", f"已删除活动：{activity_name}")
            except (PermissionDenied, ValidationError) as exc:
                set_banner(self._activity_message, "error", str(exc))

    def _add_slot(self) -> None:
        try:
            set_banner(self._slot_message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                raise ValidationError("请选择活动")
            self._service.add_slot(
                user=self._user,
                activity_id=activity_id,
                start_time=self._slot_start.dateTime().toPython(),
                end_time=self._slot_end.dateTime().toPython(),
                capacity=self._slot_capacity.value(),
            )
            self.refresh()
            set_banner(self._slot_message, "success", "时段已添加")
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._slot_message, "error", str(exc))

    @staticmethod
    def _format_status(start: str, end: str) -> str:
        now = datetime.now()
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            return "未知"
        if now < start_dt:
            return "未开始"
        if start_dt <= now <= end_dt:
            return "报名中"
        return "已结束"
