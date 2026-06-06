from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.activity_service import ActivityService
from app.application.registration_service import RegistrationService
from app.domain.exceptions import CapacityExceeded, ConflictError, ValidationError
from app.domain.models import ActivityStatus, ActivityType, RegistrationStatus, SignupMode, User
from app.infrastructure.notifications import notify
from app.infrastructure.repositories import RegistrationRepository
from app.ui.style import get_palette
from app.ui.ui_utils import (
    CountdownLabel,
    ModeSelector,
    StyledComboBox,
    configure_table,
    format_activity_status,
    format_datetime,
    format_slot_name,
    format_status,
    make_page_header,
    set_banner,
    set_table_empty,
)


def _p():
    return get_palette()


def _color(hex_str: str) -> QColor:
    return QColor(hex_str)


class SlotGridWidget(QWidget):
    """医院挂号式的时段格子视图：按日期分组，每个格子显示时段名称和剩余名额"""
    slot_clicked = Signal(str)  # slot_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._slots: list[dict] = []
        self._signup_mode: str = SignupMode.REALTIME.value
        self._selected_slot_id: str | None = None
        self._grid_layout: QGridLayout | None = None
        self._content_widget: QWidget | None = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._content_widget = QWidget()
        self._grid_layout = QGridLayout()
        self._grid_layout.setSpacing(8)
        self._grid_layout.setContentsMargins(4, 4, 4, 4)
        self._content_widget.setLayout(self._grid_layout)
        self._scroll.setWidget(self._content_widget)

        layout.addWidget(self._scroll)
        self.setLayout(layout)

    def set_slots(self, slots: list[dict], signup_mode: str = SignupMode.REALTIME.value):
        self._slots = slots
        self._signup_mode = signup_mode
        self._rebuild_grid()

    def get_selected_slot_id(self) -> str | None:
        return self._selected_slot_id

    def _rebuild_grid(self):
        # 清空旧内容
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        p = _p()

        # 按日期分组（仅时段类型）
        date_groups: dict[str, list[dict]] = {}
        non_time_slots: list[dict] = []

        for slot in self._slots:
            if slot.get("parent_slot_id"):
                continue  # 子岗位不直接在格子中显示
            if slot.get("start_time"):
                try:
                    dt = datetime.fromisoformat(slot["start_time"].replace('Z', '+00:00'))
                    date_key = dt.strftime("%Y-%m-%d")
                    date_groups.setdefault(date_key, []).append(slot)
                except (ValueError, TypeError):
                    non_time_slots.append(slot)
            else:
                non_time_slots.append(slot)

        row = 0

        # 时段模式：按日期分组显示格子
        for date_key in sorted(date_groups.keys()):
            slots_for_date = date_groups[date_key]
            try:
                dt = datetime.strptime(date_key, "%Y-%m-%d")
                weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                weekday = weekday_names[dt.weekday()]
                date_label = QLabel(f"  {dt.strftime('%m月%d日')} {weekday}")
                date_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {p.text_primary}; margin-top: 4px;")
                self._grid_layout.addWidget(date_label, row, 0, 1, -1)
                row += 1

                # 格子行
                col = 0
                max_cols = 4
                for slot in sorted(slots_for_date, key=lambda s: s.get("start_time", "")):
                    card = self._create_slot_card(slot)
                    self._grid_layout.addWidget(card, row, col)
                    col += 1
                    if col >= max_cols:
                        col = 0
                        row += 1
                if col > 0:
                    row += 1
            except ValueError:
                for slot in slots_for_date:
                    non_time_slots.append(slot)

        # 非时段选项：列表式显示
        if non_time_slots:
            if date_groups:
                sep = QLabel("  选项列表")
                sep.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {p.text_primary}; margin-top: 8px;")
                self._grid_layout.addWidget(sep, row, 0, 1, -1)
                row += 1

            col = 0
            max_cols = 4
            for slot in non_time_slots:
                card = self._create_slot_card(slot)
                self._grid_layout.addWidget(card, row, col)
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1

        self._grid_layout.setRowStretch(row, 1)

    def _create_slot_card(self, slot: dict) -> QWidget:
        p = _p()
        capacity = int(slot["capacity"])
        used = int(slot["used_count"])
        remaining = capacity - used
        is_full = remaining <= 0

        card = QFrame()
        card.setCursor(Qt.PointingHandCursor if not is_full else Qt.ForbiddenCursor)
        card.setProperty("slot_id", slot["id"])

        # 选中状态
        is_selected = self._selected_slot_id == slot["id"]

        if is_full:
            border_color = p.text_tertiary
            bg_color = p.bg_sidebar
        elif is_selected:
            border_color = p.accent
            bg_color = p.accent_soft
        else:
            border_color = p.border_light
            bg_color = p.bg_card

        card.setStyleSheet(f"""
            QFrame {{
                background: {bg_color};
                border: 2px solid {border_color};
                border-radius: 10px;
                padding: 8px;
                min-height: 70px;
                max-height: 90px;
            }}
            QFrame:hover {{
                border-color: {p.accent if not is_full else p.text_tertiary};
            }}
        """)

        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(2)

        # 名称
        name = format_slot_name(slot)
        name_label = QLabel(name)
        name_label.setStyleSheet(f"font-weight: 600; font-size: 12px; color: {p.text_primary if not is_full else p.text_tertiary}; border: none;")
        name_label.setWordWrap(True)
        card_layout.addWidget(name_label)

        # 时间（如果有）
        if slot.get("start_time"):
            try:
                st = datetime.fromisoformat(slot["start_time"].replace('Z', '+00:00'))
                et = datetime.fromisoformat(slot["end_time"].replace('Z', '+00:00')) if slot.get("end_time") else None
                time_text = st.strftime("%H:%M")
                if et:
                    time_text += f" - {et.strftime('%H:%M')}"
                time_label = QLabel(time_text)
                time_label.setStyleSheet(f"font-size: 11px; color: {p.text_secondary}; border: none;")
                card_layout.addWidget(time_label)
            except (ValueError, TypeError):
                pass

        # 剩余名额
        if self._signup_mode == SignupMode.REALTIME.value:
            if is_full:
                quota_label = QLabel("已满")
                quota_label.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {p.error_fg}; border: none;")
            else:
                quota_label = QLabel(f"剩余 {remaining} 名")
                quota_label.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {p.success_fg}; border: none;")
        else:
            quota_label = QLabel("名额保密")
            quota_label.setStyleSheet(f"font-size: 12px; color: {p.text_tertiary}; border: none;")
        card_layout.addWidget(quota_label)

        card.setLayout(card_layout)

        # 点击事件
        if not is_full:
            card.mousePressEvent = lambda event, s=slot: self._on_card_click(s)

        return card

    def _on_card_click(self, slot: dict):
        self._selected_slot_id = slot["id"]
        self._rebuild_grid()
        self.slot_clicked.emit(slot["id"])


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

        self._activity_selector = StyledComboBox()
        self._activity_selector.setMinimumWidth(220)
        self._slot_selector = StyledComboBox()
        self._slot_selector.setMinimumWidth(220)
        self._message = QLabel("")
        set_banner(self._message, "info", "")

        self._countdown_label = CountdownLabel("", "")

        # 格子视图
        self._slot_grid = SlotGridWidget()
        self._slot_grid.slot_clicked.connect(self._on_grid_slot_clicked)

        # 详细表格（传统视图）
        self._slot_table = QTableWidget(0, 8)
        self._slot_table.setHorizontalHeaderLabels(["ID", "类型", "名称", "开始", "结束", "容量", "已用", "剩余"])
        configure_table(self._slot_table)

        # 视图切换
        self._view_toggle = ModeSelector()
        self._view_toggle.addItems(["格子视图", "表格视图"])
        self._view_toggle.currentIndexChanged.connect(self._on_view_toggle)

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self._slot_grid)
        self._view_stack.addWidget(self._slot_table)

        # 操作区
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow("活动", self._activity_selector)
        form.addRow(self._countdown_label)

        # 操作行：视图切换 + 选项选择 + 报名按钮
        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("视图"))
        action_row.addWidget(self._view_toggle)
        action_row.addSpacing(16)
        action_row.addWidget(QLabel("选项"))
        action_row.addWidget(self._slot_selector, 1)
        submit_btn = QPushButton("提交报名")
        submit_btn.setObjectName("primaryButton")
        submit_btn.clicked.connect(self._register)
        action_row.addWidget(submit_btn)
        form.addRow(action_row)
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

        # 选项详情区域
        detail_group = QGroupBox("选项详情")
        detail_layout = QVBoxLayout()
        detail_layout.setContentsMargins(12, 12, 12, 12)
        detail_layout.addWidget(self._view_stack)
        detail_group.setLayout(detail_layout)

        header = make_page_header("报名", "选择活动和时段完成报名")

        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        right_col.addWidget(detail_group, 1)
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

    def _on_view_toggle(self, index: int):
        self._view_stack.setCurrentIndex(index)

    def _on_grid_slot_clicked(self, slot_id: str):
        """格子视图点击后同步到下拉框"""
        for i in range(self._slot_selector.count()):
            if self._slot_selector.itemData(i) == slot_id:
                self._slot_selector.setCurrentIndex(i)
                break

    def refresh(self) -> None:
        activities = self._activity_service.list_activities()
        self._activity_selector.blockSignals(True)
        self._activity_selector.clear()
        if not activities:
            set_table_empty(self._slot_table, 8, "暂无活动，请等待管理员创建活动")
            self._activity_selector.blockSignals(False)
            self._load_my_registrations()
            return
        open_activities = [a for a in activities if a.get("status") == ActivityStatus.OPEN.value]
        other_activities = [a for a in activities if a.get("status") != ActivityStatus.OPEN.value]
        for activity in open_activities:
            at = activity.get("activity_type", "time_slot")
            mode_tag = "时段" if at == ActivityType.TIME_SLOT.value else "选项"
            self._activity_selector.addItem(f"{activity['name']} [{mode_tag}] (报名中)", activity["id"])
        if other_activities:
            self._activity_selector.insertSeparator(self._activity_selector.count())
            for activity in other_activities:
                status_text = format_activity_status(activity)
                self._activity_selector.addItem(f"{activity['name']} ({status_text})", activity["id"])
        self._activity_selector.blockSignals(False)
        self._load_slots()
        self._load_my_registrations()

    def _load_slots(self) -> None:
        activity_id = self._activity_selector.currentData()
        self._slot_selector.clear()
        self._slot_grid._selected_slot_id = None
        if not activity_id:
            self._countdown_label.set_times("", "")
            return
        activity = self._activity_service.get_activity(activity_id)
        if activity:
            self._countdown_label.set_times(activity.get("signup_start", ""), activity.get("signup_end", ""))
        signup_mode = activity.get("signup_mode") if activity else SignupMode.REALTIME.value
        is_open = activity.get("status") == ActivityStatus.OPEN.value if activity else False
        slots = self._activity_service.list_slots(activity_id)

        # 过滤掉子岗位（用户报名选择父时段，排班系统分配岗位）
        top_slots = [s for s in slots if not s.get("parent_slot_id")]

        if not top_slots:
            set_table_empty(self._slot_table, 8, "暂无选项")
            self._slot_grid.set_slots([], signup_mode)
            return

        # 更新格子视图
        self._slot_grid.set_slots(top_slots, signup_mode)

        # 更新表格视图
        self._slot_table.clearSpans()
        self._slot_table.setRowCount(len(top_slots))
        for row_index, slot in enumerate(top_slots):
            self._slot_table.setItem(row_index, 0, QTableWidgetItem(str(slot["id"])))

            slot_type = slot.get("slot_type", "time_slot")
            type_text = {
                "time_slot": "时段",
                "topic": "选题",
                "course": "课程",
                "custom_option": "自定义"
            }.get(slot_type, "其他")
            self._slot_table.setItem(row_index, 1, QTableWidgetItem(type_text))

            self._slot_table.setItem(row_index, 2, QTableWidgetItem(format_slot_name(slot)))

            start_text = format_datetime(slot["start_time"]) if slot.get("start_time") else "-"
            self._slot_table.setItem(row_index, 3, QTableWidgetItem(start_text))
            end_text = format_datetime(slot["end_time"]) if slot.get("end_time") else "-"
            self._slot_table.setItem(row_index, 4, QTableWidgetItem(end_text))

            capacity = int(slot["capacity"])
            used = int(slot["used_count"])
            remaining = capacity - used
            capacity_item = QTableWidgetItem(str(capacity))
            capacity_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._slot_table.setItem(row_index, 5, capacity_item)
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
            self._slot_table.setItem(row_index, 6, used_item)
            self._slot_table.setItem(row_index, 7, remaining_item)

            # 下拉框
            base_label = format_slot_name(slot)
            if signup_mode == SignupMode.REALTIME.value:
                slot_label = f"{base_label} (剩余{remaining}名)"
            else:
                slot_label = base_label
            self._slot_selector.addItem(slot_label, slot["id"])

        self._slot_table.setColumnHidden(0, True)

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
        self._my_reg_table.clearSpans()
        self._my_reg_table.setRowCount(len(regs))
        for row_index, reg in enumerate(regs):
            self._my_reg_table.setItem(row_index, 0, QTableWidgetItem(str(reg["id"])))
            activity_name = activities.get(reg["activity_id"], "未知活动")
            self._my_reg_table.setItem(row_index, 1, QTableWidgetItem(activity_name))
            slot = slots.get(reg["slot_id"])
            slot_text = format_slot_name(slot) if slot else "-"
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
