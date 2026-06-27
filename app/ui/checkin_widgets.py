from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.activity_service import ActivityService
from app.application.checkin_service import CheckInService
from app.domain.exceptions import ConflictError, PermissionDenied, ValidationError
from app.domain.models import ActivityStatus, CheckInMode, Role, User
from app.infrastructure.repositories import ScheduleRepository, UserRepository
from app.ui.style import get_palette
from app.ui.ui_utils import (
    ItemDetailDialog,
    StyledComboBox,
    configure_table,
    format_activity_status,
    format_datetime,
    make_page_header,
    set_banner,
    set_table_empty,
)

_CHECKIN_MODE_LABELS = {
    CheckInMode.MANUAL.value: "手动签到",
    CheckInMode.QRCODE.value: "二维码签到",
    CheckInMode.SELF_CODE.value: "签到码签到",
    CheckInMode.LOCATION.value: "位置签到",
    CheckInMode.PHOTO.value: "拍照签到",
}


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

        self._activity_selector = StyledComboBox()
        self._activity_selector.setMinimumWidth(220)
        self._message = QLabel("")
        set_banner(self._message, "info", "")

        # Activity info display
        self._activity_info_frame = QFrame()
        self._activity_info_frame.setObjectName("activityInfoFrame")
        self._activity_info_layout = QHBoxLayout()
        self._activity_info_layout.setContentsMargins(16, 10, 16, 10)
        self._activity_info_layout.setSpacing(24)
        self._activity_info_frame.setLayout(self._activity_info_layout)
        self._activity_info_frame.setVisible(False)

        # Checkin code display — prominent card
        self._checkin_code_frame = QFrame()
        self._checkin_code_frame.setObjectName("checkinCodeFrame")
        code_layout = QVBoxLayout()
        code_layout.setContentsMargins(24, 16, 24, 16)
        code_layout.setSpacing(4)
        code_title = QLabel("签到码")
        code_title.setObjectName("checkinCodeTitle")
        code_title.setAlignment(Qt.AlignCenter)
        self._checkin_code_label = QLabel("")
        self._checkin_code_label.setObjectName("checkinCodeLabel")
        self._checkin_code_label.setAlignment(Qt.AlignCenter)
        code_layout.addWidget(code_title)
        code_layout.addWidget(self._checkin_code_label)
        self._checkin_code_frame.setLayout(code_layout)
        self._checkin_code_frame.setVisible(False)

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

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(["用户名", "时段", "签到状态", "签到时间", "user_id", "slot_id"])
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

        self._batch_checkin_btn = QPushButton("全选已签到")
        self._batch_checkin_btn.setObjectName("primaryButton")
        self._batch_checkin_btn.clicked.connect(self._batch_check_in)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self._load_results)

        self._generate_code_btn = QPushButton("刷新签到码")
        self._generate_code_btn.setObjectName("primaryButton")
        self._generate_code_btn.clicked.connect(self._generate_checkin_code)

        # 提前结束签到按钮：仅在签到中显示，人工关闭后隐藏
        self._close_checkin_btn = QPushButton("提前结束签到")
        self._close_checkin_btn.setObjectName("dangerButton")
        self._close_checkin_btn.clicked.connect(self._close_checkin)
        self._close_checkin_btn.setVisible(False)

        self._reopen_checkin_btn = QPushButton("恢复签到")
        self._reopen_checkin_btn.setObjectName("secondaryButton")
        self._reopen_checkin_btn.clicked.connect(self._reopen_checkin)
        self._reopen_checkin_btn.setVisible(False)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addWidget(checkin_btn)
        btn_layout.addWidget(absent_btn)
        btn_layout.addWidget(unabsent_btn)
        btn_layout.addWidget(self._batch_checkin_btn)
        btn_layout.addWidget(self._generate_code_btn)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self._close_checkin_btn)
        btn_layout.addWidget(self._reopen_checkin_btn)

        selector_layout = QHBoxLayout()
        selector_layout.setSpacing(12)
        selector_layout.addWidget(QLabel("活动"))
        selector_layout.addWidget(self._activity_selector, 1)
        selector_layout.addStretch()

        # ---- 信息区域：活动信息 + 签到码 + 统计（水平排列，紧凑展示） ----
        info_row = QHBoxLayout()
        info_row.setSpacing(12)
        info_row.addWidget(self._activity_info_frame, 3)
        info_row.addWidget(self._checkin_code_frame, 1)
        info_row.addWidget(self._qr_label, 1)

        # ---- 整体布局（纵向排布） ----
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(make_page_header("签到", "管理活动签到与缺勤标记"))
        layout.addLayout(selector_layout)
        layout.addLayout(info_row)
        layout.addWidget(self._stats_frame)
        layout.addWidget(self._table, 1)
        layout.addLayout(btn_layout)
        layout.addWidget(self._message)
        self.setLayout(layout)

        self._activity_selector.currentIndexChanged.connect(self._load_results)
        self._table.cellDoubleClicked.connect(self._on_checkin_double_clicked)

        # Auto-refresh timer for real-time stats
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._load_results)

        self.refresh()

    def refresh(self) -> None:
        activities = self._activity_service.list_activities()
        self._activity_selector.blockSignals(True)
        self._activity_selector.clear()
        if not activities:
            set_table_empty(self._table, 6, "暂无活动")
            self._activity_selector.blockSignals(False)
            return
        # Only show activities with status closed or later (排班完成后才有签到需求)
        visible_statuses = {ActivityStatus.CLOSED.value, ActivityStatus.ARCHIVED.value}
        for activity in activities:
            if activity.get("status", "draft") not in visible_statuses:
                continue
            status_text = format_activity_status(activity)
            self._activity_selector.addItem(f"{activity['name']} ({status_text})", activity["id"])
        self._activity_selector.blockSignals(False)
        self._load_results()

    def _on_checkin_double_clicked(self, row: int, _col: int) -> None:
        data = {}
        for col, key in enumerate(["用户名", "时段", "签到状态", "签到时间"]):
            item = self._table.item(row, col)
            data[key] = item.text() if item else "—"
        ItemDetailDialog("签到详情", data, self).exec()

    def _load_results(self) -> None:
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            set_table_empty(self._table, 6, "请选择活动")
            self._checkin_code_frame.setVisible(False)
            self._qr_label.setVisible(False)
            self._stats_frame.setVisible(False)
            self._activity_info_frame.setVisible(False)
            self._generate_code_btn.setVisible(False)
            self._batch_checkin_btn.setVisible(False)
            self._refresh_timer.stop()
            return

        activity = self._activity_service.get_activity(activity_id)
        checkin_mode = activity.get("checkin_mode", CheckInMode.MANUAL.value) if activity else CheckInMode.MANUAL.value
        is_code_mode = checkin_mode in (CheckInMode.SELF_CODE.value, CheckInMode.QRCODE.value)

        # Show generate code button only for SELF_CODE and QRCODE modes
        self._generate_code_btn.setVisible(is_code_mode)
        self._batch_checkin_btn.setVisible(True)

        # Activity info display
        self._load_activity_info(activity)

        # Show checkin code if available and mode supports it
        if is_code_mode and activity and activity.get("checkin_code"):
            code = activity["checkin_code"]
            self._checkin_code_label.setText(code)
            self._checkin_code_frame.setVisible(True)
            # Try to show QR code image for QRCODE mode
            if checkin_mode == CheckInMode.QRCODE.value:
                self._show_qr_code(code)
            else:
                self._qr_label.setVisible(False)
        else:
            self._checkin_code_frame.setVisible(False)
            self._qr_label.setVisible(False)

        # Load statistics
        self._load_stats(activity_id)

        rows = self._schedule_repo.list_by_activity(activity_id)
        if not rows:
            set_table_empty(self._table, 6, "暂无排班结果")
            return
        slot_map: dict[str, str] = {}
        for slot in self._activity_service.list_slots(activity_id):
            if slot.get("name"):
                slot_map[slot["id"]] = slot["name"]
            elif slot.get("start_time"):
                slot_map[slot["id"]] = f"{format_datetime(slot['start_time'])} - {format_datetime(slot['end_time'])}"
            else:
                slot_map[slot["id"]] = slot["id"]
        checkins = self._checkin_service.list_by_activity(activity_id)
        checkin_map: dict[str, dict] = {}
        for ci in checkins:
            checkin_map[ci["user_id"] + ":" + ci["slot_id"]] = ci
        user_cache: dict[str, str] = {}
        self._table.clearSpans()
        self._table.setRowCount(len(rows))
        p = get_palette()
        for row_index, row in enumerate(rows):
            uid = row["user_id"]
            if uid not in user_cache:
                u = self._user_repo.get_by_id(uid)
                user_cache[uid] = u["username"] if u else uid
            self._table.setItem(row_index, 0, QTableWidgetItem(user_cache[uid]))
            slot_label = slot_map.get(row["slot_id"], row["slot_id"])
            self._table.setItem(row_index, 1, QTableWidgetItem(slot_label))

            ci = checkin_map.get(uid + ":" + row["slot_id"])
            status_raw = ci["status"] if ci else ""
            if status_raw == "checked_in":
                status_text = "已签到"
            elif status_raw == "absent":
                status_text = "缺勤"
            else:
                status_text = "未签到"

            # Visual status indicator
            status_item = self._make_checkin_status_item(status_text, p)
            self._table.setItem(row_index, 2, status_item)

            # Checked-at time
            checked_at_text = ""
            if ci and ci.get("checked_at"):
                checked_at_text = format_datetime(ci["checked_at"])
            self._table.setItem(row_index, 3, QTableWidgetItem(checked_at_text))

            self._table.setItem(row_index, 4, QTableWidgetItem(uid))
            self._table.setItem(row_index, 5, QTableWidgetItem(row["slot_id"]))
        self._table.setColumnHidden(4, True)
        self._table.setColumnHidden(5, True)

        # Start auto-refresh for closed or archived activities (both allow check-in)
        if activity and activity.get("status") in (ActivityStatus.CLOSED.value, ActivityStatus.ARCHIVED.value):
            if not self._refresh_timer.isActive():
                self._refresh_timer.start(10000)  # Refresh every 10 seconds
        else:
            self._refresh_timer.stop()

    def _load_activity_info(self, activity: dict | None) -> None:
        """Display activity metadata: location, checkin mode, checkin time range."""
        # Clear existing
        for i in reversed(range(self._activity_info_layout.count())):
            item = self._activity_info_layout.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

        if not activity:
            self._activity_info_frame.setVisible(False)
            return

        p = get_palette()
        self._activity_info_frame.setStyleSheet(f"""
            QFrame#activityInfoFrame {{
                background: {p.bg_input};
                border: 1px solid {p.border_light};
                border-radius: 12px;
            }}
            QFrame#activityInfoFrame QLabel {{
                color: {p.text_primary};
                border: none;
                background: transparent;
            }}
        """)

        info_items: list[tuple[str, str]] = []

        # 活动状态（签到上下文）
        status_label = format_activity_status(activity)
        info_items.append(("状态", status_label))

        # Location
        location = activity.get("location", "")
        if location:
            info_items.append(("地点", location))

        # Checkin mode
        mode_val = activity.get("checkin_mode", CheckInMode.MANUAL.value)
        mode_label = _CHECKIN_MODE_LABELS.get(mode_val, mode_val)
        info_items.append(("签到方式", mode_label))

        # Checkin time range
        checkin_start = activity.get("checkin_start", "")
        checkin_end = activity.get("checkin_end", "")
        if checkin_start and checkin_end:
            info_items.append(("签到时间", f"{format_datetime(checkin_start)} ~ {format_datetime(checkin_end)}"))
        elif checkin_start:
            info_items.append(("签到开始", format_datetime(checkin_start)))

        if not info_items:
            self._activity_info_frame.setVisible(False)
            return

        self._activity_info_frame.setVisible(True)
        for label_text, value_text in info_items:
            pair = QFrame()
            pair.setStyleSheet("background: transparent; border: none;")
            pair_layout = QVBoxLayout()
            pair_layout.setContentsMargins(0, 0, 0, 0)
            pair_layout.setSpacing(2)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px; border: none; background: transparent;")
            val = QLabel(value_text)
            val.setStyleSheet(f"color: {p.text_primary}; font-size: 13px; font-weight: 500; border: none; background: transparent;")
            pair_layout.addWidget(lbl)
            pair_layout.addWidget(val)
            pair.setLayout(pair_layout)
            self._activity_info_layout.addWidget(pair)

        self._activity_info_layout.addStretch()

        # 根据签到状态控制「提前结束签到/恢复签到」按钮可见性
        # 仅管理员/组织者可见，且仅在签到中/签到已结束时显示对应按钮
        is_manager = self._user.role in {Role.SUPER_ADMIN, Role.ORGANIZER}
        if not is_manager:
            self._close_checkin_btn.setVisible(False)
            self._reopen_checkin_btn.setVisible(False)
            return
        status = activity.get("status", "")
        checkin_closed = bool(activity.get("checkin_closed"))
        # 仅在 CLOSED/ARCHIVED 状态（签到阶段）显示
        in_checkin_phase = status in ("closed", "archived")
        if not in_checkin_phase:
            self._close_checkin_btn.setVisible(False)
            self._reopen_checkin_btn.setVisible(False)
        elif checkin_closed:
            self._close_checkin_btn.setVisible(False)
            self._reopen_checkin_btn.setVisible(True)
        else:
            self._close_checkin_btn.setVisible(True)
            self._reopen_checkin_btn.setVisible(False)

    def _load_stats(self, activity_id: str) -> None:
        """Load and display check-in statistics with progress bars and percentages."""
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
            ("总分配", str(total_assigned), total_assigned, total_assigned, "accent"),
            ("已签到", str(checked_in), checked_in, total_assigned, "success"),
            ("缺勤", str(absent), absent, total_assigned, "error"),
            ("未签到", str(not_checked_in), not_checked_in, total_assigned, "warning"),
        ]

        for index, (label, value, progress_val, progress_max, accent_key) in enumerate(cards):
            card = self._make_stat_card(label, value, progress_val, progress_max, accent_key)
            self._stats_layout.addWidget(card, 0, index)

    def _make_stat_card(
        self, label: str, value: str, progress_val: int, progress_max: int, accent_key: str
    ) -> QFrame:
        p = get_palette()
        color_map = {
            "accent": p.accent,
            "success": p.success_fg,
            "error": p.error_fg,
            "warning": p.warning_fg,
        }
        accent_color = color_map.get(accent_key, p.accent)

        card = QFrame()
        card.setObjectName("statCard")
        card.setProperty("accentColor", accent_key)
        card.setFixedHeight(110)
        # Force style re-evaluation for dynamic property
        card.style().unpolish(card)
        card.style().polish(card)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        name_label = QLabel(label)
        name_label.setObjectName("statLabel")
        layout.addWidget(name_label)

        # Value + percentage row
        val_row = QHBoxLayout()
        val_row.setSpacing(8)
        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        val_row.addWidget(value_label)

        if progress_max > 0:
            pct = progress_val / progress_max * 100
            pct_label = QLabel(f"{pct:.0f}%")
            pct_label.setStyleSheet(
                f"color: {accent_color}; font-size: 13px; font-weight: 600; border: none; background: transparent;"
            )
            val_row.addWidget(pct_label)
        val_row.addStretch()
        layout.addLayout(val_row)

        # Progress bar
        if progress_max > 0:
            bar = QProgressBar()
            bar.setRange(0, progress_max)
            bar.setValue(progress_val)
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background: {p.bg_input};
                    border: none;
                    border-radius: 3px;
                }}
                QProgressBar::chunk {{
                    background: {accent_color};
                    border-radius: 3px;
                }}
            """)
            layout.addWidget(bar)

        card.setLayout(layout)
        return card

    @staticmethod
    def _make_checkin_status_item(text: str, p) -> QTableWidgetItem:
        """Create a table item with colored foreground/background for checkin status."""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        color_map = {
            "已签到": (p.success_fg, p.success_bg),
            "缺勤": (p.error_fg, p.error_bg),
            "未签到": (p.text_tertiary, p.bg_base),
        }
        fg, bg = color_map.get(text, (p.text_secondary, p.bg_base))
        item.setForeground(QBrush(QColor(fg)))
        item.setBackground(QBrush(QColor(bg)))
        return item

    def _generate_checkin_code(self) -> None:
        try:
            set_banner(self._message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                set_banner(self._message, "error", "请先选择活动")
                return
            code = self._checkin_service.generate_checkin_code(user=self._user, activity_id=activity_id)
            # 直接更新签到码显示，避免 _load_results 重新加载导致闪烁
            self._checkin_code_label.setText(code)
            self._checkin_code_frame.setVisible(True)
            # Show QR code if QRCODE mode
            activity = self._activity_service.get_activity(activity_id)
            if activity and activity.get("checkin_mode") == CheckInMode.QRCODE.value:
                self._show_qr_code(code)
            else:
                self._qr_label.setVisible(False)
            set_banner(self._message, "success", f"签到码已刷新: {code}")
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
            user_id_item = self._table.item(current_row, 4)
            slot_id_item = self._table.item(current_row, 5)
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

    def _batch_check_in(self) -> None:
        """Batch check-in all selected rows in the table."""
        try:
            set_banner(self._message, "info", "")
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                set_banner(self._message, "error", "请先选择活动")
                return
            selected_rows = set()
            for item in self._table.selectedItems():
                selected_rows.add(item.row())
            if not selected_rows:
                set_banner(self._message, "error", "请先选择要签到的行")
                return
            success_count = 0
            skip_count = 0
            error_count = 0
            for row_index in sorted(selected_rows):
                user_id_item = self._table.item(row_index, 4)
                slot_id_item = self._table.item(row_index, 5)
                status_item = self._table.item(row_index, 2)
                if not user_id_item or not slot_id_item:
                    error_count += 1
                    continue
                # Skip already checked-in
                if status_item and status_item.text() == "已签到":
                    skip_count += 1
                    continue
                try:
                    self._checkin_service.check_in(
                        user=self._user,
                        activity_id=activity_id,
                        user_id=user_id_item.text(),
                        slot_id=slot_id_item.text(),
                    )
                    success_count += 1
                except (ConflictError, ValidationError):
                    skip_count += 1
            parts = []
            if success_count:
                parts.append(f"签到成功 {success_count} 人")
            if skip_count:
                parts.append(f"跳过 {skip_count} 人")
            if error_count:
                parts.append(f"异常 {error_count} 人")
            set_banner(self._message, "success", "，".join(parts) if parts else "无操作")
            self._load_results()
        except PermissionDenied as exc:
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
            user_id_item = self._table.item(current_row, 4)
            slot_id_item = self._table.item(current_row, 5)
            if not user_id_item or not slot_id_item:
                set_banner(self._message, "error", "数据异常")
                return
            self._checkin_service.mark_absent(
                user=self._user,
                activity_id=activity_id,
                user_id=user_id_item.text(),
                slot_id=slot_id_item.text(),
            )
        except PermissionDenied as exc:
            set_banner(self._message, "error", str(exc))
        except ValidationError as exc:
            set_banner(self._message, "error", str(exc))

    def _close_checkin(self) -> None:
        """人工提前结束签到。"""
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            set_banner(self._message, "error", "请先选择活动")
            return
        reply = QMessageBox.question(
            self, "提前结束签到",
            "确定要提前结束签到吗？结束后用户将无法继续签到，可通过「恢复签到」撤销。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._checkin_service.close_checkin(self._user, activity_id)
            set_banner(self._message, "success", "签到已结束")
            self._load_results()
        except PermissionDenied as exc:
            set_banner(self._message, "error", str(exc))
        except ValidationError as exc:
            set_banner(self._message, "error", str(exc))
        except Exception as exc:
            set_banner(self._message, "error", f"操作失败：{exc}")

    def _reopen_checkin(self) -> None:
        """恢复签到（撤销人工提前结束）。"""
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            set_banner(self._message, "error", "请先选择活动")
            return
        try:
            self._checkin_service.reopen_checkin(self._user, activity_id)
            set_banner(self._message, "success", "签到已恢复")
            self._load_results()
        except PermissionDenied as exc:
            set_banner(self._message, "error", str(exc))
        except ValidationError as exc:
            set_banner(self._message, "error", str(exc))
        except Exception as exc:
            set_banner(self._message, "error", f"操作失败：{exc}")

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
            user_id_item = self._table.item(current_row, 4)
            slot_id_item = self._table.item(current_row, 5)
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
