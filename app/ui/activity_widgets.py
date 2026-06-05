from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from app.application.activity_service import ActivityService
from app.application.remote_services import RemoteSchedulingService
from app.application.scheduling_service import SchedulingService
from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import AllocationMode, CheckInMode, Role, SignupMode, User
from app.infrastructure.notifications import notify
from app.infrastructure.repositories import ActivityRepository, RegistrationRepository
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, make_status_item, set_banner, set_table_empty, SearchBox, format_status


class ActivityPanel(QWidget):
    def __init__(self, activity_service: ActivityService, user: User, scheduling_service: SchedulingService | None = None, activity_repo: ActivityRepository | None = None) -> None:
        super().__init__()
        self._service = activity_service
        self._user = user
        self._scheduling_service = scheduling_service
        self._activity_repo = activity_repo

        self._activity_table = QTableWidget(0, 8)
        self._activity_table.setHorizontalHeaderLabels(["ID", "名称", "报名开始", "报名截止", "名额显示", "分配策略", "地点", "状态"])
        configure_table(self._activity_table)

        self._slot_table = QTableWidget(0, 6)
        self._slot_table.setHorizontalHeaderLabels(["ID", "开始", "结束", "容量", "已用", "剩余"])
        configure_table(self._slot_table)

        self._activity_selector = QComboBox()
        self._activity_selector.setMinimumWidth(240)

        self._search_box = SearchBox()
        self._search_box.textChanged.connect(self._filter_activities)
        self._all_activities: list[dict] = []

        self._init_activity_form()
        self._init_slot_form()

        self._activity_list_group = QGroupBox("活动列表")
        activity_list_layout = QVBoxLayout()
        activity_list_layout.setContentsMargins(12, 12, 12, 12)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索"))
        search_layout.addWidget(self._search_box, 1)
        activity_list_layout.addLayout(search_layout)

        activity_list_layout.addWidget(self._activity_table)

        status_btn_layout = QHBoxLayout()
        status_btn_layout.setSpacing(8)
        self._submit_review_btn = QPushButton("提交审核")
        self._submit_review_btn.setObjectName("secondaryButton")
        self._submit_review_btn.clicked.connect(lambda: self._change_status("submit_review"))
        self._publish_btn = QPushButton("发布")
        self._publish_btn.setObjectName("primaryButton")
        self._publish_btn.clicked.connect(lambda: self._change_status("publish"))
        self._reject_btn = QPushButton("退回修改")
        self._reject_btn.setObjectName("dangerButton")
        self._reject_btn.clicked.connect(lambda: self._change_status("reject"))
        self._close_btn = QPushButton("结束报名")
        self._close_btn.setObjectName("secondaryButton")
        self._close_btn.clicked.connect(lambda: self._change_status("close"))
        self._archive_btn = QPushButton("归档")
        self._archive_btn.setObjectName("secondaryButton")
        self._archive_btn.clicked.connect(lambda: self._change_status("archive"))
        self._delete_btn = QPushButton("删除")
        self._delete_btn.setObjectName("dangerButton")
        self._delete_btn.clicked.connect(self._delete_activity)
        status_btn_layout.addWidget(self._submit_review_btn)
        status_btn_layout.addWidget(self._publish_btn)
        status_btn_layout.addWidget(self._reject_btn)
        status_btn_layout.addWidget(self._close_btn)
        status_btn_layout.addWidget(self._archive_btn)
        status_btn_layout.addStretch(1)
        status_btn_layout.addWidget(self._delete_btn)
        activity_list_layout.addLayout(status_btn_layout)

        self._activity_list_group.setLayout(activity_list_layout)

        self._slot_list_group = QGroupBox("时段列表")
        slot_list_layout = QVBoxLayout()
        slot_list_layout.setContentsMargins(12, 12, 12, 12)
        slot_list_layout.addWidget(self._slot_table)
        self._slot_list_group.setLayout(slot_list_layout)

        # Left column in a scroll area so the form never overflows
        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        left_col.addWidget(self._activity_group)
        left_col.addWidget(self._slot_group)
        left_col.addStretch(1)
        left_widget = QWidget()
        left_widget.setLayout(left_col)
        left_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        left_scroll = QScrollArea()
        left_scroll.setWidget(left_widget)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(300)

        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        right_col.addWidget(self._activity_list_group, 1)
        right_col.addWidget(self._slot_list_group, 1)
        right_widget = QWidget()
        right_widget.setLayout(right_col)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(16)
        body_layout.addWidget(left_scroll, 1)
        body_layout.addWidget(right_widget, 2)

        header = make_page_header("活动管理", "创建活动、配置时段与报名策略")

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addLayout(body_layout, 1)
        self.setLayout(layout)

        self._activity_selector.currentIndexChanged.connect(self._load_slots)
        self._activity_table.itemSelectionChanged.connect(self._update_status_buttons)
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
        self._location = QLineEdit()
        self._location.setPlaceholderText("例如：图书馆一楼大厅（位置签到需填坐标，如 39.9042,116.4074）")
        self._signup_mode = QComboBox()
        self._signup_mode.addItem("实时显示名额", SignupMode.REALTIME)
        self._signup_mode.addItem("非实时显示名额", SignupMode.BLIND)
        self._allocation_mode = QComboBox()
        self._allocation_mode.addItem("志愿优先(贪心)", AllocationMode.GREEDY)
        self._allocation_mode.addItem("先到先得", AllocationMode.FIRST_COME)
        self._allocation_mode.addItem("抽签随机", AllocationMode.LOTTERY)
        self._checkin_mode = QComboBox()
        self._checkin_mode.addItem("手动签到", CheckInMode.MANUAL)
        self._checkin_mode.addItem("二维码签到", CheckInMode.QRCODE)
        self._checkin_mode.addItem("自助签到码", CheckInMode.SELF_CODE)
        self._checkin_mode.addItem("位置签到", CheckInMode.LOCATION)
        self._checkin_mode.addItem("拍照签到", CheckInMode.PHOTO)
        self._checkin_start = QDateTimeEdit(QDateTime.currentDateTime())
        self._checkin_start.setCalendarPopup(True)
        self._checkin_start.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._checkin_start.setSpecialValueText("不限制")
        self._checkin_end = QDateTimeEdit(QDateTime.currentDateTime().addDays(1))
        self._checkin_end.setCalendarPopup(True)
        self._checkin_end.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._checkin_end.setSpecialValueText("不限制")
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
        form.addRow("地点", self._location)
        form.addRow("名额显示", self._signup_mode)
        form.addRow("分配策略", self._allocation_mode)
        form.addRow("签到模式", self._checkin_mode)
        form.addRow("签到开始", self._checkin_start)
        form.addRow("签到截止", self._checkin_end)
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
        self._all_activities = self._service.list_activities()
        self._filter_activities(self._search_box.text())

    def _filter_activities(self, query: str) -> None:
        query = query.strip().lower()
        if query:
            activities = [a for a in self._all_activities if query in a["name"].lower() or query in a.get("details", "").lower()]
        else:
            activities = self._all_activities

        if not activities:
            set_table_empty(self._activity_table, 8, "暂无活动，请先创建活动")
            self._activity_selector.blockSignals(True)
            self._activity_selector.clear()
            self._activity_selector.blockSignals(False)
            self._load_slots()
            return
        self._activity_table.clearSpans()
        self._activity_table.setRowCount(len(activities))
        self._activity_selector.blockSignals(True)
        self._activity_selector.clear()
        for row_index, activity in enumerate(activities):
            self._activity_table.setItem(row_index, 0, QTableWidgetItem(str(activity["id"])))
            self._activity_table.setItem(row_index, 1, QTableWidgetItem(str(activity["name"])))
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
            self._activity_table.setItem(row_index, 6, QTableWidgetItem(activity.get("location", "")))
            status_text = format_status(activity.get("status", "draft"))
            self._activity_table.setItem(row_index, 7, make_status_item(status_text))
            self._activity_selector.addItem(activity["name"], activity["id"])
        self._activity_selector.blockSignals(False)

        self._activity_table.setColumnHidden(0, True)
        self._update_status_buttons()
        self._load_slots()

    def _load_slots(self) -> None:
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            self._slot_table.clearSpans()
            self._slot_table.setRowCount(0)
            return
        slots = self._service.list_slots(activity_id)
        if not slots:
            set_table_empty(self._slot_table, 6, "暂无时段，请添加时段")
            return
        self._slot_table.clearSpans()
        self._slot_table.setRowCount(len(slots))
        for row_index, slot in enumerate(slots):
            self._slot_table.setItem(row_index, 0, QTableWidgetItem(str(slot["id"])))
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
                location=self._location.text().strip(),
                checkin_mode=self._checkin_mode.currentData(),
                checkin_start=self._checkin_start.dateTime().toPython(),
                checkin_end=self._checkin_end.dateTime().toPython(),
            )
            self.refresh()
            set_banner(self._activity_message, "success", f"已创建活动：{activity.name}")
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._activity_message, "error", str(exc))

    def _delete_activity(self) -> None:
        activity_id, activity_name = self._get_selected_activity()
        if not activity_id:
            QMessageBox.warning(self, "提示", "请先选择要删除的活动")
            return

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

    def _get_selected_activity(self) -> tuple[str | None, str | None]:
        """Get the selected activity's ID and name from the table."""
        rows = self._activity_table.selectionModel().selectedRows()
        if not rows:
            return None, None
        row = rows[0].row()
        id_item = self._activity_table.item(row, 0)
        name_item = self._activity_table.item(row, 1)
        if not id_item or not name_item:
            return None, None
        return id_item.text(), name_item.text()

    def _get_selected_activity_status(self) -> str:
        """Get the raw status value of the selected activity."""
        rows = self._activity_table.selectionModel().selectedRows()
        if not rows:
            return ""
        row = rows[0].row()
        # Find the activity by ID to get the raw status
        id_item = self._activity_table.item(row, 0)
        if not id_item:
            return ""
        activity_id = id_item.text()
        for activity in self._all_activities:
            if activity["id"] == activity_id:
                return activity.get("status", "")
        return ""

    def _is_selected_activity_owner(self) -> bool:
        """Check if the current user is the owner of the selected activity."""
        rows = self._activity_table.selectionModel().selectedRows()
        if not rows:
            return False
        row = rows[0].row()
        id_item = self._activity_table.item(row, 0)
        if not id_item:
            return False
        activity_id = id_item.text()
        for activity in self._all_activities:
            if activity["id"] == activity_id:
                return activity.get("owner_id") == self._user.id
        return False

    def _change_status(self, action: str) -> None:
        activity_id, activity_name = self._get_selected_activity()
        if not activity_id:
            QMessageBox.warning(self, "提示", "请先选择要操作的活动")
            return
        action_map = {
            "submit_review": "提交审核",
            "publish": "发布",
            "reject": "退回修改",
            "close": "结束报名",
            "archive": "归档",
        }
        action_text = action_map.get(action, action)
        reply = QMessageBox.question(
            self,
            "确认操作",
            f"确定要{action_text}活动「{activity_name}」吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            if action == "submit_review":
                self._service.submit_for_review(user=self._user, activity_id=activity_id)
            elif action == "publish":
                self._service.publish_activity(user=self._user, activity_id=activity_id)
            elif action == "reject":
                self._service.reject_activity(user=self._user, activity_id=activity_id)
            elif action == "close":
                self._service.close_activity(user=self._user, activity_id=activity_id)
                # Auto-schedule after closing only in local mode;
                # in remote mode the API server already handles auto-scheduling
                if self._scheduling_service and not isinstance(self._scheduling_service, RemoteSchedulingService):
                    try:
                        self._scheduling_service.run(activity_id)
                    except Exception:
                        # Rollback activity status if scheduling fails
                        self._service.reopen_activity(user=self._user, activity_id=activity_id)
                        raise
            elif action == "archive":
                self._service.archive_activity(user=self._user, activity_id=activity_id)
            self.refresh()
            set_banner(self._activity_message, "success", f"活动「{activity_name}」已{action_text}")
        except (PermissionDenied, ValidationError) as exc:
            QMessageBox.warning(self, "操作失败", str(exc))

    def _update_status_buttons(self) -> None:
        status = self._get_selected_activity_status()
        has_selection = bool(status)
        is_owner = self._is_selected_activity_owner()
        is_super_admin = self._user.role == Role.SUPER_ADMIN

        # Default: all disabled
        self._submit_review_btn.setEnabled(False)
        self._publish_btn.setEnabled(False)
        self._reject_btn.setEnabled(False)
        self._close_btn.setEnabled(False)
        self._archive_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)

        if not has_selection:
            return

        self._delete_btn.setEnabled(True)

        if status == "draft":
            # 组织者只能"提交审核"，超级管理员可直接"发布"
            self._submit_review_btn.setEnabled(True)
            self._publish_btn.setEnabled(is_super_admin)
        elif status == "pending_review":
            # 超级管理员始终可发布（即使自己是创建者）；非创建者（审核人）可发布和退回
            self._publish_btn.setEnabled(is_super_admin or not is_owner)
            self._reject_btn.setEnabled(not is_owner)
        elif status == "open":
            self._close_btn.setEnabled(True)
        elif status == "closed":
            self._archive_btn.setEnabled(True)
        # archived: only delete is enabled

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
