from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.activity_service import ActivityService
from app.application.checkin_service import CheckInService
from app.domain.exceptions import ConflictError, ValidationError
from app.domain.models import ActivityStatus, CheckInMode, User
from app.infrastructure.repositories import ScheduleRepository
from app.ui.style import get_palette
from app.ui.ui_utils import configure_table, format_datetime, format_slot_name, make_page_header, set_banner, set_table_empty

# 支持自助签到的签到模式
_SELF_CHECKIN_MODES = {CheckInMode.SELF_CODE, CheckInMode.QRCODE, CheckInMode.LOCATION, CheckInMode.PHOTO}

_CHECKIN_MODE_LABELS = {
    CheckInMode.SELF_CODE: "自助签到码",
    CheckInMode.QRCODE: "扫码签到",
    CheckInMode.LOCATION: "位置签到",
    CheckInMode.PHOTO: "拍照签到",
}

_CHECKIN_HINTS = {
    CheckInMode.SELF_CODE: "请输入签到码完成签到",
    CheckInMode.QRCODE: "请输入扫码获取的签到码完成签到",
    CheckInMode.LOCATION: "请获取位置后签到",
    CheckInMode.PHOTO: "请选择照片后签到",
}


def _make_info_field(label: str, value: str) -> tuple[QLabel, QLabel]:
    """Create a (label, value) pair for the activity info card."""
    p = get_palette()
    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {p.text_secondary}; font-weight: 600; font-size: 12px;")
    val = QLabel(value)
    val.setWordWrap(True)
    val.setStyleSheet(f"color: {p.text_primary}; font-size: 13px;")
    return lbl, val


def _make_checkin_status_item(status_raw: str) -> QTableWidgetItem:
    """Create a table item with colored indicator for checkin status."""
    p = get_palette()
    if status_raw == "checked_in":
        text = "● 已签到"
        fg, bg = p.success_fg, p.success_bg
    elif status_raw == "absent":
        text = "● 缺勤"
        fg, bg = p.error_fg, p.error_bg
    else:
        text = "● 未签到"
        fg, bg = p.text_tertiary, p.bg_sidebar
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignCenter)
    item.setForeground(QBrush(QColor(fg)))
    item.setBackground(QBrush(QColor(bg)))
    return item


class SelfCheckInPanel(QWidget):
    def __init__(
        self,
        checkin_service: CheckInService,
        activity_service: ActivityService,
        schedule_repo: ScheduleRepository,
        user: User,
    ) -> None:
        super().__init__()
        self._checkin_service = checkin_service
        self._activity_service = activity_service
        self._schedule_repo = schedule_repo
        self._user = user

        # 当前选中活动的签到模式（缓存）
        self._current_checkin_mode: CheckInMode | None = None

        # 位置签到数据
        self._latitude: float | None = None
        self._longitude: float | None = None

        # 拍照签到数据
        self._photo_path: str = ""

        # ---- 活动选择器 ----
        self._activity_selector = QComboBox()
        self._activity_selector.setMinimumWidth(220)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self._load_my_slots)

        selector_layout = QHBoxLayout()
        selector_layout.setSpacing(12)
        selector_layout.addWidget(QLabel("活动"))
        selector_layout.addWidget(self._activity_selector, 1)
        selector_layout.addWidget(refresh_btn)

        # ---- 活动信息卡片 ----
        self._info_card = QFrame()
        self._info_card.setObjectName("statCard")
        self._info_card.setProperty("accentColor", "accent")
        self._info_layout = QGridLayout()
        self._info_layout.setContentsMargins(16, 12, 16, 12)
        self._info_layout.setSpacing(8)
        self._info_layout.setColumnStretch(1, 1)
        self._info_layout.setColumnStretch(3, 1)
        self._info_card.setLayout(self._info_layout)

        self._info_name_val = QLabel("—")
        self._info_location_val = QLabel("—")
        self._info_mode_val = QLabel("—")
        self._info_time_val = QLabel("—")
        self._refresh_info_card()

        # ---- 签到说明 ----
        self._hint_label = QLabel("")
        p = get_palette()
        self._hint_label.setStyleSheet(
            f"background: {p.accent_soft}; color: {p.accent}; "
            f"border-radius: 8px; padding: 8px 14px; font-weight: 500;"
        )

        # ---- 签到码输入页 ----
        self._checkin_code_input = QLineEdit()
        self._checkin_code_input.setPlaceholderText("输入签到码")
        self._checkin_code_input.setMaxLength(8)

        code_page = QWidget()
        code_layout = QHBoxLayout(code_page)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.setSpacing(12)
        code_layout.addWidget(QLabel("签到码"))
        code_layout.addWidget(self._checkin_code_input, 1)

        # ---- 位置签到页 ----
        self._location_label = QLabel("尚未获取位置")
        self._get_location_btn = QPushButton("获取位置")
        self._get_location_btn.setObjectName("secondaryButton")
        self._get_location_btn.clicked.connect(self._fetch_location)

        location_page = QWidget()
        location_layout = QHBoxLayout(location_page)
        location_layout.setContentsMargins(0, 0, 0, 0)
        location_layout.setSpacing(12)
        location_layout.addWidget(self._get_location_btn)
        location_layout.addWidget(self._location_label, 1)

        # ---- 拍照签到页 ----
        self._photo_label = QLabel("尚未选择照片")
        self._choose_photo_btn = QPushButton("选择图片")
        self._choose_photo_btn.setObjectName("secondaryButton")
        self._choose_photo_btn.clicked.connect(self._choose_photo)

        photo_page = QWidget()
        photo_layout = QHBoxLayout(photo_page)
        photo_layout.setContentsMargins(0, 0, 0, 0)
        photo_layout.setSpacing(12)
        photo_layout.addWidget(self._choose_photo_btn)
        photo_layout.addWidget(self._photo_label, 1)

        # ---- 堆叠签到方式 ----
        self._checkin_stack = QStackedWidget()
        self._checkin_stack.addWidget(code_page)    # index 0: 签到码
        self._checkin_stack.addWidget(location_page) # index 1: 位置
        self._checkin_stack.addWidget(photo_page)    # index 2: 拍照

        self._message = QLabel("")
        set_banner(self._message, "info", "")

        checkin_btn = QPushButton("签到")
        checkin_btn.setObjectName("primaryButton")
        checkin_btn.clicked.connect(self._self_check_in)

        form_layout = QHBoxLayout()
        form_layout.setSpacing(12)
        form_layout.addWidget(self._checkin_stack, 1)
        form_layout.addWidget(checkin_btn)

        # ---- 时段表 ----
        self._slot_table = QTableWidget(0, 5)
        self._slot_table.setHorizontalHeaderLabels(["时段", "地点", "签到状态", "slot_id", "activity_id"])
        configure_table(self._slot_table)

        # ---- 整体布局：顶部活动选择+信息 → 中部签到操作 → 底部时段表 ----
        group = QGroupBox("自助签到")
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(12, 12, 12, 12)
        group_layout.setSpacing(12)
        group_layout.addLayout(selector_layout)
        group_layout.addWidget(self._info_card)
        group_layout.addWidget(self._hint_label)
        group_layout.addLayout(form_layout)
        group_layout.addWidget(self._message)
        group_layout.addWidget(self._slot_table, 1)
        group.setLayout(group_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(make_page_header("签到", "完成自助签到"))
        layout.addWidget(group, 1)
        self.setLayout(layout)

        self._activity_selector.currentIndexChanged.connect(self._on_activity_changed)
        self.refresh()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        activities = self._activity_service.list_activities()
        self._activity_selector.blockSignals(True)
        self._activity_selector.clear()
        # 只显示已关闭或已归档且支持自助签到的活动（签到仅在排班完成后可用）
        allowed_statuses = {ActivityStatus.CLOSED.value, ActivityStatus.ARCHIVED.value}
        for activity in activities:
            if activity.get("status") not in allowed_statuses:
                continue
            mode = activity.get("checkin_mode", "manual")
            try:
                mode_enum = CheckInMode(mode)
            except ValueError:
                continue
            if mode_enum not in _SELF_CHECKIN_MODES:
                continue
            self._activity_selector.addItem(activity["name"], activity["id"])
        self._activity_selector.blockSignals(False)
        self._on_activity_changed()

    # ------------------------------------------------------------------
    # 活动信息卡片
    # ------------------------------------------------------------------

    def _refresh_info_card(self, activity: dict | None = None) -> None:
        """Update the activity info card with the given activity data."""
        # Clear existing widgets from the grid layout
        while self._info_layout.count():
            item = self._info_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not activity:
            p = get_palette()
            placeholder = QLabel("请选择活动以查看详情")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet(f"color: {p.text_tertiary}; font-size: 13px;")
            self._info_layout.addWidget(placeholder, 0, 0, 1, 4)
            return

        # Row 0: 活动名称 + 签到模式
        name_lbl, name_val = _make_info_field("活动名称", activity.get("name", "—"))
        mode_str = activity.get("checkin_mode", "manual")
        try:
            mode_label = _CHECKIN_MODE_LABELS.get(CheckInMode(mode_str), mode_str)
        except ValueError:
            mode_label = mode_str
        mode_lbl, mode_val = _make_info_field("签到模式", mode_label)
        self._info_layout.addWidget(name_lbl, 0, 0)
        self._info_layout.addWidget(name_val, 0, 1)
        self._info_layout.addWidget(mode_lbl, 0, 2)
        self._info_layout.addWidget(mode_val, 0, 3)

        # Row 1: 地点 + 签到时间
        loc_lbl, loc_val = _make_info_field("地点", activity.get("location") or "—")
        checkin_start = activity.get("checkin_start")
        checkin_end = activity.get("checkin_end")
        if checkin_start and checkin_end:
            time_text = f"{format_datetime(checkin_start)} ~ {format_datetime(checkin_end)}"
        elif checkin_start:
            time_text = f"{format_datetime(checkin_start)} 起"
        else:
            time_text = "不限"
        time_lbl, time_val = _make_info_field("签到时间", time_text)
        self._info_layout.addWidget(loc_lbl, 1, 0)
        self._info_layout.addWidget(loc_val, 1, 1)
        self._info_layout.addWidget(time_lbl, 1, 2)
        self._info_layout.addWidget(time_val, 1, 3)

    # ------------------------------------------------------------------
    # 活动切换
    # ------------------------------------------------------------------

    def _on_activity_changed(self) -> None:
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            self._current_checkin_mode = None
            self._checkin_stack.setCurrentIndex(0)
            self._refresh_info_card(None)
            self._hint_label.setText("")
            self._hint_label.setVisible(False)
            self._load_my_slots()
            return

        activity = self._activity_service.get_activity(activity_id)
        if activity:
            mode_str = activity.get("checkin_mode", "manual")
            try:
                self._current_checkin_mode = CheckInMode(mode_str)
            except ValueError:
                self._current_checkin_mode = None
        else:
            self._current_checkin_mode = None

        self._refresh_info_card(activity)
        self._update_hint()
        self._switch_checkin_ui()
        self._load_my_slots()

    def _update_hint(self) -> None:
        """Update the checkin hint label based on current mode."""
        mode = self._current_checkin_mode
        if mode and mode in _CHECKIN_HINTS:
            self._hint_label.setText(_CHECKIN_HINTS[mode])
            self._hint_label.setVisible(True)
            # Re-apply stylesheet to pick up current palette
            p = get_palette()
            self._hint_label.setStyleSheet(
                f"background: {p.accent_soft}; color: {p.accent}; "
                f"border-radius: 8px; padding: 8px 14px; font-weight: 500;"
            )
        else:
            self._hint_label.setText("")
            self._hint_label.setVisible(False)

    def _switch_checkin_ui(self) -> None:
        """根据当前活动的签到模式切换签到方式 UI"""
        mode = self._current_checkin_mode
        if mode in (CheckInMode.SELF_CODE, CheckInMode.QRCODE):
            self._checkin_stack.setCurrentIndex(0)
        elif mode == CheckInMode.LOCATION:
            self._checkin_stack.setCurrentIndex(1)
            self._latitude = None
            self._longitude = None
            self._location_label.setText("尚未获取位置")
        elif mode == CheckInMode.PHOTO:
            self._checkin_stack.setCurrentIndex(2)
            self._photo_path = ""
            self._photo_label.setText("尚未选择照片")
        else:
            self._checkin_stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # 位置签到辅助
    # ------------------------------------------------------------------

    def _fetch_location(self) -> None:
        """获取当前位置（模拟）"""
        # 桌面端无法直接获取 GPS，此处使用模拟坐标
        # 实际项目中可集成系统定位 API 或让用户手动输入
        self._latitude = 39.9042
        self._longitude = 116.4074
        self._location_label.setText(f"已获取位置: {self._latitude:.4f}, {self._longitude:.4f}")

    # ------------------------------------------------------------------
    # 拍照签到辅助
    # ------------------------------------------------------------------

    def _choose_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择签到照片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self._photo_path = path
            self._photo_label.setText(path)

    # ------------------------------------------------------------------
    # 加载时段表
    # ------------------------------------------------------------------

    def _load_my_slots(self) -> None:
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            set_table_empty(self._slot_table, 5, "请选择活动")
            return

        # Get activity for location info
        activity = self._activity_service.get_activity(activity_id)
        activity_location = activity.get("location", "") if activity else ""

        # Get my schedule results for this activity
        my_results = self._schedule_repo.list_by_user(self._user.id)
        activity_results = [r for r in my_results if r["activity_id"] == activity_id]

        if not activity_results:
            set_table_empty(self._slot_table, 5, "您未在此活动中被分配时段")
            return

        # Get slot info
        slots = self._activity_service.list_slots(activity_id)
        slot_map = {slot["id"]: slot for slot in slots}

        # Get checkin status
        checkins = self._checkin_service.list_by_user(self._user.id)
        checkin_map = {ci["slot_id"]: ci["status"] for ci in checkins}

        self._slot_table.clearSpans()
        self._slot_table.setRowCount(len(activity_results))
        for row_index, result in enumerate(activity_results):
            slot = slot_map.get(result["slot_id"])
            slot_label = format_slot_name(slot) if slot else result["slot_id"]
            self._slot_table.setItem(row_index, 0, QTableWidgetItem(slot_label))

            # 地点列
            self._slot_table.setItem(row_index, 1, QTableWidgetItem(activity_location or "—"))

            # 签到状态（带颜色指示）
            status_raw = checkin_map.get(result["slot_id"], "")
            self._slot_table.setItem(row_index, 2, _make_checkin_status_item(status_raw))

            self._slot_table.setItem(row_index, 3, QTableWidgetItem(result["slot_id"]))
            self._slot_table.setItem(row_index, 4, QTableWidgetItem(activity_id))

        self._slot_table.setColumnHidden(3, True)
        self._slot_table.setColumnHidden(4, True)

    # ------------------------------------------------------------------
    # 签到执行
    # ------------------------------------------------------------------

    def _self_check_in(self) -> None:
        try:
            set_banner(self._message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                set_banner(self._message, "error", "请选择活动")
                return

            # 必须选择具体时段
            current_row = self._slot_table.currentRow()
            if current_row < 0:
                set_banner(self._message, "error", "请先选择要签到的时段")
                return
            slot_id_item = self._slot_table.item(current_row, 3)
            if not slot_id_item:
                set_banner(self._message, "error", "数据异常")
                return
            slot_id = slot_id_item.text()

            mode = self._current_checkin_mode

            if mode in (CheckInMode.SELF_CODE, CheckInMode.QRCODE):
                self._do_code_checkin(activity_id, slot_id)
            elif mode == CheckInMode.LOCATION:
                self._do_location_checkin(activity_id, slot_id)
            elif mode == CheckInMode.PHOTO:
                self._do_photo_checkin(activity_id, slot_id)
            else:
                set_banner(self._message, "error", "该活动不支持自助签到")

        except (ConflictError, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))

    def _do_code_checkin(self, activity_id: str, slot_id: str) -> None:
        checkin_code = self._checkin_code_input.text().strip().upper()
        if not checkin_code:
            set_banner(self._message, "error", "请输入签到码")
            return

        if hasattr(self._checkin_service, 'self_check_in'):
            self._checkin_service.self_check_in(
                user_id=self._user.id,
                activity_id=activity_id,
                slot_id=slot_id,
                checkin_code=checkin_code,
            )
        else:
            set_banner(self._message, "error", "自助签到功能不可用")
            return

        set_banner(self._message, "success", "签到成功")
        self._checkin_code_input.clear()
        self._load_my_slots()

    def _do_location_checkin(self, activity_id: str, slot_id: str) -> None:
        if self._latitude is None or self._longitude is None:
            set_banner(self._message, "error", "请先获取位置")
            return

        if hasattr(self._checkin_service, 'location_check_in'):
            self._checkin_service.location_check_in(
                user_id=self._user.id,
                activity_id=activity_id,
                slot_id=slot_id,
                latitude=self._latitude,
                longitude=self._longitude,
            )
        else:
            set_banner(self._message, "error", "位置签到功能不可用")
            return

        set_banner(self._message, "success", "签到成功")
        self._latitude = None
        self._longitude = None
        self._location_label.setText("尚未获取位置")
        self._load_my_slots()

    def _do_photo_checkin(self, activity_id: str, slot_id: str) -> None:
        if not self._photo_path:
            set_banner(self._message, "error", "请先选择照片")
            return

        if hasattr(self._checkin_service, 'photo_check_in'):
            self._checkin_service.photo_check_in(
                user_id=self._user.id,
                activity_id=activity_id,
                slot_id=slot_id,
                photo_path=self._photo_path,
            )
        else:
            set_banner(self._message, "error", "拍照签到功能不可用")
            return

        set_banner(self._message, "success", "签到成功")
        self._photo_path = ""
        self._photo_label.setText("尚未选择照片")
        self._load_my_slots()
