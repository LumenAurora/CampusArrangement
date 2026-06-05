from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.activity_service import ActivityService
from app.application.checkin_service import CheckInService
from app.domain.exceptions import ConflictError, PermissionDenied, ValidationError
from app.domain.models import ActivityStatus, CheckInMode, User
from app.infrastructure.repositories import ScheduleRepository, UserRepository
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, set_banner, set_table_empty, format_status


class CheckInPanel(QWidget):
    def __init__(
        self,
        checkin_service: CheckInService,
        activity_service: ActivityService,
        schedule_repo: ScheduleRepository,
        user_repo: UserRepository,
        user: User,
    ) -> None:
        super().__init__()
        self._checkin_service = checkin_service
        self._activity_service = activity_service
        self._schedule_repo = schedule_repo
        self._user_repo = user_repo
        self._user = user

        self._activity_selector = QComboBox()
        self._activity_selector.setMinimumWidth(220)
        self._message = QLabel("")
        set_banner(self._message, "info", "")

        # Checkin code display
        self._checkin_code_label = QLabel("")
        self._checkin_code_label.setObjectName("checkinCodeLabel")
        self._checkin_code_label.setAlignment(Qt.AlignCenter)
        self._checkin_code_label.setVisible(False)

        # QR code display
        self._qr_label = QLabel("")
        self._qr_label.setObjectName("qrCodeLabel")
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setVisible(False)

        # Statistics cards
        self._stats_frame = QFrame()
        self._stats_frame.setObjectName("statsFrame")
        self._stats_layout = QGridLayout()
        self._stats_layout.setSpacing(12)
        self._stats_frame.setLayout(self._stats_layout)
        self._stats_frame.setVisible(False)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["用户名", "时段", "签到状态", "user_id", "slot_id"])
        configure_table(self._table)

        checkin_btn = QPushButton("签到")
        checkin_btn.setObjectName("primaryButton")
        checkin_btn.clicked.connect(self._check_in)

        absent_btn = QPushButton("标记缺勤")
        absent_btn.setObjectName("dangerButton")
        absent_btn.clicked.connect(self._mark_absent)

        unabsent_btn = QPushButton("取消缺勤")
        unabsent_btn.setObjectName("secondaryButton")
        unabsent_btn.clicked.connect(self._unmark_absent)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self._load_results)

        self._generate_code_btn = QPushButton("生成签到码")
        self._generate_code_btn.setObjectName("primaryButton")
        self._generate_code_btn.clicked.connect(self._generate_checkin_code)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addWidget(checkin_btn)
        btn_layout.addWidget(absent_btn)
        btn_layout.addWidget(unabsent_btn)
        btn_layout.addWidget(self._generate_code_btn)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()

        selector_layout = QHBoxLayout()
        selector_layout.setSpacing(12)
        selector_layout.addWidget(QLabel("活动"))
        selector_layout.addWidget(self._activity_selector, 1)
        selector_layout.addStretch()

        group = QGroupBox("签到管理")
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(12, 12, 12, 12)
        group_layout.addLayout(selector_layout)
        group_layout.addWidget(self._checkin_code_label)
        group_layout.addWidget(self._qr_label)
        group_layout.addWidget(self._stats_frame)
        group_layout.addWidget(self._table)
        group_layout.addLayout(btn_layout)
        group_layout.addWidget(self._message)
        group.setLayout(group_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(make_page_header("签到", "管理活动签到与缺勤标记"))
        layout.addWidget(group, 1)
        self.setLayout(layout)

        self._activity_selector.currentIndexChanged.connect(self._load_results)

        # Auto-refresh timer for real-time stats
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._load_results)

        self.refresh()

    def refresh(self) -> None:
        activities = self._activity_service.list_activities()
        self._activity_selector.clear()
        if not activities:
            set_table_empty(self._table, 5, "暂无活动")
            return
        # Only show activities with status closed or later (排班完成后才有签到需求)
        visible_statuses = {ActivityStatus.CLOSED.value, ActivityStatus.ARCHIVED.value}
        for activity in activities:
            if activity.get("status", "draft") not in visible_statuses:
                continue
            status_text = format_status(activity.get("status", "draft"))
            self._activity_selector.addItem(f"{activity['name']} ({status_text})", activity["id"])
        self._load_results()

    def _load_results(self) -> None:
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            set_table_empty(self._table, 5, "请选择活动")
            self._checkin_code_label.setVisible(False)
            self._qr_label.setVisible(False)
            self._stats_frame.setVisible(False)
            self._generate_code_btn.setVisible(False)
            self._refresh_timer.stop()
            return

        activity = self._activity_service.get_activity(activity_id)
        checkin_mode = activity.get("checkin_mode", CheckInMode.MANUAL.value) if activity else CheckInMode.MANUAL.value
        is_code_mode = checkin_mode in (CheckInMode.SELF_CODE.value, CheckInMode.QRCODE.value)

        # Show generate code button only for SELF_CODE and QRCODE modes
        self._generate_code_btn.setVisible(is_code_mode)

        # Show checkin code if available and mode supports it
        if is_code_mode and activity and activity.get("checkin_code"):
            code = activity["checkin_code"]
            self._checkin_code_label.setText(f"签到码: {code}")
            self._checkin_code_label.setVisible(True)
            # Try to show QR code image for QRCODE mode
            if checkin_mode == CheckInMode.QRCODE.value:
                self._show_qr_code(code)
            else:
                self._qr_label.setVisible(False)
        else:
            self._checkin_code_label.setVisible(False)
            self._qr_label.setVisible(False)

        # Load statistics
        self._load_stats(activity_id)

        rows = self._schedule_repo.list_by_activity(activity_id)
        if not rows:
            set_table_empty(self._table, 5, "暂无排班结果")
            return
        slot_map: dict[str, str] = {}
        for slot in self._activity_service.list_slots(activity_id):
            slot_map[slot["id"]] = f"{format_datetime(slot['start_time'])} - {format_datetime(slot['end_time'])}"
        checkins = self._checkin_service.list_by_activity(activity_id)
        checkin_map: dict[str, str] = {}
        for ci in checkins:
            checkin_map[ci["user_id"] + ":" + ci["slot_id"]] = ci["status"]
        user_cache: dict[str, str] = {}
        self._table.clearSpans()
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            uid = row["user_id"]
            if uid not in user_cache:
                u = self._user_repo.get_by_id(uid)
                user_cache[uid] = u["username"] if u else uid
            self._table.setItem(row_index, 0, QTableWidgetItem(user_cache[uid]))
            slot_label = slot_map.get(row["slot_id"], row["slot_id"])
            self._table.setItem(row_index, 1, QTableWidgetItem(slot_label))
            status_raw = checkin_map.get(uid + ":" + row["slot_id"], "")
            if status_raw == "checked_in":
                status_text = "已签到"
            elif status_raw == "absent":
                status_text = "缺勤"
            else:
                status_text = "未签到"
            self._table.setItem(row_index, 2, QTableWidgetItem(status_text))
            self._table.setItem(row_index, 3, QTableWidgetItem(uid))
            self._table.setItem(row_index, 4, QTableWidgetItem(row["slot_id"]))
        self._table.setColumnHidden(3, True)
        self._table.setColumnHidden(4, True)

        # Start auto-refresh for closed or archived activities (both allow check-in)
        if activity and activity.get("status") in (ActivityStatus.CLOSED.value, ActivityStatus.ARCHIVED.value):
            if not self._refresh_timer.isActive():
                self._refresh_timer.start(10000)  # Refresh every 10 seconds
        else:
            self._refresh_timer.stop()

    def _load_stats(self, activity_id: str) -> None:
        """Load and display check-in statistics."""
        # Clear existing stats
        for i in reversed(range(self._stats_layout.count())):
            item = self._stats_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

        try:
            stats = self._checkin_service.get_checkin_stats(activity_id)
        except ValidationError:
            self._stats_frame.setVisible(False)
            return

        total_assigned = stats["total_assigned"]
        checked_in = stats["checked_in"]
        absent = stats["absent"]
        not_checked_in = stats["not_checked_in"]

        if total_assigned == 0:
            self._stats_frame.setVisible(False)
            return

        self._stats_frame.setVisible(True)

        cards = [
            ("总分配", str(total_assigned)),
            ("已签到", str(checked_in)),
            ("缺勤", str(absent)),
            ("未签到", str(not_checked_in)),
        ]

        for index, (label, value) in enumerate(cards):
            card = self._make_stat_card(label, value)
            self._stats_layout.addWidget(card, 0, index)

    def _make_stat_card(self, label: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("statCard")
        card.setFixedHeight(80)
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        name_label = QLabel(label)
        name_label.setObjectName("statLabel")
        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        layout.addWidget(name_label)
        layout.addWidget(value_label)
        card.setLayout(layout)
        return card

    def _generate_checkin_code(self) -> None:
        try:
            set_banner(self._message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                set_banner(self._message, "error", "请先选择活动")
                return
            code = self._checkin_service.generate_checkin_code(user=self._user, activity_id=activity_id)
            self._checkin_code_label.setText(f"签到码: {code}")
            self._checkin_code_label.setVisible(True)
            # Show QR code if QRCODE mode
            activity = self._activity_service.get_activity(activity_id)
            if activity and activity.get("checkin_mode") == CheckInMode.QRCODE.value:
                self._show_qr_code(code)
            else:
                self._qr_label.setVisible(False)
            set_banner(self._message, "success", f"签到码已生成: {code}")
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))

    def _check_in(self) -> None:
        try:
            set_banner(self._message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                set_banner(self._message, "error", "请先选择活动")
                return
            current_row = self._table.currentRow()
            if current_row < 0:
                set_banner(self._message, "error", "请选择一行进行签到")
                return
            user_id_item = self._table.item(current_row, 3)
            slot_id_item = self._table.item(current_row, 4)
            if not user_id_item or not slot_id_item:
                set_banner(self._message, "error", "数据异常")
                return
            self._checkin_service.check_in(
                user=self._user,
                activity_id=activity_id,
                user_id=user_id_item.text(),
                slot_id=slot_id_item.text(),
            )
            set_banner(self._message, "success", "签到成功")
            self._load_results()
        except (ConflictError, PermissionDenied, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))

    def _mark_absent(self) -> None:
        try:
            set_banner(self._message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                set_banner(self._message, "error", "请先选择活动")
                return
            current_row = self._table.currentRow()
            if current_row < 0:
                set_banner(self._message, "error", "请选择一行进行标记")
                return
            user_id_item = self._table.item(current_row, 3)
            slot_id_item = self._table.item(current_row, 4)
            if not user_id_item or not slot_id_item:
                set_banner(self._message, "error", "数据异常")
                return
            self._checkin_service.mark_absent(
                user=self._user,
                activity_id=activity_id,
                user_id=user_id_item.text(),
                slot_id=slot_id_item.text(),
            )
            set_banner(self._message, "success", "已标记缺勤")
            self._load_results()
        except (ConflictError, PermissionDenied, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))

    def _unmark_absent(self) -> None:
        try:
            set_banner(self._message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                set_banner(self._message, "error", "请先选择活动")
                return
            current_row = self._table.currentRow()
            if current_row < 0:
                set_banner(self._message, "error", "请选择一行进行取消缺勤")
                return
            user_id_item = self._table.item(current_row, 3)
            slot_id_item = self._table.item(current_row, 4)
            if not user_id_item or not slot_id_item:
                set_banner(self._message, "error", "数据异常")
                return
            self._checkin_service.unmark_absent(
                user=self._user,
                activity_id=activity_id,
                user_id=user_id_item.text(),
                slot_id=slot_id_item.text(),
            )
            set_banner(self._message, "success", "已取消缺勤标记")
            self._load_results()
        except (ConflictError, PermissionDenied, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))

    def _show_qr_code(self, code: str) -> None:
        """Try to generate and display a QR code image; fall back to text if qrcode lib unavailable."""
        try:
            import qrcode as qrcode_lib
            from io import BytesIO

            qr = qrcode_lib.QRCode(version=1, box_size=6, border=2)
            qr.add_data(code)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue(), "PNG")
            if not pixmap.isNull():
                self._qr_label.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self._qr_label.setVisible(True)
                return
        except ImportError:
            pass
        # Fallback: show text code
        self._qr_label.setVisible(False)
