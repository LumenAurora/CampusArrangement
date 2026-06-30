"""向导式活动创建面板 — 分步引导、卡片选项、自适应布局。

替代原有的平铺长表单，将活动创建拆分为 3 个递进步骤：
  步骤 1：基本信息（模式、名称、详情、地点）
  步骤 2：报名规则（报名时间、名额显示、分配策略、报名范围、兼报设置）
  步骤 3：时段与岗位配置（时段管理、批量添加、岗位分配）

设计遵循附录规范：
- 右侧活动列表可折叠为窄边栏
- 底部固定操作栏
- 卡片式选项选择器
- 时间默认当前+1h/当前+7天
- 实时校验 + 提交前检查
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QFrame,
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
from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import ActivityType, AllocationMode, CheckInMode, SignupMode, User
from app.ui.style import get_palette
from app.ui.ui_utils import (
    RadioCardGroup,
    StepIndicator,
    StyledComboBox,
    set_banner,
)


class GuidedActivityPanel(QWidget):
    """向导式活动创建面板。

    嵌入 ActivityPanel 左侧区域，取代原有的 QTabWidget 平铺表单。
    与父面板共享 activity_service/user/group_repo 等服务。
    需要通过信号通知父面板刷新活动列表。
    """

    activity_created = None  # Qt Signal 替代 — 由父面板在 __init__ 后连接

    def __init__(
        self,
        activity_service: ActivityService,
        user: User,
        group_repo=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = activity_service
        self._user = user
        self._group_repo = group_repo
        self._current_step = 0
        self._build_ui()

    def _build_ui(self) -> None:
        p = get_palette()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # ── 步骤指示器 ────────────────────────────────────
        self._step_indicator = StepIndicator(
            ["基本信息", "报名规则", "时段岗位"], current=0
        )
        layout.addWidget(self._step_indicator)

        # ── 步骤页面堆栈 ──────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_step1())
        self._stack.addWidget(self._build_step2())
        self._stack.addWidget(self._build_step3())
        layout.addWidget(self._stack, 1)

        # ── 错误提示 ──────────────────────────────────────
        self._message = QLabel("")
        set_banner(self._message, "info", "")
        layout.addWidget(self._message)

        # ── 底部固定导航栏 ────────────────────────────────
        nav_bar = QFrame()
        nav_bar.setStyleSheet(
            f"background: {p.bg_card}; border-top: 1px solid {p.border_light}; "
            f"border-radius: 8px; padding: 8px 0;"
        )
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 4, 0, 4)
        nav_layout.setSpacing(12)

        self._prev_btn = QPushButton("← 上一步")
        self._prev_btn.setObjectName("secondaryButton")
        self._prev_btn.clicked.connect(self._go_prev)
        self._prev_btn.setVisible(False)

        nav_layout.addWidget(self._prev_btn)
        nav_layout.addStretch()

        self._next_btn = QPushButton("下一步 →")
        self._next_btn.setObjectName("primaryButton")
        self._next_btn.clicked.connect(self._go_next)

        self._create_btn = QPushButton("✓ 创建活动")
        self._create_btn.setObjectName("primaryButton")
        self._create_btn.clicked.connect(self._create_activity)
        self._create_btn.setVisible(False)

        nav_layout.addWidget(self._next_btn)
        nav_layout.addWidget(self._create_btn)
        nav_bar.setLayout(nav_layout)
        layout.addWidget(nav_bar)

        self.setLayout(layout)
        # 初始联动：显示/隐藏地点/签到字段
        self._update_fields_by_mode()

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

        # ── 活动模式 卡片选择 ────────────────────────────
        mode_label = QLabel("活动模式")
        mode_label.setStyleSheet(
            f"font-weight: 700; font-size: 13px; color: {p.text_primary}; margin-top: 4px;"
        )
        layout.addWidget(mode_label)

        self._activity_type = RadioCardGroup()
        self._activity_type.add_card(
            "时段模式",
            "适用于排班、志愿填报等需要时间安排的场景，支持签到管理",
            ActivityType.TIME_SLOT,
        )
        self._activity_type.add_card(
            "非时段模式",
            "适用于选课、选题等无需时间安排的场景，仅做名额分配",
            ActivityType.NON_TIME_SLOT,
        )
        self._activity_type.set_current_index(0)
        layout.addWidget(self._activity_type)

        # ── 活动名称 ──────────────────────────────────────
        name_label = QLabel("活动名称 *")
        name_label.setStyleSheet(
            f"font-weight: 700; font-size: 13px; color: {p.text_primary};"
        )
        layout.addWidget(name_label)
        self._name = QLineEdit()
        self._name.setPlaceholderText("例如：志愿服务（图书馆）")
        self._name.setMinimumHeight(40)
        layout.addWidget(self._name)

        # ── 活动详情 ──────────────────────────────────────
        detail_label = QLabel("活动详情")
        detail_label.setStyleSheet(
            f"font-weight: 700; font-size: 13px; color: {p.text_primary};"
        )
        layout.addWidget(detail_label)
        self._details = QTextEdit()
        self._details.setPlaceholderText("简要说明活动内容与要求…")
        self._details.setMaximumHeight(100)
        self._details.setMinimumHeight(72)
        layout.addWidget(self._details)

        # ── 地点（时段模式） ──────────────────────────────
        self._location_label = QLabel("活动地点")
        self._location_label.setStyleSheet(
            f"font-weight: 700; font-size: 13px; color: {p.text_primary};"
        )
        layout.addWidget(self._location_label)
        self._location = QLineEdit()
        self._location.setPlaceholderText("例如：图书馆一楼大厅（坐标可选填，如 39.9042,116.4074）")
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

        # ── 标题样式工厂 ─────────────────────────────────
        def _section_title(text: str) -> QLabel:
            label = QLabel(text)
            label.setStyleSheet(
                f"font-weight: 700; font-size: 13px; color: {p.text_primary}; margin-top: 6px;"
            )
            return label

        # ── 报名时间 ─────────────────────────────────────
        layout.addWidget(_section_title("报名时间"))
        time_row = QHBoxLayout()
        time_row.setSpacing(12)
        now = datetime.now()
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

        # 时间校验提示
        self._signup_err = QLabel("")
        self._signup_err.setStyleSheet(f"color: {p.error_fg}; font-size: 11px; padding: 0 4px;")
        self._signup_err.setVisible(False)
        layout.addWidget(self._signup_err)
        for w in (self._signup_start, self._signup_end):
            w.dateTimeChanged.connect(self._validate_signup_time)

        # ── 名额显示 卡片选择 ────────────────────────────
        layout.addWidget(_section_title("名额显示"))
        self._signup_mode = RadioCardGroup()
        self._signup_mode.add_card(
            "实时显示名额",
            "用户可实时看到剩余名额，先到先得时推荐使用",
            SignupMode.REALTIME,
        )
        self._signup_mode.add_card(
            "非实时显示名额",
            "隐藏实时剩余名额，适用于盲报或抽签场景",
            SignupMode.BLIND,
        )
        self._signup_mode.set_current_index(0)
        layout.addWidget(self._signup_mode)

        # ── 分配策略 卡片选择 ────────────────────────────
        layout.addWidget(_section_title("分配策略"))
        self._allocation_mode = RadioCardGroup()
        self._allocation_mode.add_card(
            "志愿优先（贪心）",
            "按用户志愿顺序优先匹配，额满则顺延至下一志愿",
            AllocationMode.GREEDY,
            tooltip="贪心算法：优先满足高优先级志愿，适合志愿填报场景",
        )
        self._allocation_mode.add_card(
            "先到先得",
            "按报名时间顺序分配，先报名者优先获得名额",
            AllocationMode.FIRST_COME,
        )
        self._allocation_mode.add_card(
            "抽签随机",
            "报名结束后随机分配，公平但不可预测",
            AllocationMode.LOTTERY,
        )
        self._allocation_mode.add_card(
            "意愿点（99点制）",
            "用户可分配意愿点数，高者优先匹配，精细化分配",
            AllocationMode.POINTS,
        )
        self._allocation_mode.set_current_index(0)
        layout.addWidget(self._allocation_mode)

        # ── 兼报设置 ─────────────────────────────────────
        layout.addWidget(_section_title("兼报设置"))
        self._allow_multiple_slots = QCheckBox("允许同一用户兼报多个时段/岗位")
        self._allow_multiple_slots.setToolTip(
            "开启后，同一用户可报名同一活动下的多个时段或岗位"
        )
        layout.addWidget(self._allow_multiple_slots)

        # ── 报名范围 ─────────────────────────────────────
        layout.addWidget(_section_title("报名范围"))
        self._group_selector = StyledComboBox()
        self._group_selector.addItem("公开（全体用户）", None)
        self._group_selector.setMinimumHeight(36)
        if self._group_repo:
            for g in self._group_repo.list_all():
                self._group_selector.addItem(g["name"], g["id"])
        layout.addWidget(self._group_selector)

        # ── 签到模式（时段模式） ───────────────────────────
        self._checkin_section = QWidget()
        checkin_layout = QVBoxLayout()
        checkin_layout.setContentsMargins(0, 0, 0, 0)
        checkin_layout.setSpacing(14)

        checkin_layout.addWidget(_section_title("签到模式"))
        self._checkin_mode = RadioCardGroup()
        self._checkin_mode.add_card("手动签到", "管理员操作签到", CheckInMode.MANUAL)
        self._checkin_mode.add_card("二维码签到", "扫码完成签到", CheckInMode.QRCODE)
        self._checkin_mode.add_card("自助签到码", "用户输入签到码", CheckInMode.SELF_CODE)
        self._checkin_mode.add_card("位置签到", "GPS定位验证", CheckInMode.LOCATION)
        self._checkin_mode.add_card("拍照签到", "上传现场照片", CheckInMode.PHOTO)
        self._checkin_mode.set_current_index(0)
        checkin_layout.addWidget(self._checkin_mode)

        # 签到时间联动
        self._checkin_sync = QCheckBox("签到时间与活动时间同步")
        self._checkin_sync.setChecked(True)
        self._checkin_sync.toggled.connect(self._on_checkin_sync_toggled)
        checkin_layout.addWidget(self._checkin_sync)

        checkin_time_row = QHBoxLayout()
        checkin_time_row.setSpacing(12)
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
        checkin_time_row.addWidget(QLabel("开始"))
        checkin_time_row.addWidget(self._checkin_start)
        checkin_time_row.addWidget(QLabel("截止"))
        checkin_time_row.addWidget(self._checkin_end)
        checkin_layout.addLayout(checkin_time_row)

        self._checkin_err = QLabel("")
        self._checkin_err.setStyleSheet(f"color: {p.error_fg}; font-size: 11px; padding: 0 4px;")
        self._checkin_err.setVisible(False)
        checkin_layout.addWidget(self._checkin_err)
        self._checkin_section.setLayout(checkin_layout)
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
    # 步骤 3：时段与岗位配置
    # ═══════════════════════════════════════════════════════════

    def _build_step3(self) -> QWidget:
        p = get_palette()
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 提示说明
        hint = QLabel("创建活动后，可在活动列表右侧的「选项列表」中配置时段和岗位。\n"
                       "您也可以先创建活动，再逐步添加时段。")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {p.text_tertiary}; font-size: 12px; padding: 8px; "
                           f"background: {p.bg_input}; border-radius: 8px;")
        layout.addWidget(hint)

        # 快速添加单个时段（可选）
        quick_group = QGroupBox("快速添加时段（可选）")
        quick_layout = QVBoxLayout()
        quick_layout.setContentsMargins(12, 12, 12, 12)
        quick_layout.setSpacing(8)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("时段名称"))
        self._slot_name = QLineEdit()
        self._slot_name.setPlaceholderText("例如：周二下午3-6点")
        name_row.addWidget(self._slot_name, 1)

        time_row = QHBoxLayout()
        time_row.setSpacing(8)
        self._slot_start = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self._slot_start.setCalendarPopup(True)
        self._slot_start.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._slot_end = QDateTimeEdit(QDateTime.currentDateTime().addSecs(7200))
        self._slot_end.setCalendarPopup(True)
        self._slot_end.setDisplayFormat("yyyy-MM-dd HH:mm")
        time_row.addWidget(QLabel("开始"))
        time_row.addWidget(self._slot_start)
        time_row.addWidget(QLabel("结束"))
        time_row.addWidget(self._slot_end)

        cap_row = QHBoxLayout()
        cap_row.addWidget(QLabel("容量"))
        self._slot_capacity = QSpinBox()
        self._slot_capacity.setRange(1, 10000)
        self._slot_capacity.setValue(30)
        cap_row.addWidget(self._slot_capacity)
        cap_row.addStretch()

        quick_layout.addLayout(name_row)
        quick_layout.addLayout(time_row)
        quick_layout.addLayout(cap_row)

        quick_group.setLayout(quick_layout)
        layout.addWidget(quick_group)

        layout.addStretch()
        page.setLayout(layout)
        return page

    # ═══════════════════════════════════════════════════════════
    # 导航与联动
    # ═══════════════════════════════════════════════════════════

    def _go_step(self, index: int) -> None:
        self._current_step = index
        self._stack.setCurrentIndex(index)
        self._step_indicator.set_current(index)
        self._prev_btn.setVisible(index > 0)
        is_last = index == self._stack.count() - 1
        self._next_btn.setVisible(not is_last)
        self._create_btn.setVisible(is_last)
        self._update_fields_by_mode()

    def _go_next(self) -> None:
        if self._current_step == 0:
            # 校验基本信息
            if not self._name.text().strip():
                set_banner(self._message, "error", "请输入活动名称")
                return
        elif self._current_step == 1:
            # 校验时间
            if not self._validate_signup_time():
                return
        self._go_step(self._current_step + 1)

    def _go_prev(self) -> None:
        if self._current_step > 0:
            self._go_step(self._current_step - 1)

    def _is_time_slot(self) -> bool:
        data = self._activity_type.current_data()
        return data == ActivityType.TIME_SLOT

    def _update_fields_by_mode(self) -> None:
        """根据活动模式动态显示/隐藏地点和签到字段。"""
        is_ts = self._is_time_slot()
        self._location_label.setVisible(is_ts)
        self._location.setVisible(is_ts)
        self._checkin_section.setVisible(is_ts)

    def _on_checkin_sync_toggled(self, checked: bool) -> None:
        """签到时间与活动时间联动。"""
        if checked:
            # 同步到报名时间
            self._checkin_start.setDateTime(self._signup_start.dateTime())
            self._checkin_end.setDateTime(self._signup_end.dateTime())
        self._checkin_start.setEnabled(not checked)
        self._checkin_end.setEnabled(not checked)

    def _validate_signup_time(self, *args) -> bool:
        """实时校验报名结束时间 > 开始时间。"""
        p = get_palette()
        start = self._signup_start.dateTime().toPython()
        end = self._signup_end.dateTime().toPython()
        ok = end > start
        self._signup_err.setVisible(not ok)
        if not ok:
            self._signup_err.setText("⚠ 报名截止必须晚于报名开始")
        return ok

    # ═══════════════════════════════════════════════════════════
    # 提交
    # ═══════════════════════════════════════════════════════════

    def _create_activity(self) -> None:
        """收集所有步骤数据并创建活动。"""
        name = self._name.text().strip()
        if not name:
            set_banner(self._message, "error", "请输入活动名称")
            self._go_step(0)
            return
        if not self._validate_signup_time():
            set_banner(self._message, "error", "请修正报名时间")
            self._go_step(1)
            return

        try:
            set_banner(self._message, "info", "")
            is_ts = self._is_time_slot()

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
                checkin_mode=self._checkin_mode.current_data() if is_ts else CheckInMode.MANUAL.value,
                checkin_start=self._checkin_start.dateTime().toPython() if is_ts else None,
                checkin_end=self._checkin_end.dateTime().toPython() if is_ts else None,
                group_id=self._group_selector.currentData(),
                allow_multiple_slots=self._allow_multiple_slots.isChecked(),
            )

            # 如果步骤3填写了时段名称，自动创建一个初始时段
            slot_name = self._slot_name.text().strip()
            if slot_name and is_ts:
                try:
                    self._service.add_slot(
                        user=self._user,
                        activity_id=activity.id,
                        name=slot_name,
                        start_time=self._slot_start.dateTime().toPython(),
                        end_time=self._slot_end.dateTime().toPython(),
                        capacity=self._slot_capacity.value(),
                    )
                except Exception:
                    pass  # 时段添加失败不影响活动创建

            set_banner(self._message, "success", f"活动「{name}」创建成功")
            # 通知父面板刷新
            if hasattr(self, "_on_created") and callable(self._on_created):
                self._on_created()

            # 重置表单
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
        """设置创建成功后的回调（由父面板调用刷新列表）。"""
        self._on_created = callback
