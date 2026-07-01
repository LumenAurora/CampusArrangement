"""向导式活动创建面板 v2 — 模板驱动、周期支持、简洁操作流。

商业软件级设计：操作流如 Google Calendar / Eventbrite。

流程：
  第 0 步：选择创建方式（空白新建 / 模板加载 / 周期批量）
  第 1 步：基本信息（名称、详情、模式）
  第 2 步：报名规则（时间、分配、签到 — 卡片选择）
  第 3 步：时段配置（日历可视化 + 快速添加）
  第 4 步：确认创建

新增：
  - 模板系统：内置 4 套模板（每周志愿、每月值班、学期选课、单次活动）
  - 周期模式：每周 / 每月 / 学期批量生成
  - 保存为模板按钮
  - 日历视图选择时间
"""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QDateTimeEdit,
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
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.application.activity_service import ActivityService
from app.application.template_service import TemplateService, generate_recurring_activities
from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import ActivityType, AllocationMode, CheckInMode, SignupMode, SlotType, User
from app.domain.templates import ActivityTemplate, RecurrencePattern
from app.ui.style import get_palette
from app.ui.ui_utils import (
    RadioCardGroup,
    StepIndicator,
    StyledComboBox,
    set_banner,
)


class GuidedActivityPanel(QWidget):
    """向导式活动创建面板 v2。"""

    activity_created = Signal()

    def __init__(
        self,
        activity_service: ActivityService,
        user: User,
        template_service: TemplateService | None = None,
        group_repo=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = activity_service
        self._user = user
        self._tpl_service = template_service or TemplateService()
        self._group_repo = group_repo
        self._current_step = 0
        self._creation_mode = "new"  # new | template | recurring
        self._selected_template: ActivityTemplate | None = None
        self._build_ui()
        self._load_templates()

    # ═══════════════════════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        p = get_palette()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 步骤指示器（5步骤）
        self._step_indicator = StepIndicator(
            ["创建方式", "基本信息", "报名规则", "时段配置", "确认创建"],
            current=0,
        )
        layout.addWidget(self._step_indicator)

        # 步骤页面
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_step0())
        self._stack.addWidget(self._build_step1())
        self._stack.addWidget(self._build_step2())
        self._stack.addWidget(self._build_step3())
        self._stack.addWidget(self._build_step4())
        layout.addWidget(self._stack, 1)

        # 消息条
        self._message = QLabel("")
        set_banner(self._message, "info", "")
        layout.addWidget(self._message)

        # 底部导航
        nav_bar = QFrame()
        nav_bar.setStyleSheet(
            f"background: {p.bg_card}; border-top: 1px solid {p.border_light}; border-radius: 8px;"
        )
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 6, 0, 6)
        nav_layout.setSpacing(10)

        self._prev_btn = QPushButton("← 上一步")
        self._prev_btn.setStyleSheet(
            f"QPushButton {{ background: {p.btn_secondary_bg}; color: {p.btn_secondary_fg}; "
            f"border: none; border-radius: 8px; padding: 8px 18px; font-weight: 600; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {p.btn_secondary_hover}; }}"
        )
        self._prev_btn.clicked.connect(self._go_prev)

        self._save_tpl_btn = QPushButton("💾 保存模板")
        self._save_tpl_btn.setStyleSheet(
            f"QPushButton {{ background: {p.btn_secondary_bg}; color: {p.btn_secondary_fg}; "
            f"border: none; border-radius: 8px; padding: 8px 14px; font-weight: 600; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {p.btn_secondary_hover}; }}"
        )
        self._save_tpl_btn.clicked.connect(self._save_as_template)
        self._save_tpl_btn.setVisible(False)

        self._next_btn = QPushButton("下一步 →")
        self._next_btn.setStyleSheet(
            f"QPushButton {{ background: {p.accent}; color: {p.text_on_accent}; "
            f"border: none; border-radius: 8px; padding: 8px 20px; font-weight: 600; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {p.accent_hover}; }}"
        )
        self._next_btn.clicked.connect(self._go_next)

        self._create_btn = QPushButton("✓ 创建活动")
        self._create_btn.setStyleSheet(
            f"QPushButton {{ background: {p.accent}; color: {p.text_on_accent}; "
            f"border: none; border-radius: 8px; padding: 8px 20px; font-weight: 600; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {p.accent_hover}; }}"
        )
        self._create_btn.clicked.connect(self._create_activity)
        self._create_btn.setVisible(False)

        nav_layout.addWidget(self._prev_btn)
        nav_layout.addWidget(self._save_tpl_btn)
        nav_layout.addStretch()
        nav_layout.addWidget(self._next_btn)
        nav_layout.addWidget(self._create_btn)
        nav_bar.setLayout(nav_layout)
        layout.addWidget(nav_bar)

        self.setLayout(layout)
        self._update_fields_by_mode()

    # ═══════════════════════════════════════════════════════════
    # 步骤 0：创建方式
    # ═══════════════════════════════════════════════════════════

    def _build_step0(self) -> QWidget:
        p = get_palette()
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(16)

        title = QLabel("选择创建方式")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {p.text_primary};")
        layout.addWidget(title)

        subtitle = QLabel("您想如何创建活动？")
        subtitle.setStyleSheet(f"color: {p.text_secondary}; font-size: 12px;")
        layout.addWidget(subtitle)

        # 大卡片选择
        cards_layout = QGridLayout()
        cards_layout.setSpacing(12)

        self._mode_cards = RadioCardGroup()
        self._mode_cards.add_card(
            "✨ 新建活动",
            "从零开始创建，自由配置所有参数",
            "new",
        )
        self._mode_cards.add_card(
            "📋 使用模板",
            "加载预设模板快速创建，只需调整时间",
            "template",
        )
        self._mode_cards.add_card(
            "🔄 周期批量",
            "一次生成多期活动（每周/每月），适合固定岗位",
            "recurring",
        )
        self._mode_cards.set_current_index(0)
        layout.addWidget(self._mode_cards)

        # 模板选择区（初始隐藏）
        self._template_section = QWidget()
        tpl_layout = QVBoxLayout()
        tpl_layout.setContentsMargins(0, 0, 0, 0)
        tpl_layout.setSpacing(8)

        tpl_label = QLabel("选择模板")
        tpl_label.setStyleSheet(f"font-weight: 600; color: {p.text_primary};")
        tpl_layout.addWidget(tpl_label)

        self._template_selector = StyledComboBox()
        self._template_selector.setMinimumHeight(36)
        tpl_layout.addWidget(self._template_selector)

        self._tpl_desc = QLabel("")
        self._tpl_desc.setWordWrap(True)
        self._tpl_desc.setStyleSheet(
            f"color: {p.text_tertiary}; font-size: 11px; padding: 8px; "
            f"background: {p.bg_input}; border-radius: 6px;"
        )
        tpl_layout.addWidget(self._tpl_desc)

        self._template_section.setLayout(tpl_layout)
        self._template_section.setVisible(False)
        layout.addWidget(self._template_section)

        # 周期配置区（初始隐藏）
        self._recurrence_section = QWidget()
        rec_layout = QVBoxLayout()
        rec_layout.setContentsMargins(0, 0, 0, 0)
        rec_layout.setSpacing(8)

        rec_label = QLabel("周期设置")
        rec_label.setStyleSheet(f"font-weight: 600; color: {p.text_primary};")
        rec_layout.addWidget(rec_label)

        rec_row = QHBoxLayout()
        rec_row.setSpacing(12)
        rec_row.addWidget(QLabel("模式"))
        self._recurrence_mode = StyledComboBox()
        self._recurrence_mode.addItem("每周", RecurrencePattern.WEEKLY)
        self._recurrence_mode.addItem("每月", RecurrencePattern.MONTHLY)
        self._recurrence_mode.addItem("整学期", RecurrencePattern.SEMESTER)
        rec_row.addWidget(self._recurrence_mode, 1)

        rec_row2 = QHBoxLayout()
        rec_row2.setSpacing(12)
        rec_row2.addWidget(QLabel("期数"))
        self._recurrence_count = QSpinBox()
        self._recurrence_count.setRange(1, 52)
        self._recurrence_count.setValue(4)
        self._recurrence_count.setToolTip("要创建的活动个数（整学期模式固定为 1）")
        rec_row2.addWidget(self._recurrence_count, 1)

        rec_layout.addLayout(rec_row)
        rec_layout.addLayout(rec_row2)

        self._recurrence_section.setLayout(rec_layout)
        self._recurrence_section.setVisible(False)
        layout.addWidget(self._recurrence_section)

        layout.addStretch()
        page.setLayout(layout)

        # 联动
        self._mode_cards._group.buttonClicked.connect(self._on_mode_changed)
        self._template_selector.currentIndexChanged.connect(self._on_template_selected)
        return page

    # ═══════════════════════════════════════════════════════════
    # 步骤 1：基本信息
    # ═══════════════════════════════════════════════════════════

    def _build_step1(self) -> QWidget:
        p = get_palette()
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        def _label(text: str, required: bool = False) -> QLabel:
            t = text + (" *" if required else "")
            lbl = QLabel(t)
            lbl.setStyleSheet(f"font-weight: 700; font-size: 13px; color: {p.text_primary};")
            return lbl

        layout.addWidget(_label("活动名称", True))
        self._name = QLineEdit()
        self._name.setPlaceholderText("例如：图书馆志愿服务")
        self._name.setMinimumHeight(40)
        layout.addWidget(self._name)

        layout.addWidget(_label("活动详情"))
        self._details = QTextEdit()
        self._details.setPlaceholderText("简要说明活动内容、要求、注意事项…")
        self._details.setMaximumHeight(80)
        self._details.setMinimumHeight(64)
        layout.addWidget(self._details)

        # 活动模式
        layout.addWidget(_label("活动模式"))
        self._activity_type = RadioCardGroup()
        self._activity_type.add_card("时段模式", "排班/志愿/签到", ActivityType.TIME_SLOT)
        self._activity_type.add_card("非时段模式", "选课/选题/名额分配", ActivityType.NON_TIME_SLOT)
        self._activity_type.set_current_index(0)
        # 连接信号：切换活动类型时更新地点/签到字段可见性
        self._activity_type._group.buttonClicked.connect(self._update_fields_by_mode)
        layout.addWidget(self._activity_type)

        # 地点
        self._location_label = QLabel("活动地点")
        self._location_label.setStyleSheet(f"font-weight: 700; font-size: 13px; color: {p.text_primary};")
        layout.addWidget(self._location_label)
        self._location = QLineEdit()
        self._location.setPlaceholderText("例如：图书馆一楼（位置签到需坐标格式）")
        self._location.setMinimumHeight(40)
        layout.addWidget(self._location)

        layout.addStretch()
        container.setLayout(layout)
        scroll.setWidget(container)
        page_layout = QVBoxLayout()
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)
        page.setLayout(page_layout)
        return page

    # ═══════════════════════════════════════════════════════════
    # 步骤 2：报名规则
    # ═══════════════════════════════════════════════════════════

    def _build_step2(self) -> QWidget:
        p = get_palette()
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        def _section(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(f"font-weight: 700; font-size: 13px; color: {p.text_primary}; margin-top: 6px;")
            return lbl

        # 报名时间
        layout.addWidget(_section("报名时间"))
        time_row = QHBoxLayout()
        time_row.setSpacing(12)
        self._signup_start = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self._signup_start.setCalendarPopup(True)
        self._signup_start.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._signup_start.setMinimumHeight(40)
        self._signup_end = QDateTimeEdit(QDateTime.currentDateTime().addDays(7))
        self._signup_end.setCalendarPopup(True)
        self._signup_end.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._signup_end.setMinimumHeight(40)
        time_row.addWidget(QLabel("开始"))
        time_row.addWidget(self._signup_start)
        time_row.addWidget(QLabel("截止"))
        time_row.addWidget(self._signup_end)
        layout.addLayout(time_row)

        self._signup_err = QLabel("")
        self._signup_err.setStyleSheet(f"color: {p.error_fg}; font-size: 11px; padding: 0 4px;")
        self._signup_err.setVisible(False)
        layout.addWidget(self._signup_err)
        self._signup_start.dateTimeChanged.connect(self._validate_signup_time)
        self._signup_end.dateTimeChanged.connect(self._validate_signup_time)

        # 名额显示
        layout.addWidget(_section("名额显示"))
        self._signup_mode = RadioCardGroup()
        self._signup_mode.add_card("实时显示", "用户可见剩余名额，适合先到先得", SignupMode.REALTIME)
        self._signup_mode.add_card("非实时显示", "隐藏名额，适合盲报/抽签", SignupMode.BLIND)
        self._signup_mode.set_current_index(0)
        layout.addWidget(self._signup_mode)

        # 分配策略
        layout.addWidget(_section("分配策略"))
        self._allocation_mode = RadioCardGroup()
        self._allocation_mode.add_card("志愿优先", "按志愿顺序匹配，额满顺延", AllocationMode.GREEDY)
        self._allocation_mode.add_card("先到先得", "按报名时间顺序分配", AllocationMode.FIRST_COME)
        self._allocation_mode.add_card("抽签随机", "结束后随机分配", AllocationMode.LOTTERY)
        self._allocation_mode.add_card("意愿点制", "99点自由分配，高者优先", AllocationMode.POINTS)
        self._allocation_mode.set_current_index(0)
        layout.addWidget(self._allocation_mode)

        # 兼报
        layout.addWidget(_section("兼报"))
        self._allow_multiple_slots = QCheckBox("允许同用户兼报多个时段/岗位")
        layout.addWidget(self._allow_multiple_slots)

        # 报名范围
        layout.addWidget(_section("报名范围"))
        self._group_selector = StyledComboBox()
        self._group_selector.addItem("公开（全体用户）", None)
        self._group_selector.setMinimumHeight(36)
        if self._group_repo:
            for g in self._group_repo.list_all():
                self._group_selector.addItem(g["name"], g["id"])
        layout.addWidget(self._group_selector)

        # 签到（时段模式）
        self._checkin_section = QWidget()
        ck_layout = QVBoxLayout()
        ck_layout.setContentsMargins(0, 0, 0, 0)
        ck_layout.setSpacing(14)
        ck_layout.addWidget(_section("签到模式"))
        self._checkin_mode = RadioCardGroup()
        self._checkin_mode.add_card("手动签到", "管理员操作", CheckInMode.MANUAL)
        self._checkin_mode.add_card("二维码", "扫码签到", CheckInMode.QRCODE)
        self._checkin_mode.add_card("签到码", "输入码签到", CheckInMode.SELF_CODE)
        self._checkin_mode.add_card("位置", "GPS验证", CheckInMode.LOCATION)
        self._checkin_mode.add_card("拍照", "上传照片", CheckInMode.PHOTO)
        self._checkin_mode.set_current_index(0)
        ck_layout.addWidget(self._checkin_mode)

        self._checkin_sync = QCheckBox("签到时间与报名时间同步")
        self._checkin_sync.setChecked(True)
        self._checkin_sync.toggled.connect(self._on_checkin_sync_toggled)
        ck_layout.addWidget(self._checkin_sync)

        ck_time_row = QHBoxLayout()
        ck_time_row.setSpacing(12)
        self._checkin_start = QDateTimeEdit(QDateTime.currentDateTime())
        self._checkin_start.setCalendarPopup(True)
        self._checkin_start.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._checkin_start.setEnabled(False)
        self._checkin_start.setMinimumHeight(40)
        self._checkin_end = QDateTimeEdit(QDateTime.currentDateTime().addDays(1))
        self._checkin_end.setCalendarPopup(True)
        self._checkin_end.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._checkin_end.setEnabled(False)
        self._checkin_end.setMinimumHeight(40)
        ck_time_row.addWidget(QLabel("开始"))
        ck_time_row.addWidget(self._checkin_start)
        ck_time_row.addWidget(QLabel("截止"))
        ck_time_row.addWidget(self._checkin_end)
        ck_layout.addLayout(ck_time_row)

        self._checkin_err = QLabel("")
        self._checkin_err.setStyleSheet(f"color: {p.error_fg}; font-size: 11px;")
        self._checkin_err.setVisible(False)
        ck_layout.addWidget(self._checkin_err)
        self._checkin_section.setLayout(ck_layout)
        layout.addWidget(self._checkin_section)

        layout.addStretch()
        container.setLayout(layout)
        scroll.setWidget(container)
        page_layout = QVBoxLayout()
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)
        page.setLayout(page_layout)
        return page

    # ═══════════════════════════════════════════════════════════
    # 步骤 3：时段配置 (含日历)
    # ═══════════════════════════════════════════════════════════

    def _build_step3(self) -> QWidget:
        p = get_palette()
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 日历可视化选择
        cal_group = QGroupBox("📅 选择活动日期")
        cal_layout = QVBoxLayout()
        cal_layout.setContentsMargins(12, 12, 12, 12)
        self._calendar = QCalendarWidget()
        self._calendar.setGridVisible(True)
        self._calendar.setMinimumHeight(240)
        self._calendar.setMaximumHeight(280)
        cal_layout.addWidget(self._calendar)
        cal_group.setLayout(cal_layout)
        layout.addWidget(cal_group)

        # 快速添加时段
        quick_group = QGroupBox("⏱ 添加时段")
        quick_layout = QVBoxLayout()
        quick_layout.setContentsMargins(12, 12, 12, 12)
        quick_layout.setSpacing(8)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(QLabel("名称"))
        self._slot_name = QLineEdit()
        self._slot_name.setPlaceholderText("如：上午场")
        self._slot_name.setMinimumHeight(36)
        name_row.addWidget(self._slot_name, 1)

        time_row = QHBoxLayout()
        time_row.setSpacing(8)
        self._slot_start = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self._slot_start.setCalendarPopup(True)
        self._slot_start.setDisplayFormat("HH:mm")
        self._slot_start.setMinimumHeight(36)
        self._slot_end = QDateTimeEdit(QDateTime.currentDateTime().addSecs(7200))
        self._slot_end.setCalendarPopup(True)
        self._slot_end.setDisplayFormat("HH:mm")
        self._slot_end.setMinimumHeight(36)
        time_row.addWidget(QLabel("起"))
        time_row.addWidget(self._slot_start, 1)
        time_row.addWidget(QLabel("迄"))
        time_row.addWidget(self._slot_end, 1)

        cap_row = QHBoxLayout()
        cap_row.setSpacing(8)
        cap_row.addWidget(QLabel("容量"))
        self._slot_capacity = QSpinBox()
        self._slot_capacity.setRange(1, 10000)
        self._slot_capacity.setValue(30)
        self._slot_capacity.setMinimumHeight(36)
        cap_row.addWidget(self._slot_capacity)
        cap_row.addStretch()

        quick_layout.addLayout(name_row)
        quick_layout.addLayout(time_row)
        quick_layout.addLayout(cap_row)
        quick_group.setLayout(quick_layout)
        layout.addWidget(quick_group)

        # 提示
        hint = QLabel("💡 创建活动后可在「添加选项」中批量管理时段和岗位")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px; padding: 6px 10px; "
                           f"background: {p.bg_input}; border-radius: 6px;")
        layout.addWidget(hint)

        layout.addStretch()
        page.setLayout(layout)
        return page

    # ═══════════════════════════════════════════════════════════
    # 步骤 4：确认
    # ═══════════════════════════════════════════════════════════

    def _build_step4(self) -> QWidget:
        p = get_palette()
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title = QLabel("确认活动信息")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {p.text_primary};")
        layout.addWidget(title)

        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(
            f"background: {p.bg_input}; border: 1px solid {p.border_light}; "
            f"border-radius: 8px; padding: 16px; color: {p.text_secondary}; line-height: 1.6;"
        )
        layout.addWidget(self._summary)

        layout.addStretch()
        page.setLayout(layout)
        return page

    # ═══════════════════════════════════════════════════════════
    # 导航
    # ═══════════════════════════════════════════════════════════

    def _go_step(self, index: int) -> None:
        self._current_step = index
        self._stack.setCurrentIndex(index)
        self._step_indicator.set_current(index)
        self._prev_btn.setVisible(index > 0)
        is_last = index == self._stack.count() - 1
        self._next_btn.setVisible(not is_last)
        self._create_btn.setVisible(is_last)
        self._save_tpl_btn.setVisible(index >= 2)  # 从规则步骤开始可以保存模板
        self._update_fields_by_mode()
        # 步骤 4 更新摘要
        if is_last:
            self._update_summary()

    def _go_next(self) -> None:
        if self._current_step == 0:
            # 验证创建方式
            self._creation_mode = self._mode_cards.current_data()
            if self._creation_mode == "template":
                tpl_id = self._template_selector.currentData()
                if not tpl_id:
                    set_banner(self._message, "error", "请选择一个模板")
                    return
                self._selected_template = self._tpl_service.get_template(tpl_id)
                if self._selected_template:
                    self._apply_template(self._selected_template)
            elif self._creation_mode == "recurring":
                tpl_id = self._template_selector.currentData()
                if not tpl_id:
                    set_banner(self._message, "error", "周期模式需要选择一个模板")
                    return
                self._selected_template = self._tpl_service.get_template(tpl_id)
                if self._selected_template:
                    self._apply_template(self._selected_template)
        elif self._current_step == 1:
            if not self._name.text().strip():
                set_banner(self._message, "error", "请输入活动名称")
                return
        elif self._current_step == 2:
            if not self._validate_signup_time():
                return

        self._go_step(self._current_step + 1)

    def _go_prev(self) -> None:
        if self._current_step > 0:
            self._go_step(self._current_step - 1)

    def _is_time_slot(self) -> bool:
        return self._activity_type.current_data() == ActivityType.TIME_SLOT

    def _update_fields_by_mode(self) -> None:
        is_ts = self._is_time_slot()
        self._location_label.setVisible(is_ts)
        self._location.setVisible(is_ts)
        self._checkin_section.setVisible(is_ts)

    def _on_mode_changed(self, btn) -> None:
        mode = self._mode_cards.current_data()
        self._template_section.setVisible(mode in ("template", "recurring"))
        self._recurrence_section.setVisible(mode == "recurring")

    def _validate_signup_time(self, *args) -> bool:
        start = self._signup_start.dateTime().toPython()
        end = self._signup_end.dateTime().toPython()
        ok = end > start
        self._signup_err.setVisible(not ok)
        if not ok:
            self._signup_err.setText("⚠ 截止必须晚于开始")
        return ok

    def _on_checkin_sync_toggled(self, checked: bool) -> None:
        if checked:
            self._checkin_start.setDateTime(self._signup_start.dateTime())
            self._checkin_end.setDateTime(self._signup_end.dateTime())
        self._checkin_start.setEnabled(not checked)
        self._checkin_end.setEnabled(not checked)

    # ═══════════════════════════════════════════════════════════
    # 模板
    # ═══════════════════════════════════════════════════════════

    def _load_templates(self) -> None:
        """加载模板列表到选择器。"""
        self._template_selector.clear()
        for tpl in self._tpl_service.list_templates():
            recurrence_label = {
                "once": "一次性",
                "weekly": "每周",
                "monthly": "每月",
                "semester": "学期",
            }.get(tpl.recurrence, "")
            label = f"{tpl.name} ({recurrence_label})"
            self._template_selector.addItem(label, tpl.id)

    def _on_template_selected(self, index: int) -> None:
        """模板选择时显示描述。"""
        if index < 0:
            return
        tpl_id = self._template_selector.currentData()
        if tpl_id:
            tpl = self._tpl_service.get_template(tpl_id)
            if tpl:
                self._tpl_desc.setText(tpl.description)

    def _apply_template(self, tpl: ActivityTemplate) -> None:
        """将模板设置填入表单。"""
        # 基本信息
        self._name.setText(tpl.name)
        self._details.setPlainText(tpl.description)

        # 活动模式
        if tpl.activity_type == ActivityType.NON_TIME_SLOT:
            self._activity_type.set_current_by_data(ActivityType.NON_TIME_SLOT)
        else:
            self._activity_type.set_current_by_data(ActivityType.TIME_SLOT)

        # 报名规则
        try:
            self._signup_mode.set_current_by_data(SignupMode(tpl.signup_mode))
        except ValueError:
            self._signup_mode.set_current_index(0)
        try:
            self._allocation_mode.set_current_by_data(AllocationMode(tpl.allocation_mode))
        except ValueError:
            self._allocation_mode.set_current_index(0)
        try:
            self._checkin_mode.set_current_by_data(CheckInMode(tpl.checkin_mode))
        except ValueError:
            self._checkin_mode.set_current_index(0)

        self._allow_multiple_slots.setChecked(tpl.allow_multiple_slots)

        # 时段预填
        if tpl.slot_templates:
            first = tpl.slot_templates[0]
            self._slot_name.setText(first.get("name", ""))
            self._slot_capacity.setValue(first.get("capacity", 30))

        self._selected_template = tpl

    def _save_as_template(self) -> None:
        """保存当前配置为模板。"""
        name = self._name.text().strip()
        if not name:
            set_banner(self._message, "error", "请先填写活动名称")
            return
        try:
            tpl = self._tpl_service.save_template(
                name=name,
                description=self._details.toPlainText().strip(),
                activity_type=self._activity_type.current_data().value,
                signup_mode=self._signup_mode.current_data().value,
                allocation_mode=self._allocation_mode.current_data().value,
                checkin_mode=self._checkin_mode.current_data().value,
                allow_multiple_slots=self._allow_multiple_slots.isChecked(),
                slot_templates=[
                    {
                        "name": self._slot_name.text().strip() or "时段1",
                        "capacity": self._slot_capacity.value(),
                    }
                ],
                recurrence="once",
            )
            set_banner(self._message, "success", f"模板「{tpl.name}」已保存")
            self._load_templates()
        except Exception as exc:
            set_banner(self._message, "error", f"保存模板失败：{exc}")

    # ═══════════════════════════════════════════════════════════
    # 确认摘要
    # ═══════════════════════════════════════════════════════════

    def _update_summary(self) -> None:
        p = get_palette()
        is_ts = self._is_time_slot()
        mode = "时段模式" if is_ts else "非时段模式"
        alloc_map = {"greedy": "志愿优先", "first_come": "先到先得", "lottery": "抽签", "points": "意愿点"}
        alloc = alloc_map.get(self._allocation_mode.current_data(), "—")
        signup = "实时" if self._signup_mode.current_data() == SignupMode.REALTIME else "非实时"

        lines = [
            f"📌 <b>{self._name.text() or '—'}</b>",
            f"🔧 模式：{mode} · 分配：{alloc} · 名额：{signup}",
            f"📅 报名：{self._signup_start.dateTime().toString('M月d日 HH:mm')} → {self._signup_end.dateTime().toString('M月d日 HH:mm')}",
        ]
        if self._creation_mode == "recurring":
            rec_label = self._recurrence_mode.currentText()
            count = self._recurrence_count.value()
            lines.append(f"🔄 周期：{rec_label} · 共 {count} 期")

        if is_ts:
            lines.append(f"📍 地点：{self._location.text() or '—'}")
            ck_idx = self._checkin_mode.current_index()
            ck_text = self._checkin_mode.card_text(ck_idx) if ck_idx >= 0 else "手动"
            lines.append(f"✅ 签到：{ck_text}")

        if self._slot_name.text().strip():
            lines.append(f"⏱ 初始时段：{self._slot_name.text()} ({self._slot_capacity.value()}人)")
        else:
            lines.append("⏱ 创建后添加时段")

        self._summary.setText("<br>".join(lines))

    # ═══════════════════════════════════════════════════════════
    # 创建
    # ═══════════════════════════════════════════════════════════

    def _create_activity(self) -> None:
        """提交创建（支持新建、模板、周期三种模式）。"""
        name = self._name.text().strip()
        if not name:
            set_banner(self._message, "error", "请输入活动名称")
            self._go_step(1)
            return
        if not self._validate_signup_time():
            set_banner(self._message, "error", "请修正报名时间")
            self._go_step(2)
            return

        try:
            set_banner(self._message, "info", "")
            is_ts = self._is_time_slot()

            # 周期模式
            if self._creation_mode == "recurring" and self._selected_template:
                recurrence = self._recurrence_mode.currentData()
                count = self._recurrence_count.value()
                results = generate_recurring_activities(
                    activity_service=self._service,
                    template_service=self._tpl_service,
                    user=self._user,
                    template_id=self._selected_template.id,
                    base_name=name,
                    first_signup_start=self._signup_start.dateTime().toPython(),
                    count=count,
                    recurrence=recurrence,
                )
                count_created = len(results)
                set_banner(self._message, "success", f"已创建 {count_created} 个周期活动")
                if hasattr(self, "_on_created") and callable(self._on_created):
                    self._on_created()
                # 重置
                self._name.clear()
                self._details.clear()
                self._go_step(0)
                return

            # 新建 / 模板模式
            activity = self._service.create_activity(
                user=self._user,
                name=name,
                signup_start=self._signup_start.dateTime().toPython(),
                signup_end=self._signup_end.dateTime().toPython(),
                details=self._details.toPlainText().strip(),
                signup_mode=SignupMode(self._signup_mode.current_data()),
                allocation_mode=AllocationMode(self._allocation_mode.current_data()),
                location=self._location.text().strip() if is_ts else "",
                activity_type=ActivityType(self._activity_type.current_data()),
                checkin_mode=CheckInMode(self._checkin_mode.current_data()) if is_ts else CheckInMode.MANUAL.value,
                checkin_start=self._checkin_start.dateTime().toPython() if is_ts else None,
                checkin_end=self._checkin_end.dateTime().toPython() if is_ts else None,
                group_id=self._group_selector.currentData(),
                allow_multiple_slots=self._allow_multiple_slots.isChecked(),
            )

            # 自动创建初始时段
            slot_name = self._slot_name.text().strip()
            if slot_name and is_ts:
                try:
                    # 合并日历日期 + 时间
                    cal_date = self._calendar.selectedDate()
                    slot_start = datetime(
                        cal_date.year(), cal_date.month(), cal_date.day(),
                        self._slot_start.time().hour(), self._slot_start.time().minute(),
                        tzinfo=timezone.utc,
                    )
                    slot_end = datetime(
                        cal_date.year(), cal_date.month(), cal_date.day(),
                        self._slot_end.time().hour(), self._slot_end.time().minute(),
                        tzinfo=timezone.utc,
                    )
                    self._service.add_slot(
                        user=self._user,
                        activity_id=activity.id,
                        name=slot_name,
                        start_time=slot_start,
                        end_time=slot_end,
                        capacity=self._slot_capacity.value(),
                    )
                except (ValidationError, PermissionDenied):
                    import logging as _log
                    _log.getLogger(__name__).warning("自动添加初始时段失败，活动已创建", exc_info=True)
                except Exception:
                    import logging as _log
                    _log.getLogger(__name__).exception("自动添加初始时段异常")

            set_banner(self._message, "success", f"活动「{name}」创建成功")
            if hasattr(self, "_on_created") and callable(self._on_created):
                self._on_created()
            # 发射 Signal 通知所有监听者
            self.activity_created.emit()

            self._name.clear()
            self._details.clear()
            self._location.clear()
            self._slot_name.clear()
            self._go_step(0)

        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))
        except Exception as exc:
            set_banner(self._message, "error", f"创建失败：{exc}")

    def set_on_created(self, callback: callable) -> None:
        self._on_created = callback
