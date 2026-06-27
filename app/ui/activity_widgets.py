from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from app.application.activity_service import ActivityService
from app.application.remote_services import RemoteSchedulingService
from app.application.scheduling_service import SchedulingService
from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import AllocationMode, ActivityType, CheckInMode, Role, SignupMode, SlotType, User
from app.infrastructure.notifications import notify
from app.infrastructure.repositories import ActivityRepository, RegistrationRepository
from app.ui.style import get_palette
from app.ui.ui_utils import (
    ItemDetailDialog,
    ModeSelector,
    SearchBox,
    StyledComboBox,
    configure_table,
    format_activity_status,
    format_datetime,
    format_slot_name,
    format_status,
    make_page_header,
    make_status_item,
    set_banner,
    set_table_empty,
)


class _CapacityBar(QWidget):
    """A compact visual capacity bar colored by usage ratio."""

    def __init__(self, used: int, capacity: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._used = used
        self._capacity = capacity
        self.setFixedHeight(22)
        self.setMinimumWidth(90)

    def paintEvent(self, event):  # noqa: N802
        p = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background track
        painter.setBrush(QColor(p.bg_input))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 4, 4)

        ratio = self._used / self._capacity if self._capacity > 0 else 0
        ratio = min(ratio, 1.0)

        # Fill color based on usage
        if ratio < 0.5:
            fill_color = QColor(p.success_fg)
        elif ratio < 0.8:
            fill_color = QColor(p.warning_fg)
        else:
            fill_color = QColor(p.error_fg)

        fill_width = int((self.width() - 2) * ratio)
        if fill_width > 0:
            painter.setBrush(fill_color)
            painter.drawRoundedRect(1, 1, fill_width, self.height() - 2, 3, 3)

        # Text label
        text_color = QColor(p.text_on_accent) if ratio > 0.35 else QColor(p.text_primary)
        painter.setPen(text_color)
        painter.drawText(self.rect(), Qt.AlignCenter, f"{self._used}/{self._capacity}")
        painter.end()


class ActivityPanel(QWidget):
    def __init__(self, activity_service: ActivityService, user: User, scheduling_service: SchedulingService | None = None, activity_repo: ActivityRepository | None = None, group_repo=None) -> None:
        super().__init__()
        self._service = activity_service
        self._user = user
        self._scheduling_service = scheduling_service
        self._activity_repo = activity_repo
        self._group_repo = group_repo

        self._activity_table = QTableWidget(0, 9)
        self._activity_table.setHorizontalHeaderLabels(["ID", "名称", "报名开始", "报名截止", "名额显示", "分配策略", "地点", "状态", "操作"])
        configure_table(self._activity_table)

        # 选项列表改用 TreeWidget 以支持层级展示
        self._slot_tree = QTreeWidget()
        self._slot_tree.setHeaderLabels(["名称", "类型", "开始", "结束", "容量", "已用", "剩余", "使用率"])
        self._slot_tree.setAlternatingRowColors(True)
        self._slot_tree.setAnimated(True)
        self._slot_tree.setExpandsOnDoubleClick(True)
        self._slot_tree.setColumnWidth(0, 200)
        self._slot_tree.setColumnWidth(1, 60)
        self._slot_tree.setColumnWidth(2, 130)
        self._slot_tree.setColumnWidth(3, 130)
        self._slot_tree.setColumnWidth(4, 50)
        self._slot_tree.setColumnWidth(5, 50)
        self._slot_tree.setColumnWidth(6, 50)
        self._slot_tree.setColumnWidth(7, 110)

        self._activity_selector = StyledComboBox()
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
        status_btn_layout.setSpacing(6)
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

        # Review group
        status_btn_layout.addWidget(self._submit_review_btn)
        status_btn_layout.addWidget(self._publish_btn)
        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setFrameShadow(QFrame.Sunken)
        sep1.setFixedWidth(1)
        p = get_palette()
        sep1.setStyleSheet(f"color: {p.border_light};")
        status_btn_layout.addWidget(sep1)
        # Moderation group
        status_btn_layout.addWidget(self._reject_btn)
        status_btn_layout.addWidget(self._close_btn)
        status_btn_layout.addWidget(self._archive_btn)
        # Spacer + separator + destructive
        status_btn_layout.addStretch(1)
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setFrameShadow(QFrame.Sunken)
        sep2.setFixedWidth(1)
        sep2.setStyleSheet(f"color: {p.border_light};")
        status_btn_layout.addWidget(sep2)
        status_btn_layout.addWidget(self._delete_btn)
        activity_list_layout.addLayout(status_btn_layout)

        self._activity_list_group.setLayout(activity_list_layout)

        self._slot_list_group = QGroupBox("选项列表")
        slot_list_layout = QVBoxLayout()
        slot_list_layout.setContentsMargins(12, 12, 12, 12)

        # 活动详情信息卡
        self._detail_card = QFrame()
        self._detail_card.setObjectName("activityDetailCard")
        p = get_palette()
        self._detail_card.setStyleSheet(
            f"QFrame#activityDetailCard {{ background: {p.bg_elevated}; border: 1px solid {p.border_light}; border-radius: 10px; padding: 8px 12px; }}"
        )
        detail_grid = QGridLayout()
        detail_grid.setContentsMargins(8, 6, 8, 6)
        detail_grid.setHorizontalSpacing(20)
        detail_grid.setVerticalSpacing(4)

        self._detail_name_label = QLabel("-")
        self._detail_name_label.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {p.text_primary};")
        self._detail_location_label = QLabel("-")
        self._detail_location_label.setStyleSheet(f"color: {p.accent}; font-weight: 500;")
        self._detail_signup_label = QLabel("-")
        self._detail_signup_label.setStyleSheet(f"color: {p.text_secondary}; font-size: 12px;")
        self._detail_status_label = QLabel("-")
        self._detail_status_label.setStyleSheet(f"font-weight: 600;")
        self._detail_allocation_label = QLabel("-")
        self._detail_allocation_label.setStyleSheet(f"color: {p.text_secondary}; font-size: 12px;")

        detail_grid.addWidget(QLabel("活动"), 0, 0)
        detail_grid.addWidget(self._detail_name_label, 0, 1)
        detail_grid.addWidget(QLabel("地点"), 0, 2)
        detail_grid.addWidget(self._detail_location_label, 0, 3)
        detail_grid.addWidget(QLabel("报名时间"), 1, 0)
        detail_grid.addWidget(self._detail_signup_label, 1, 1)
        detail_grid.addWidget(QLabel("状态"), 1, 2)
        detail_grid.addWidget(self._detail_status_label, 1, 3)
        detail_grid.addWidget(QLabel("分配策略"), 0, 4)
        detail_grid.addWidget(self._detail_allocation_label, 0, 5)

        # Style the grid labels
        for row in range(detail_grid.rowCount()):
            for col in range(0, detail_grid.columnCount(), 2):
                item = detail_grid.itemAtPosition(row, col)
                if item and item.widget():
                    item.widget().setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px; font-weight: 600;")

        self._detail_card.setLayout(detail_grid)
        self._detail_card.setVisible(False)

        slot_list_layout.addWidget(self._detail_card)
        slot_list_layout.addWidget(self._slot_tree)
        self._slot_list_group.setLayout(slot_list_layout)

        # Left column: tab-based layout to reduce visual clutter
        p = get_palette()
        tab_widget = QTabWidget()
        tab_widget.addTab(self._activity_group, "创建活动")
        tab_widget.addTab(self._slot_group, "添加选项")
        tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: transparent;
            }}
            QTabBar::tab {{
                background: {p.btn_secondary_bg};
                color: {p.btn_secondary_fg};
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
                margin: 2px;
                font-weight: 600;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background: {p.accent};
                color: {p.text_on_accent};
            }}
            QTabBar::tab:hover:!selected {{
                background: {p.btn_secondary_hover};
            }}
        """)

        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        left_col.addWidget(tab_widget)
        left_col.addStretch(1)
        left_widget = QWidget()
        left_widget.setLayout(left_col)
        left_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        left_scroll = QScrollArea()
        left_scroll.setWidget(left_widget)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(280)
        left_scroll.setMaximumWidth(520)
        left_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        right_col.addWidget(self._activity_list_group, 1)
        right_col.addWidget(self._slot_list_group, 1)
        right_widget = QWidget()
        right_widget.setLayout(right_col)

        # 使用 QSplitter 替代固定比例，解决宽度显示不全问题
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_scroll)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([360, 720])

        header = make_page_header("活动管理", "创建活动、配置时段与报名策略")

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addWidget(splitter, 1)
        self.setLayout(layout)

        self._activity_selector.currentIndexChanged.connect(self._load_slots)
        self._activity_table.itemSelectionChanged.connect(self._update_status_buttons)
        self._activity_table.cellDoubleClicked.connect(self._on_activity_double_clicked)
        self.refresh()

    def _init_activity_form(self) -> None:
        self._activity_name = QLineEdit()
        self._activity_name.setPlaceholderText("例如：志愿服务（图书馆）")
        self._activity_type = ModeSelector()
        self._activity_type.addItem("活动报名（时段模式）", ActivityType.TIME_SLOT)
        self._activity_type.addItem("选课/选题（非时段模式）", ActivityType.NON_TIME_SLOT)
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
        self._signup_mode = ModeSelector()
        self._signup_mode.addItem("实时显示名额", SignupMode.REALTIME)
        self._signup_mode.addItem("非实时显示名额", SignupMode.BLIND)
        self._allocation_mode = ModeSelector()
        self._allocation_mode.addItem("志愿优先(贪心)", AllocationMode.GREEDY)
        self._allocation_mode.addItem("先到先得", AllocationMode.FIRST_COME)
        self._allocation_mode.addItem("抽签随机", AllocationMode.LOTTERY)
        self._checkin_mode = ModeSelector()
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
        form.addRow("模式", self._activity_type)
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
        # 小组限制
        self._group_selector = StyledComboBox()
        self._group_selector.addItem("公开（全体用户）", None)
        form.addRow("报名范围", self._group_selector)
        form.addRow(create_btn)
        form.addRow(self._activity_message)

        self._activity_group = QGroupBox("创建活动")
        self._activity_group.setLayout(form)

    def _init_slot_form(self) -> None:
        # 根据活动模式动态切换的表单
        self._slot_name = QLineEdit()
        self._slot_name.setPlaceholderText("例如：周二下午3-6点 / 机器学习选题A")

        # 时段模式字段
        self._slot_start = QDateTimeEdit(QDateTime.currentDateTime())
        self._slot_start.setCalendarPopup(True)
        self._slot_start.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._slot_end = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self._slot_end.setCalendarPopup(True)
        self._slot_end.setDisplayFormat("yyyy-MM-dd HH:mm")

        # 非时段模式字段
        self._slot_option_type = ModeSelector()
        self._slot_option_type.addItem("选题", SlotType.TOPIC)
        self._slot_option_type.addItem("课程", SlotType.COURSE)
        self._slot_option_type.addItem("自定义", SlotType.CUSTOM_OPTION)
        self._slot_description = QLineEdit()
        self._slot_description.setPlaceholderText("选项的详细说明")

        self._slot_capacity = QSpinBox()
        self._slot_capacity.setRange(1, 1000)
        self._auto_create_position = ModeSelector()
        self._auto_create_position.addItem("不划分岗位", "none")
        self._auto_create_position.addItem("自动创建默认岗位", "default")
        self._auto_create_position.setCurrentIndex(0)
        self._slot_message = QLabel("")
        set_banner(self._slot_message, "info", "")
        self._add_slot_btn = QPushButton("添加时段")
        self._add_slot_btn.setObjectName("secondaryButton")
        self._add_slot_btn.clicked.connect(self._add_slot)

        # 岗位管理（时段模式下，为选中时段添加子岗位）
        self._position_name = QLineEdit()
        self._position_name.setPlaceholderText("例如：接待员、引导员")
        self._position_capacity = QSpinBox()
        self._position_capacity.setRange(1, 1000)
        self._position_capacity.setValue(1)
        self._add_position_btn = QPushButton("为选中时段添加岗位")
        self._add_position_btn.setObjectName("secondaryButton")
        self._add_position_btn.clicked.connect(self._add_position)
        self._add_default_position_btn = QPushButton("一键创建默认岗位")
        self._add_default_position_btn.setObjectName("secondaryButton")
        self._add_default_position_btn.clicked.connect(self._add_default_position)

        # 批量添加时段控件（仅时段模式）
        self._batch_start_date = QDateTimeEdit(QDateTime.currentDateTime())
        self._batch_start_date.setCalendarPopup(True)
        self._batch_start_date.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._batch_end_date = QDateTimeEdit(QDateTime.currentDateTime().addDays(7))
        self._batch_end_date.setCalendarPopup(True)
        self._batch_end_date.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._batch_interval = ModeSelector()
        self._batch_interval.addItems(["每天", "每2天", "每3天", "每周", "每2周"])
        self._batch_day_of_week = ModeSelector()
        self._batch_day_of_week.addItems(["周一", "周二", "周三", "周四", "周五", "周六", "周日"])
        self._batch_day_of_week.setEnabled(False)
        self._batch_start_time = QDateTimeEdit(QDateTime.currentDateTime().time())
        self._batch_start_time.setCalendarPopup(False)
        self._batch_start_time.setDisplayFormat("HH:mm")
        self._batch_duration = QSpinBox()
        self._batch_duration.setRange(1, 24)
        self._batch_duration.setValue(3)
        self._batch_duration.setSuffix(" 小时")
        self._batch_capacity = QSpinBox()
        self._batch_capacity.setRange(1, 1000)
        self._batch_capacity.setValue(5)
        # 批量添加时可同时创建岗位
        self._batch_position_name = QLineEdit()
        self._batch_position_name.setPlaceholderText("留空则不创建岗位，例如：志愿者")
        self._batch_position_capacity = QSpinBox()
        self._batch_position_capacity.setRange(1, 1000)
        self._batch_position_capacity.setValue(1)
        batch_add_btn = QPushButton("批量添加时段")
        batch_add_btn.setObjectName("primaryButton")
        batch_add_btn.clicked.connect(self._batch_add_slots)

        self._batch_interval.currentIndexChanged.connect(self._on_batch_interval_changed)

        # 主表单
        self._slot_form = QFormLayout()
        self._slot_form.setHorizontalSpacing(12)
        self._slot_form.setVerticalSpacing(10)
        self._slot_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._slot_form.addRow("活动", self._activity_selector)
        self._slot_form.addRow("名称", self._slot_name)
        # 时段模式字段
        self._slot_form.addRow("开始时间", self._slot_start)
        self._slot_form.addRow("结束时间", self._slot_end)
        # 非时段模式字段
        self._slot_form.addRow("选项类型", self._slot_option_type)
        self._slot_form.addRow("说明", self._slot_description)
        self._slot_form.addRow("容量", self._slot_capacity)
        self._slot_form.addRow("岗位模式", self._auto_create_position)
        self._slot_form.addRow(self._add_slot_btn)
        self._slot_form.addRow(self._slot_message)

        # 岗位管理区域（时段模式）—— 整体控制可见性
        p = get_palette()
        self._position_section = QWidget()
        position_layout = QFormLayout()
        position_layout.setContentsMargins(0, 0, 0, 0)
        position_layout.setHorizontalSpacing(12)
        position_layout.setVerticalSpacing(10)
        position_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        position_title = QLabel("岗位管理（时段模式）")
        position_title.setStyleSheet(
            f"font-weight: bold; font-size: 13px; margin-top: 6px; color: {p.text_secondary};"
        )
        position_layout.addRow(position_title)
        position_layout.addRow("岗位名称", self._position_name)
        position_layout.addRow("岗位容量", self._position_capacity)
        position_layout.addRow(self._add_position_btn)
        position_layout.addRow(self._add_default_position_btn)
        self._position_section.setLayout(position_layout)
        self._slot_form.addRow(self._position_section)

        # 批量添加区域（时段模式）—— 整体控制可见性
        self._batch_section = QWidget()
        batch_layout = QFormLayout()
        batch_layout.setContentsMargins(0, 0, 0, 0)
        batch_layout.setHorizontalSpacing(12)
        batch_layout.setVerticalSpacing(10)
        batch_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        batch_title = QLabel("批量添加时段")
        batch_title.setStyleSheet(
            f"font-weight: bold; font-size: 13px; margin-top: 6px; color: {p.text_secondary};"
        )
        batch_layout.addRow(batch_title)
        batch_layout.addRow("开始日期", self._batch_start_date)
        batch_layout.addRow("结束日期", self._batch_end_date)
        batch_layout.addRow("重复间隔", self._batch_interval)
        batch_layout.addRow("周几", self._batch_day_of_week)
        batch_layout.addRow("每天开始时间", self._batch_start_time)
        batch_layout.addRow("持续时长", self._batch_duration)
        batch_layout.addRow("容量", self._batch_capacity)
        batch_layout.addRow("岗位名称", self._batch_position_name)
        batch_layout.addRow("岗位容量", self._batch_position_capacity)
        batch_layout.addRow(batch_add_btn)
        self._batch_section.setLayout(batch_layout)
        self._slot_form.addRow(self._batch_section)

        self._slot_group = QGroupBox("添加选项")
        self._slot_group.setLayout(self._slot_form)

        # 初始状态：根据选中活动的模式动态调整
        self._update_slot_form_mode()

    def _update_slot_form_mode(self) -> None:
        """根据选中活动的模式，动态切换表单显示"""
        activity_id = self._activity_selector.currentData()
        is_time_slot_mode = True  # 默认时段模式
        if activity_id:
            activity = self._service.get_activity(activity_id)
            if activity:
                at = activity.get("activity_type", "time_slot")
                is_time_slot_mode = at == ActivityType.TIME_SLOT.value

        # 时段模式字段
        self._slot_start.setVisible(is_time_slot_mode)
        self._slot_end.setVisible(is_time_slot_mode)
        self._auto_create_position.setVisible(is_time_slot_mode)
        auto_pos_label = self._slot_form.labelForField(self._auto_create_position)
        if auto_pos_label:
            auto_pos_label.setVisible(is_time_slot_mode)
        # 非时段模式字段
        self._slot_option_type.setVisible(not is_time_slot_mode)
        self._slot_description.setVisible(not is_time_slot_mode)
        # 岗位管理和批量添加区域整体控制
        self._position_section.setVisible(is_time_slot_mode)
        self._batch_section.setVisible(is_time_slot_mode)

        # 更新按钮文字和表单标签
        if is_time_slot_mode:
            self._add_slot_btn.setText("添加时段")
            self._slot_group.setTitle("添加时段")
            self._slot_name.setPlaceholderText("例如：周二下午3-6点")
            name_label = self._slot_form.labelForField(self._slot_name)
            if name_label:
                name_label.setText("名称")
        else:
            self._add_slot_btn.setText("添加选项")
            self._slot_group.setTitle("添加选项")
            self._slot_name.setPlaceholderText("例如：机器学习选题A / 高等数学")
            name_label = self._slot_form.labelForField(self._slot_name)
            if name_label:
                name_label.setText("选项名称")

    def refresh(self) -> None:
        self._all_activities = self._service.list_activities()
        self._filter_activities(self._search_box.text())
        # 更新小组选择器
        if self._group_repo:
            current = self._group_selector.currentData()
            self._group_selector.blockSignals(True)
            self._group_selector.clear()
            self._group_selector.addItem("公开（全体用户）", None)
            for g in self._group_repo.list_all():
                self._group_selector.addItem(g["name"], g["id"])
            # 恢复之前的选中项
            if current:
                for i in range(self._group_selector.count()):
                    if self._group_selector.itemData(i) == current:
                        self._group_selector.setCurrentIndex(i)
                        break
            self._group_selector.blockSignals(False)

    def _on_activity_double_clicked(self, row: int, _col: int) -> None:
        id_item = self._activity_table.item(row, 0)
        if not id_item:
            return
        activity_id = id_item.text()
        activity = next((a for a in self._all_activities if a["id"] == activity_id), None)
        if not activity:
            return
        signup_mode_text = "实时" if activity.get("signup_mode") == SignupMode.REALTIME.value else "非实时"
        allocation_mode = activity.get("allocation_mode", AllocationMode.GREEDY.value)
        allocation_text = {
            AllocationMode.GREEDY.value: "志愿优先",
            AllocationMode.FIRST_COME.value: "先到先得",
            AllocationMode.LOTTERY.value: "抽签",
        }.get(allocation_mode, "志愿优先")
        data = {
            "ID": str(activity.get("id", "")),
            "名称": activity.get("name", ""),
            "报名开始": format_datetime(activity["signup_start"]) if activity.get("signup_start") else "—",
            "报名截止": format_datetime(activity["signup_end"]) if activity.get("signup_end") else "—",
            "名额显示": signup_mode_text,
            "分配策略": allocation_text,
            "地点": activity.get("location") or "—",
            "状态": format_activity_status(activity),
            "详情": activity.get("details") or "—",
        }
        ItemDetailDialog("活动详情", data, self).exec()

    def _filter_activities(self, query: str) -> None:
        query = query.strip().lower()
        if query:
            activities = [a for a in self._all_activities if query in a["name"].lower() or query in a.get("details", "").lower()]
        else:
            activities = self._all_activities

        if not activities:
            set_table_empty(self._activity_table, 9, "暂无活动，请先创建活动")
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
            # Location with prominent styling
            location_text = activity.get("location") or "-"
            location_label = QLabel(f"📍 {location_text}")
            p = get_palette()
            location_label.setStyleSheet(
                f"color: {p.accent}; font-weight: 500; padding: 2px 6px; "
                f"background: {p.accent_soft}; border-radius: 4px;"
            )
            location_label.setAlignment(Qt.AlignCenter)
            self._activity_table.setCellWidget(row_index, 6, location_label)
            status_text = format_activity_status(activity)
            self._activity_table.setItem(row_index, 7, make_status_item(status_text))

            copy_btn = QPushButton("复制")
            copy_btn.setObjectName("secondaryButton")
            copy_btn.setProperty("activity_id", activity["id"])
            copy_btn.clicked.connect(self._on_copy_activity)
            self._activity_table.setCellWidget(row_index, 8, copy_btn)

            # 活动选择器显示模式标签
            at = activity.get("activity_type", "time_slot")
            mode_tag = "时段" if at == ActivityType.TIME_SLOT.value else "选项"
            self._activity_selector.addItem(f"{activity['name']} [{mode_tag}]", activity["id"])
        self._activity_selector.blockSignals(False)

        self._activity_table.setColumnHidden(0, True)
        self._update_status_buttons()
        self._load_slots()

    def _load_slots(self) -> None:
        self._update_slot_form_mode()
        activity_id = self._activity_selector.currentData()
        self._slot_tree.clear()
        if not activity_id:
            self._update_activity_detail_card()
            return
        slots = self._service.list_slots(activity_id)
        if not slots:
            item = QTreeWidgetItem(["暂无选项，请添加", "", "", "", "", "", "", ""])
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self._slot_tree.addTopLevelItem(item)
            self._update_activity_detail_card()
            return

        # 分离父级和子级
        parent_slots = [s for s in slots if not s.get("parent_slot_id")]
        child_map: dict[str, list[dict]] = {}
        for s in slots:
            pid = s.get("parent_slot_id")
            if pid:
                child_map.setdefault(pid, []).append(s)

        for slot in parent_slots:
            slot_type = slot.get("slot_type", "time_slot")
            type_text = {
                "time_slot": "时段",
                "topic": "选题",
                "course": "课程",
                "custom_option": "自定义",
            }.get(slot_type, "其他")
            name = format_slot_name(slot)
            start_text = format_datetime(slot["start_time"]) if slot.get("start_time") else "-"
            end_text = format_datetime(slot["end_time"]) if slot.get("end_time") else "-"
            capacity = int(slot["capacity"])
            used = int(slot["used_count"])
            remaining = capacity - used

            parent_item = QTreeWidgetItem([name, type_text, start_text, end_text, str(capacity), str(used), str(remaining), ""])
            parent_item.setData(0, Qt.UserRole, slot)
            self._slot_tree.addTopLevelItem(parent_item)
            self._slot_tree.setItemWidget(parent_item, 7, _CapacityBar(used, capacity))

            # 添加子岗位
            children = child_map.get(slot["id"], [])
            for child in children:
                child_name = format_slot_name(child)
                child_capacity = int(child["capacity"])
                child_used = int(child["used_count"])
                child_remaining = child_capacity - child_used
                child_item = QTreeWidgetItem([f"  └ {child_name}", "岗位", "", "", str(child_capacity), str(child_used), str(child_remaining), ""])
                child_item.setData(0, Qt.UserRole, child)
                parent_item.addChild(child_item)
                self._slot_tree.setItemWidget(child_item, 7, _CapacityBar(child_used, child_capacity))

            if children:
                parent_item.setExpanded(True)
            elif slot_type == "time_slot":
                # 时段模式下，没有子岗位时显示提示
                hint_item = QTreeWidgetItem(["  └ 未划分岗位（报名直接分配到时段）", "", "", "", "", "", "", ""])
                hint_item.setFlags(hint_item.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsEditable)
                p_hint = get_palette()
                hint_item.setForeground(0, QColor(p_hint.text_tertiary))
                parent_item.addChild(hint_item)
                parent_item.setExpanded(True)

        self._update_activity_detail_card()

    def _on_copy_activity(self) -> None:
        btn = self.sender()
        activity_id = btn.property("activity_id")
        if not activity_id:
            return

        activity = self._service.get_activity(activity_id)
        if not activity:
            return

        dialog = CopyActivityDialog(activity)
        if dialog.exec() == QDialog.Accepted:
            try:
                self._service.duplicate_activity(
                    user=self._user,
                    activity_id=activity_id,
                    new_signup_start=dialog.get_signup_start(),
                    new_signup_end=dialog.get_signup_end(),
                    new_checkin_start=dialog.get_checkin_start(),
                    new_checkin_end=dialog.get_checkin_end(),
                )
                self.refresh()
                set_banner(self._activity_message, "success", "活动已复制")
            except (PermissionDenied, ValidationError) as exc:
                set_banner(self._activity_message, "error", str(exc))
            except Exception as exc:
                set_banner(self._activity_message, "error", f"复制失败：{exc}")

    def _create_activity(self) -> None:
        try:
            set_banner(self._activity_message, "info", "")
            # Client-side validation
            name = self._activity_name.text().strip()
            if not name:
                set_banner(self._activity_message, "error", "活动名称不能为空")
                return
            signup_start = self._signup_start.dateTime().toPython()
            signup_end = self._signup_end.dateTime().toPython()
            if signup_end <= signup_start:
                set_banner(self._activity_message, "error", "报名截止时间必须晚于开始时间")
                return
            activity = self._service.create_activity(
                user=self._user,
                name=name,
                signup_start=signup_start,
                signup_end=signup_end,
                details=self._details.text().strip(),
                signup_mode=SignupMode(self._signup_mode.currentData()),
                allocation_mode=AllocationMode(self._allocation_mode.currentData()),
                location=self._location.text().strip(),
                activity_type=ActivityType(self._activity_type.currentData()),
                checkin_mode=self._checkin_mode.currentData(),
                checkin_start=self._checkin_start.dateTime().toPython(),
                checkin_end=self._checkin_end.dateTime().toPython(),
                group_id=self._group_selector.currentData(),
            )
            self.refresh()
            # Clear form fields after successful creation
            self._activity_name.clear()
            self._details.clear()
            self._location.clear()
            from datetime import datetime, timedelta
            now = datetime.now()
            self._signup_start.setDateTime(now)
            self._signup_end.setDateTime(now + timedelta(days=1))
            set_banner(self._activity_message, "success", f"已创建活动：{activity.name}")
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._activity_message, "error", str(exc))
        except Exception as exc:
            set_banner(self._activity_message, "error", f"创建失败：{exc}")

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
        rows = self._activity_table.selectionModel().selectedRows()
        if not rows:
            return ""
        row = rows[0].row()
        id_item = self._activity_table.item(row, 0)
        if not id_item:
            return ""
        activity_id = id_item.text()
        for activity in self._all_activities:
            if activity["id"] == activity_id:
                return activity.get("status", "")
        return ""

    def _is_selected_activity_owner(self) -> bool:
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
                if self._scheduling_service and not isinstance(self._scheduling_service, RemoteSchedulingService):
                    try:
                        self._scheduling_service.run(activity_id)
                    except Exception as sched_err:
                        try:
                            self._service.reopen_activity(user=self._user, activity_id=activity_id)
                        except Exception as reopen_err:
                            set_banner(self._activity_message, "error",
                                       f"排班失败且回滚失败：{sched_err}（回滚错误：{reopen_err}）")
                            self.refresh()
                            return
                        raise
            elif action == "archive":
                self._service.archive_activity(user=self._user, activity_id=activity_id)
            self.refresh()
            set_banner(self._activity_message, "success", f"活动「{activity_name}」已{action_text}")
        except (PermissionDenied, ValidationError) as exc:
            QMessageBox.warning(self, "操作失败", str(exc))
        except Exception as exc:
            QMessageBox.warning(self, "操作失败", f"操作异常：{exc}")

    def _update_status_buttons(self) -> None:
        status = self._get_selected_activity_status()
        has_selection = bool(status)
        is_owner = self._is_selected_activity_owner()
        is_super_admin = self._user.role == Role.SUPER_ADMIN

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
            self._submit_review_btn.setEnabled(True)
            self._publish_btn.setEnabled(is_super_admin)
        elif status == "pending_review":
            self._publish_btn.setEnabled(is_super_admin or not is_owner)
            self._reject_btn.setEnabled(not is_owner)
        elif status == "open":
            self._close_btn.setEnabled(True)
        elif status == "closed":
            self._archive_btn.setEnabled(True)

    def _update_activity_detail_card(self) -> None:
        """Update the activity detail info card based on the current activity selector."""
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            self._detail_card.setVisible(False)
            return

        activity = self._service.get_activity(activity_id)
        if not activity:
            self._detail_card.setVisible(False)
            return

        p = get_palette()
        self._detail_card.setVisible(True)

        self._detail_name_label.setText(activity.get("name", "-"))
        location = activity.get("location") or "-"
        self._detail_location_label.setText(f"📍 {location}")

        signup_start = format_datetime(activity["signup_start"]) if activity.get("signup_start") else "-"
        signup_end = format_datetime(activity["signup_end"]) if activity.get("signup_end") else "-"
        self._detail_signup_label.setText(f"{signup_start} ~ {signup_end}")

        status_text = format_activity_status(activity)
        status_color_map = {
            "报名中": p.success_fg,
            "报名未开始": p.accent,
            "报名已截止": p.error_fg,
            "报名已结束": p.error_fg,
            "签到未开始": p.accent,
            "签到中": p.success_fg,
            "签到已结束": p.error_fg,
            "已归档": p.text_tertiary,
            "草稿": p.warning_fg,
            "待审核": p.accent,
        }
        status_color = status_color_map.get(status_text, p.text_primary)
        self._detail_status_label.setText(status_text)
        self._detail_status_label.setStyleSheet(f"font-weight: 600; color: {status_color};")

        allocation_mode = activity.get("allocation_mode", AllocationMode.GREEDY.value)
        allocation_text = {
            AllocationMode.GREEDY.value: "志愿优先",
            AllocationMode.FIRST_COME.value: "先到先得",
            AllocationMode.LOTTERY.value: "抽签",
        }.get(allocation_mode, "志愿优先")
        self._detail_allocation_label.setText(allocation_text)

    def _on_batch_interval_changed(self) -> None:
        interval = self._batch_interval.currentText()
        self._batch_day_of_week.setEnabled(interval in ["每周", "每2周"])

    def _add_slot(self) -> None:
        try:
            set_banner(self._slot_message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                raise ValidationError("请选择活动")

            activity = self._service.get_activity(activity_id)
            is_time_slot_mode = activity and activity.get("activity_type") == ActivityType.TIME_SLOT.value
            name = self._slot_name.text().strip()
            capacity = self._slot_capacity.value()
            auto_position = self._auto_create_position.currentData() == "default"

            if is_time_slot_mode:
                slot = self._service.add_slot(
                    user=self._user,
                    activity_id=activity_id,
                    start_time=self._slot_start.dateTime().toPython(),
                    end_time=self._slot_end.dateTime().toPython(),
                    capacity=capacity,
                    name=name,
                )
                # 自动创建默认岗位
                if auto_position and slot:
                    position_name = name or format_slot_name({"start_time": str(slot.start_time), "end_time": str(slot.end_time), "name": "", "id": ""})
                    self._service.add_position(
                        user=self._user,
                        activity_id=activity_id,
                        parent_slot_id=slot.id,
                        name=position_name,
                        capacity=capacity,
                    )
            else:
                slot_type = SlotType(self._slot_option_type.currentData())
                metadata = self._slot_description.text().strip()
                self._service.add_slot_generic(
                    user=self._user,
                    activity_id=activity_id,
                    slot_type=slot_type,
                    name=name,
                    capacity=capacity,
                    metadata=metadata,
                )
            self.refresh()
            # Clear slot form fields after success
            self._slot_name.clear()
            self._slot_capacity.setValue(1)
            set_banner(self._slot_message, "success", "已添加" + ("（含默认岗位）" if auto_position and is_time_slot_mode else ""))
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._slot_message, "error", str(exc))
        except Exception as exc:
            set_banner(self._slot_message, "error", f"添加失败：{exc}")

    def _add_position(self) -> None:
        """为选中的时段添加子岗位"""
        try:
            set_banner(self._slot_message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                raise ValidationError("请选择活动")

            # 从 TreeWidget 获取选中的父时段
            selected = self._slot_tree.currentItem()
            if not selected:
                raise ValidationError("请先在选项列表中选择一个时段")
            slot_data = selected.data(0, Qt.UserRole)
            if not slot_data:
                raise ValidationError("请选择一个有效的时段")
            # 如果选中的是子岗位，取其父级
            if slot_data.get("parent_slot_id"):
                parent_slot_id = slot_data["parent_slot_id"]
            elif slot_data.get("slot_type") == "time_slot" and not slot_data.get("parent_slot_id"):
                parent_slot_id = slot_data["id"]
            else:
                raise ValidationError("只能为时段类型的选项添加岗位")

            name = self._position_name.text().strip()
            capacity = self._position_capacity.value()
            if not name:
                raise ValidationError("岗位名称不能为空")

            self._service.add_position(
                user=self._user,
                activity_id=activity_id,
                parent_slot_id=parent_slot_id,
                name=name,
                capacity=capacity,
            )
            self._position_name.clear()
            self._position_capacity.setValue(1)
            self.refresh()
            set_banner(self._slot_message, "success", f"已添加岗位：{name}")
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._slot_message, "error", str(exc))
        except Exception as exc:
            set_banner(self._slot_message, "error", f"添加岗位失败：{exc}")

    def _add_default_position(self) -> None:
        """为选中的时段一键创建默认岗位（名称与时段相同，容量等于时段容量）"""
        try:
            set_banner(self._slot_message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                raise ValidationError("请选择活动")

            selected = self._slot_tree.currentItem()
            if not selected:
                raise ValidationError("请先在选项列表中选择一个时段")
            slot_data = selected.data(0, Qt.UserRole)
            if not slot_data:
                raise ValidationError("请选择一个有效的时段")

            # 如果选中的是子岗位，取其父级
            if slot_data.get("parent_slot_id"):
                parent_slot_id = slot_data["parent_slot_id"]
                parent_data = None
            elif slot_data.get("slot_type") == "time_slot" and not slot_data.get("parent_slot_id"):
                parent_slot_id = slot_data["id"]
                parent_data = slot_data
            else:
                raise ValidationError("只能为时段类型的选项创建默认岗位")

            # 检查是否已有岗位
            existing_positions = self._service.list_positions(parent_slot_id)
            if existing_positions:
                raise ValidationError("该时段已有岗位，请手动添加")

            # 获取父时段信息用于生成默认岗位名
            if not parent_data:
                parent_data = self._service.list_slots(activity_id)
                parent_data = next((s for s in parent_data if s["id"] == parent_slot_id), None)
            if not parent_data:
                raise ValidationError("未找到父时段信息")

            position_name = format_slot_name(parent_data)
            capacity = int(parent_data["capacity"])

            self._service.add_position(
                user=self._user,
                activity_id=activity_id,
                parent_slot_id=parent_slot_id,
                name=position_name,
                capacity=capacity,
            )
            self.refresh()
            set_banner(self._slot_message, "success", f"已创建默认岗位：{position_name}（容量 {capacity}）")
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._slot_message, "error", str(exc))

    def _batch_add_slots(self) -> None:
        try:
            set_banner(self._slot_message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                raise ValidationError("请选择活动")

            batch_start = self._batch_start_date.dateTime().toPython()
            batch_end = self._batch_end_date.dateTime().toPython()
            interval_text = self._batch_interval.currentText()
            day_of_week_idx = self._batch_day_of_week.currentIndex()
            daily_start_time = self._batch_start_time.time()
            duration_hours = self._batch_duration.value()
            capacity = self._batch_capacity.value()
            position_name = self._batch_position_name.text().strip()
            position_capacity = self._batch_position_capacity.value()

            if batch_end <= batch_start:
                raise ValidationError("结束日期必须晚于开始日期")

            interval_map = {
                "每天": 1,
                "每2天": 2,
                "每3天": 3,
                "每周": 7,
                "每2周": 14,
            }
            step_days = interval_map.get(interval_text, 1)
            slots_added = 0
            positions_added = 0
            current_date = batch_start.date()
            end_date = batch_end.date()

            while current_date <= end_date:
                should_add = True
                if interval_text in ["每周", "每2周"]:
                    weekday = current_date.weekday()
                    if weekday != day_of_week_idx:
                        should_add = False

                if should_add:
                    start_datetime = datetime.combine(current_date, daily_start_time)
                    end_datetime = start_datetime + timedelta(hours=duration_hours)
                    slot = self._service.add_slot(
                        user=self._user,
                        activity_id=activity_id,
                        start_time=start_datetime,
                        end_time=end_datetime,
                        capacity=capacity,
                    )
                    slots_added += 1
                    # 如果填写了岗位名称，自动为该时段创建岗位
                    if position_name:
                        self._service.add_position(
                            user=self._user,
                            activity_id=activity_id,
                            parent_slot_id=slot.id,
                            name=position_name,
                            capacity=position_capacity,
                        )
                        positions_added += 1

                current_date += timedelta(days=step_days)

            if slots_added > 0:
                self.refresh()
                msg = f"已批量添加 {slots_added} 个时段"
                if positions_added > 0:
                    msg += f"（含 {positions_added} 个岗位）"
                set_banner(self._slot_message, "success", msg)
            else:
                set_banner(self._slot_message, "info", "未找到符合条件的日期")
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._slot_message, "error", str(exc))


class CopyActivityDialog(QDialog):
    def __init__(self, activity: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("复制活动")
        self._activity = activity
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout()

        hint_label = QLabel(f"复制活动: <b>{self._activity.get('name', '')}</b>")
        p = get_palette()
        hint_label.setStyleSheet(f"color: {p.text_secondary}; margin-bottom: 12px;")
        layout.addWidget(hint_label)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        default_start = QDateTime.currentDateTime().addDays(7)
        default_end = default_start.addDays(7)

        self._new_signup_start = QDateTimeEdit(default_start)
        self._new_signup_start.setCalendarPopup(True)
        self._new_signup_start.setDisplayFormat("yyyy-MM-dd HH:mm")

        self._new_signup_end = QDateTimeEdit(default_end)
        self._new_signup_end.setCalendarPopup(True)
        self._new_signup_end.setDisplayFormat("yyyy-MM-dd HH:mm")

        self._new_checkin_start = QDateTimeEdit(default_start.addDays(7))
        self._new_checkin_start.setCalendarPopup(True)
        self._new_checkin_start.setDisplayFormat("yyyy-MM-dd HH:mm")

        self._new_checkin_end = QDateTimeEdit(default_start.addDays(7).addHours(3))
        self._new_checkin_end.setCalendarPopup(True)
        self._new_checkin_end.setDisplayFormat("yyyy-MM-dd HH:mm")

        quick_select = StyledComboBox()
        quick_select.addItems(["自定义", "下一周", "下两周"])
        quick_select.currentIndexChanged.connect(self._on_quick_select)

        form.addRow("快速选择", quick_select)
        form.addRow("新报名开始", self._new_signup_start)
        form.addRow("新报名截止", self._new_signup_end)
        form.addRow("新签到开始", self._new_checkin_start)
        form.addRow("新签到截止", self._new_checkin_end)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("primaryButton")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch(1)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)
        self.resize(400, 300)

    def _on_quick_select(self, index: int) -> None:
        from PySide6.QtCore import QDate
        today = QDate.currentDate()
        next_monday = today.addDays((7 - today.dayOfWeek() + 1) % 7)

        if index == 1:
            self._new_signup_start.setDate(next_monday)
            self._new_signup_end.setDate(next_monday.addDays(7))
            self._new_checkin_start.setDate(next_monday.addDays(7))
            self._new_checkin_end.setDate(next_monday.addDays(7).addDays(7))
        elif index == 2:
            self._new_signup_start.setDate(next_monday)
            self._new_signup_end.setDate(next_monday.addDays(14))
            self._new_checkin_start.setDate(next_monday.addDays(14))
            self._new_checkin_end.setDate(next_monday.addDays(21))

    def get_signup_start(self) -> datetime:
        return self._new_signup_start.dateTime().toPython()

    def get_signup_end(self) -> datetime:
        return self._new_signup_end.dateTime().toPython()

    def get_checkin_start(self) -> datetime | None:
        return self._new_checkin_start.dateTime().toPython()

    def get_checkin_end(self) -> datetime | None:
        return self._new_checkin_end.dateTime().toPython()
