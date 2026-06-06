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

# 鏀寔鑷姪绛惧埌鐨勭鍒版ā寮?_SELF_CHECKIN_MODES = {CheckInMode.SELF_CODE, CheckInMode.QRCODE, CheckInMode.LOCATION, CheckInMode.PHOTO}

_CHECKIN_MODE_LABELS = {
    CheckInMode.SELF_CODE: "鑷姪绛惧埌鐮?,
    CheckInMode.QRCODE: "鎵爜绛惧埌",
    CheckInMode.LOCATION: "浣嶇疆绛惧埌",
    CheckInMode.PHOTO: "鎷嶇収绛惧埌",
}

_CHECKIN_HINTS = {
    CheckInMode.SELF_CODE: "璇疯緭鍏ョ鍒扮爜瀹屾垚绛惧埌",
    CheckInMode.QRCODE: "璇疯緭鍏ユ壂鐮佽幏鍙栫殑绛惧埌鐮佸畬鎴愮鍒?,
    CheckInMode.LOCATION: "璇疯幏鍙栦綅缃悗绛惧埌",
    CheckInMode.PHOTO: "璇烽€夋嫨鐓х墖鍚庣鍒?,
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
        text = "鈼?宸茬鍒?
        fg, bg = p.success_fg, p.success_bg
    elif status_raw == "absent":
        text = "鈼?缂哄嫟"
        fg, bg = p.error_fg, p.error_bg
    else:
        text = "鈼?鏈鍒?
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

        # 褰撳墠閫変腑娲诲姩鐨勭鍒版ā寮忥紙缂撳瓨锛?        self._current_checkin_mode: CheckInMode | None = None

        # 浣嶇疆绛惧埌鏁版嵁
        self._latitude: float | None = None
        self._longitude: float | None = None

        # 鎷嶇収绛惧埌鏁版嵁
        self._photo_path: str = ""

        # ---- 娲诲姩閫夋嫨鍣?----
        self._activity_selector = QComboBox()
        self._activity_selector.setMinimumWidth(220)

        refresh_btn = QPushButton("鍒锋柊")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self._load_my_slots)

        selector_layout = QHBoxLayout()
        selector_layout.setSpacing(12)
        selector_layout.addWidget(QLabel("娲诲姩"))
        selector_layout.addWidget(self._activity_selector, 1)
        selector_layout.addWidget(refresh_btn)

        # ---- 娲诲姩淇℃伅鍗＄墖 ----
        self._info_card = QFrame()
        self._info_card.setObjectName("statCard")
        self._info_card.setProperty("accentColor", "accent")
        self._info_layout = QGridLayout()
        self._info_layout.setContentsMargins(16, 12, 16, 12)
        self._info_layout.setSpacing(8)
        self._info_layout.setColumnStretch(1, 1)
        self._info_layout.setColumnStretch(3, 1)
        self._info_card.setLayout(self._info_layout)

        self._info_name_val = QLabel("鈥?)
        self._info_location_val = QLabel("鈥?)
        self._info_mode_val = QLabel("鈥?)
        self._info_time_val = QLabel("鈥?)
        self._refresh_info_card()

        # ---- 绛惧埌璇存槑 ----
        self._hint_label = QLabel("")
        p = get_palette()
        self._hint_label.setStyleSheet(
            f"background: {p.accent_soft}; color: {p.accent}; "
            f"border-radius: 8px; padding: 8px 14px; font-weight: 500;"
        )

        # ---- 绛惧埌鐮佽緭鍏ラ〉 ----
        self._checkin_code_input = QLineEdit()
        self._checkin_code_input.setPlaceholderText("杈撳叆绛惧埌鐮?)
        self._checkin_code_input.setMaxLength(8)

        code_page = QWidget()
        code_layout = QHBoxLayout(code_page)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.setSpacing(12)
        code_layout.addWidget(QLabel("绛惧埌鐮?))
        code_layout.addWidget(self._checkin_code_input, 1)

        # ---- 浣嶇疆绛惧埌椤?----
        self._location_label = QLabel("灏氭湭鑾峰彇浣嶇疆")
        self._get_location_btn = QPushButton("鑾峰彇浣嶇疆")
        self._get_location_btn.setObjectName("secondaryButton")
        self._get_location_btn.clicked.connect(self._fetch_location)

        location_page = QWidget()
        location_layout = QHBoxLayout(location_page)
        location_layout.setContentsMargins(0, 0, 0, 0)
        location_layout.setSpacing(12)
        location_layout.addWidget(self._get_location_btn)
        location_layout.addWidget(self._location_label, 1)

        # ---- 鎷嶇収绛惧埌椤?----
        self._photo_label = QLabel("灏氭湭閫夋嫨鐓х墖")
        self._choose_photo_btn = QPushButton("閫夋嫨鍥剧墖")
        self._choose_photo_btn.setObjectName("secondaryButton")
        self._choose_photo_btn.clicked.connect(self._choose_photo)

        photo_page = QWidget()
        photo_layout = QHBoxLayout(photo_page)
        photo_layout.setContentsMargins(0, 0, 0, 0)
        photo_layout.setSpacing(12)
        photo_layout.addWidget(self._choose_photo_btn)
        photo_layout.addWidget(self._photo_label, 1)

        # ---- 鍫嗗彔绛惧埌鏂瑰紡 ----
        self._checkin_stack = QStackedWidget()
        self._checkin_stack.addWidget(code_page)    # index 0: 绛惧埌鐮?        self._checkin_stack.addWidget(location_page) # index 1: 浣嶇疆
        self._checkin_stack.addWidget(photo_page)    # index 2: 鎷嶇収

        self._message = QLabel("")
        set_banner(self._message, "info", "")

        checkin_btn = QPushButton("绛惧埌")
        checkin_btn.setObjectName("primaryButton")
        checkin_btn.clicked.connect(self._self_check_in)

        form_layout = QHBoxLayout()
        form_layout.setSpacing(12)
        form_layout.addWidget(self._checkin_stack, 1)
        form_layout.addWidget(checkin_btn)

        # ---- 鏃舵琛?----
        self._slot_table = QTableWidget(0, 5)
        self._slot_table.setHorizontalHeaderLabels(["鏃舵", "鍦扮偣", "绛惧埌鐘舵€?, "slot_id", "activity_id"])
        configure_table(self._slot_table)

        # ---- 鏁翠綋甯冨眬锛氶《閮ㄦ椿鍔ㄩ€夋嫨+淇℃伅 鈫?涓儴绛惧埌鎿嶄綔 鈫?搴曢儴鏃舵琛?----
        group = QGroupBox("鑷姪绛惧埌")
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
        layout.addWidget(make_page_header("绛惧埌", "瀹屾垚鑷姪绛惧埌"))
        layout.addWidget(group, 1)
        self.setLayout(layout)

        self._activity_selector.currentIndexChanged.connect(self._on_activity_changed)
        self.refresh()

    # ------------------------------------------------------------------
    # 鍏紑鎺ュ彛
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        activities = self._activity_service.list_activities()
        self._activity_selector.blockSignals(True)
        self._activity_selector.clear()
        # 鍙樉绀哄凡鍏抽棴鎴栧凡褰掓。涓旀敮鎸佽嚜鍔╃鍒扮殑娲诲姩锛堢鍒颁粎鍦ㄦ帓鐝畬鎴愬悗鍙敤锛?        allowed_statuses = {ActivityStatus.CLOSED.value, ActivityStatus.ARCHIVED.value}
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
    # 娲诲姩淇℃伅鍗＄墖
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
            placeholder = QLabel("璇烽€夋嫨娲诲姩浠ユ煡鐪嬭鎯?)
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet(f"color: {p.text_tertiary}; font-size: 13px;")
            self._info_layout.addWidget(placeholder, 0, 0, 1, 4)
            return

        # Row 0: 娲诲姩鍚嶇О + 绛惧埌妯″紡
        name_lbl, name_val = _make_info_field("娲诲姩鍚嶇О", activity.get("name", "鈥?))
        mode_str = activity.get("checkin_mode", "manual")
        try:
            mode_label = _CHECKIN_MODE_LABELS.get(CheckInMode(mode_str), mode_str)
        except ValueError:
            mode_label = mode_str
        mode_lbl, mode_val = _make_info_field("绛惧埌妯″紡", mode_label)
        self._info_layout.addWidget(name_lbl, 0, 0)
        self._info_layout.addWidget(name_val, 0, 1)
        self._info_layout.addWidget(mode_lbl, 0, 2)
        self._info_layout.addWidget(mode_val, 0, 3)

        # Row 1: 鍦扮偣 + 绛惧埌鏃堕棿
        loc_lbl, loc_val = _make_info_field("鍦扮偣", activity.get("location") or "鈥?)
        checkin_start = activity.get("checkin_start")
        checkin_end = activity.get("checkin_end")
        if checkin_start and checkin_end:
            time_text = f"{format_datetime(checkin_start)} ~ {format_datetime(checkin_end)}"
        elif checkin_start:
            time_text = f"{format_datetime(checkin_start)} 璧?
        else:
            time_text = "涓嶉檺"
        time_lbl, time_val = _make_info_field("绛惧埌鏃堕棿", time_text)
        self._info_layout.addWidget(loc_lbl, 1, 0)
        self._info_layout.addWidget(loc_val, 1, 1)
        self._info_layout.addWidget(time_lbl, 1, 2)
        self._info_layout.addWidget(time_val, 1, 3)

    # ------------------------------------------------------------------
    # 娲诲姩鍒囨崲
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
        """鏍规嵁褰撳墠娲诲姩鐨勭鍒版ā寮忓垏鎹㈢鍒版柟寮?UI"""
        mode = self._current_checkin_mode
        if mode in (CheckInMode.SELF_CODE, CheckInMode.QRCODE):
            self._checkin_stack.setCurrentIndex(0)
        elif mode == CheckInMode.LOCATION:
            self._checkin_stack.setCurrentIndex(1)
            self._latitude = None
            self._longitude = None
            self._location_label.setText("灏氭湭鑾峰彇浣嶇疆")
        elif mode == CheckInMode.PHOTO:
            self._checkin_stack.setCurrentIndex(2)
            self._photo_path = ""
            self._photo_label.setText("灏氭湭閫夋嫨鐓х墖")
        else:
            self._checkin_stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # 浣嶇疆绛惧埌杈呭姪
    # ------------------------------------------------------------------

    def _fetch_location(self) -> None:
        """鑾峰彇褰撳墠浣嶇疆锛堟ā鎷燂級"""
        # 妗岄潰绔棤娉曠洿鎺ヨ幏鍙?GPS锛屾澶勪娇鐢ㄦā鎷熷潗鏍?        # 瀹為檯椤圭洰涓彲闆嗘垚绯荤粺瀹氫綅 API 鎴栬鐢ㄦ埛鎵嬪姩杈撳叆
        self._latitude = 39.9042
        self._longitude = 116.4074
        self._location_label.setText(f"宸茶幏鍙栦綅缃? {self._latitude:.4f}, {self._longitude:.4f}")

    # ------------------------------------------------------------------
    # 鎷嶇収绛惧埌杈呭姪
    # ------------------------------------------------------------------

    def _choose_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "閫夋嫨绛惧埌鐓х墖", "", "鍥剧墖鏂囦欢 (*.png *.jpg *.jpeg *.bmp)"
        )
        if path:
            self._photo_path = path
            self._photo_label.setText(path)

    # ------------------------------------------------------------------
    # 鍔犺浇鏃舵琛?    # ------------------------------------------------------------------

    def _load_my_slots(self) -> None:
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            set_table_empty(self._slot_table, 5, "璇烽€夋嫨娲诲姩")
            return

        # Get activity for location info
        activity = self._activity_service.get_activity(activity_id)
        activity_location = activity.get("location", "") if activity else ""

        # Get my schedule results for this activity
        my_results = self._schedule_repo.list_by_user(self._user.id)
        activity_results = [r for r in my_results if r["activity_id"] == activity_id]

        if not activity_results:
            set_table_empty(self._slot_table, 5, "鎮ㄦ湭鍦ㄦ娲诲姩涓鍒嗛厤鏃舵")
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

            # 鍦扮偣鍒?            self._slot_table.setItem(row_index, 1, QTableWidgetItem(activity_location or "鈥?))

            # 绛惧埌鐘舵€侊紙甯﹂鑹叉寚绀猴級
            status_raw = checkin_map.get(result["slot_id"], "")
            self._slot_table.setItem(row_index, 2, _make_checkin_status_item(status_raw))

            self._slot_table.setItem(row_index, 3, QTableWidgetItem(result["slot_id"]))
            self._slot_table.setItem(row_index, 4, QTableWidgetItem(activity_id))

        self._slot_table.setColumnHidden(3, True)
        self._slot_table.setColumnHidden(4, True)

    # ------------------------------------------------------------------
    # 绛惧埌鎵ц
    # ------------------------------------------------------------------

    def _self_check_in(self) -> None:
        try:
            set_banner(self._message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                set_banner(self._message, "error", "璇烽€夋嫨娲诲姩")
                return

            # 蹇呴』閫夋嫨鍏蜂綋鏃舵
            current_row = self._slot_table.currentRow()
            if current_row < 0:
                set_banner(self._message, "error", "璇峰厛閫夋嫨瑕佺鍒扮殑鏃舵")
                return
            slot_id_item = self._slot_table.item(current_row, 3)
            if not slot_id_item:
                set_banner(self._message, "error", "鏁版嵁寮傚父")
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
                set_banner(self._message, "error", "璇ユ椿鍔ㄤ笉鏀寔鑷姪绛惧埌")

        except (ConflictError, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))

    def _do_code_checkin(self, activity_id: str, slot_id: str) -> None:
        checkin_code = self._checkin_code_input.text().strip().upper()
        if not checkin_code:
            set_banner(self._message, "error", "璇疯緭鍏ョ鍒扮爜")
            return

        if hasattr(self._checkin_service, 'self_check_in'):
            self._checkin_service.self_check_in(
                user_id=self._user.id,
                activity_id=activity_id,
                slot_id=slot_id,
                checkin_code=checkin_code,
            )
        else:
            set_banner(self._message, "error", "鑷姪绛惧埌鍔熻兘涓嶅彲鐢?)
            return

        set_banner(self._message, "success", "绛惧埌鎴愬姛")
        self._checkin_code_input.clear()
        self._load_my_slots()

    def _do_location_checkin(self, activity_id: str, slot_id: str) -> None:
        if self._latitude is None or self._longitude is None:
            set_banner(self._message, "error", "璇峰厛鑾峰彇浣嶇疆")
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
            set_banner(self._message, "error", "浣嶇疆绛惧埌鍔熻兘涓嶅彲鐢?)
            return

        set_banner(self._message, "success", "绛惧埌鎴愬姛")
        self._latitude = None
        self._longitude = None
        self._location_label.setText("灏氭湭鑾峰彇浣嶇疆")
        self._load_my_slots()

    def _do_photo_checkin(self, activity_id: str, slot_id: str) -> None:
        if not self._photo_path:
            set_banner(self._message, "error", "璇峰厛閫夋嫨鐓х墖")
            return

        if hasattr(self._checkin_service, 'photo_check_in'):
            self._checkin_service.photo_check_in(
                user_id=self._user.id,
                activity_id=activity_id,
                slot_id=slot_id,
                photo_path=self._photo_path,
            )
        else:
            set_banner(self._message, "error", "鎷嶇収绛惧埌鍔熻兘涓嶅彲鐢?)
            return

        set_banner(self._message, "success", "绛惧埌鎴愬姛")
        self._photo_path = ""
        self._photo_label.setText("灏氭湭閫夋嫨鐓х墖")
        self._load_my_slots()
