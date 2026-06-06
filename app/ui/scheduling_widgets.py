from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.activity_service import ActivityService
from app.application.scheduling_service import SchedulingService
from app.domain.exceptions import ValidationError
from app.infrastructure.exporter import export_to_excel
from app.infrastructure.repositories import ScheduleRepository, UserRepository
from app.ui.style import get_palette
from app.ui.ui_utils import (
    StyledComboBox,
    configure_table,
    format_datetime,
    format_slot_name,
    format_status,
    make_page_header,
    set_banner,
    set_table_empty,
)


class _StatCard(QFrame):
    """A small statistics card with an accent-colored left border."""

    def __init__(self, label: str, value: str, accent_color: str) -> None:
        super().__init__()
        self.setObjectName("statCard")
        self.setProperty("accentColor", accent_color)
        self.setFixedHeight(100)

        p = get_palette()
        color = getattr(p, accent_color, p.accent)
        self.setStyleSheet(f"""
            QFrame#statCard {{
                background: {p.bg_card};
                border: 1px solid {p.border_light};
                border-left: 4px solid {color};
                border-radius: 16px;
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)

        name_label = QLabel(label)
        name_label.setObjectName("statLabel")
        layout.addWidget(name_label)

        value_label = QLabel(str(value))
        value_label.setObjectName("statValue")
        layout.addWidget(value_label)

        layout.addStretch(1)
        self.setLayout(layout)


class _ActivityInfoCard(QFrame):
    """Shows key details about the currently selected activity."""

    def __init__(self) -> None:
        super().__init__()
        p = get_palette()
        self.setStyleSheet(f"""
            QFrame#activityInfoCard {{
                background: {p.bg_card};
                border: 1px solid {p.border_light};
                border-radius: 12px;
            }}
        """)
        self.setObjectName("activityInfoCard")

        self._form = QFormLayout()
        self._form.setContentsMargins(16, 12, 16, 12)
        self._form.setSpacing(6)
        self._form.setLabelAlignment(Qt.AlignRight)

        self._name_label = QLabel("-")
        self._location_label = QLabel("-")
        self._status_label = QLabel("-")
        self._alloc_label = QLabel("-")
        self._signup_label = QLabel("-")
        self._signup_time_label = QLabel("-")

        self._form.addRow("活动名称：", self._name_label)
        self._form.addRow("活动地点：", self._location_label)
        self._form.addRow("活动状态：", self._status_label)
        self._form.addRow("分配模式：", self._alloc_label)
        self._form.addRow("报名模式：", self._signup_label)
        self._form.addRow("报名时间：", self._signup_time_label)

        self.setLayout(self._form)
        self.setVisible(False)

    def update_info(self, activity: dict | None) -> None:
        if not activity:
            self.setVisible(False)
            return
        self.setVisible(True)

        self._name_label.setText(activity.get("name", "-"))
        self._location_label.setText(activity.get("location") or "-")

        status_text = format_status(activity.get("status", "draft"))
        self._status_label.setText(status_text)

        alloc_map = {"greedy": "贪心分配", "first_come": "先到先得", "lottery": "抽签"}
        self._alloc_label.setText(alloc_map.get(activity.get("allocation_mode", ""), activity.get("allocation_mode", "-")))

        signup_map = {"realtime": "实时", "blind": "盲选"}
        self._signup_label.setText(signup_map.get(activity.get("signup_mode", ""), activity.get("signup_mode", "-")))

        start = activity.get("signup_start")
        end = activity.get("signup_end")
        if start and end:
            self._signup_time_label.setText(f"{format_datetime(start)} ~ {format_datetime(end)}")
        else:
            self._signup_time_label.setText("-")


class _StatusComboBox(StyledComboBox):
    """A combo box that renders color-coded status indicators for each activity item."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(280)
        self._activities: dict[str, dict] = {}

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        p = get_palette()

        # Draw background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(p.bg_input))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)

        # Draw text
        text_rect = self.rect().adjusted(12, 0, -32, 0)
        painter.setPen(QColor(p.text_primary))
        painter.setFont(self.font())
        text = self.currentText()
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)

        # Draw status dot
        data = self.currentData()
        if data:
            activity = self._find_activity_by_id(data)
            if activity:
                status = activity.get("status", "draft")
                dot_color = self._status_color(status, p)
                dot_x = self.rect().width() - 30
                dot_y = self.rect().height() // 2
                painter.setBrush(QColor(dot_color))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(dot_x - 4, dot_y - 4, 8, 8)

        # Draw dropdown arrow
        arrow_x = self.rect().width() - 16
        arrow_y = self.rect().height() // 2
        painter.setPen(QPen(QColor(p.text_tertiary), 1.5))
        painter.drawLine(arrow_x - 4, arrow_y - 2, arrow_x, arrow_y + 2)
        painter.drawLine(arrow_x, arrow_y + 2, arrow_x + 4, arrow_y - 2)

        painter.end()

    def _find_activity_by_id(self, activity_id: str) -> dict | None:
        for i in range(self.count()):
            if self.itemData(i) == activity_id:
                return self._activities.get(activity_id)  # type: ignore[attr-defined]
        return None

    @staticmethod
    def _status_color(status: str, p) -> str:
        mapping = {
            "draft": p.warning_fg,
            "pending_review": p.accent,
            "open": p.success_fg,
            "closed": p.error_fg,
            "archived": p.text_tertiary,
        }
        return mapping.get(status, p.text_secondary)

    def set_activities(self, activities: list[dict]) -> None:
        """Populate the combo box with activities and store them for lookup."""
        self._activities: dict[str, dict] = {a["id"]: a for a in activities}
        self.blockSignals(True)
        self.clear()
        for activity in activities:
            status_text = format_status(activity.get("status", "draft"))
            self.addItem(f"{activity['name']} ({status_text})", activity["id"])
        self.blockSignals(False)
        self.update()


class SchedulingPanel(QWidget):
    def __init__(
        self,
        activity_service: ActivityService,
        scheduling_service: SchedulingService,
        schedule_repo: ScheduleRepository,
        user_repo: UserRepository,
    ) -> None:
        super().__init__()
        self._activity_service = activity_service
        self._scheduling_service = scheduling_service
        self._schedule_repo = schedule_repo
        self._user_repo = user_repo

        self._activity_selector = _StatusComboBox()
        self._message = QLabel("")
        set_banner(self._message, "info", "")

        # ── Statistics cards ─────────────────────────────────────
        self._stat_assigned = _StatCard("已分配人数", "0", "success_fg")
        self._stat_slots = _StatCard("选项总数", "0", "accent")
        self._stat_fill = _StatCard("填充率", "0%", "warning_fg")

        stat_layout = QHBoxLayout()
        stat_layout.setSpacing(12)
        stat_layout.addWidget(self._stat_assigned)
        stat_layout.addWidget(self._stat_slots)
        stat_layout.addWidget(self._stat_fill)

        # ── Activity info card ───────────────────────────────────
        self._activity_info = _ActivityInfoCard()

        # ── Buttons ──────────────────────────────────────────────
        run_btn = QPushButton("重新排班")
        run_btn.setObjectName("secondaryButton")
        run_btn.clicked.connect(self._run)
        export_btn = QPushButton("导出排班结果")
        export_btn.setObjectName("primaryButton")
        export_btn.clicked.connect(self._export)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self._load_results)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addWidget(refresh_btn)
        btn_layout.addWidget(run_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(export_btn)

        # ── Selector ─────────────────────────────────────────────
        selector_layout = QHBoxLayout()
        selector_layout.setSpacing(12)
        selector_layout.addWidget(QLabel("活动"))
        selector_layout.addWidget(self._activity_selector, 1)
        selector_layout.addStretch()

        info_label = QLabel("排班在报名结束后自动执行。如需重新排班，请点击「重新排班」按钮。")
        info_label.setObjectName("pageSubtitle")
        info_label.setWordWrap(True)

        # ── Result table ─────────────────────────────────────────
        self._result_table = QTableWidget(0, 5)
        self._result_table.setHorizontalHeaderLabels(["用户", "时段", "地点", "选项类型", "生成时间"])
        configure_table(self._result_table)

        form_group = QGroupBox("排班结果")
        form_layout = QVBoxLayout()
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.addLayout(selector_layout)
        form_layout.addWidget(info_label)
        form_layout.addLayout(stat_layout)
        form_layout.addWidget(self._activity_info)
        form_layout.addWidget(self._result_table)
        form_layout.addLayout(btn_layout)
        form_layout.addWidget(self._message)
        form_group.setLayout(form_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(make_page_header("排班结果", "查看自动排班结果并导出"))
        layout.addWidget(form_group, 1)
        self.setLayout(layout)

        self._activity_selector.currentIndexChanged.connect(self._load_results)
        self.refresh()

    def refresh(self) -> None:
        activities = self._activity_service.list_activities()
        self._activity_selector.set_activities(activities)
        self._load_results()

    def _load_results(self) -> None:
        try:
            activity_id = self._activity_selector.currentData()
            if not activity_id:
                set_table_empty(self._result_table, 5, "请选择活动")
                self._update_stats(0, 0, 0)
                self._activity_info.update_info(None)
                return

            # Update activity info card
            activity = self._activity_service.get_activity(activity_id)
            self._activity_info.update_info(activity)

            results = self._schedule_repo.list_by_activity(activity_id)
            if not results:
                set_table_empty(self._result_table, 5, "暂无排班结果（报名结束后自动生成）")
                slots = self._activity_service.list_slots(activity_id)
                total_capacity = sum(int(s.get("capacity", 0)) for s in slots)
                self._update_stats(0, len(slots), total_capacity)
                return

            users = {user["id"]: user["username"] for user in self._user_repo.list_all()}
            slots = self._activity_service.list_slots(activity_id)
            slot_map = {}
            slot_type_map = {}
            for slot in slots:
                slot_map[slot["id"]] = format_slot_name(slot)
                slot_type_raw = slot.get("slot_type", "time_slot")
                slot_type_map[slot["id"]] = {
                    "time_slot": "时段",
                    "topic": "选题",
                    "course": "课程",
                    "custom_option": "自定义",
                }.get(slot_type_raw, "其他")

            location = activity.get("location", "") if activity else ""

            self._result_table.clearSpans()
            self._result_table.setRowCount(len(results))
            for row_index, row in enumerate(results):
                user_label = users.get(row["user_id"], row["user_id"])
                slot_label = slot_map.get(row["slot_id"], row["slot_id"])
                type_label = slot_type_map.get(row["slot_id"], "-")
                self._result_table.setItem(row_index, 0, QTableWidgetItem(user_label))
                self._result_table.setItem(row_index, 1, QTableWidgetItem(slot_label))
                self._result_table.setItem(row_index, 2, QTableWidgetItem(location or "-"))
                self._result_table.setItem(row_index, 3, QTableWidgetItem(type_label))
                self._result_table.setItem(row_index, 4, QTableWidgetItem(format_datetime(row["created_at"])))

            # Update statistics
            total_capacity = sum(int(s.get("capacity", 0)) for s in slots)
            assigned_count = len(results)
            self._update_stats(assigned_count, len(slots), total_capacity)
        except Exception as exc:
            set_table_empty(self._result_table, 5, "加载失败")
            set_banner(self._message, "error", f"加载排班结果失败：{exc}")

    def _update_stats(self, assigned: int, slot_count: int, total_capacity: int) -> None:
        self._stat_assigned = self._replace_stat_card(self._stat_assigned, "已分配人数", str(assigned), "success_fg")
        self._stat_slots = self._replace_stat_card(self._stat_slots, "选项总数", str(slot_count), "accent")
        fill_rate = f"{assigned / total_capacity * 100:.1f}%" if total_capacity > 0 else "0%"
        self._stat_fill = self._replace_stat_card(self._stat_fill, "填充率", fill_rate, "warning_fg")

    def _replace_stat_card(self, old_card: _StatCard, label: str, value: str, accent: str) -> _StatCard:
        """Replace a stat card in the layout with an updated one."""
        parent_layout = old_card.parent().layout()
        # Find the stat layout (the QHBoxLayout containing the cards)
        for i in range(parent_layout.count()):
            item = parent_layout.itemAt(i)
            if item is not None and item.layout() is not None:
                sub_layout = item.layout()
                for j in range(sub_layout.count()):
                    if sub_layout.itemAt(j) and sub_layout.itemAt(j).widget() is old_card:
                        new_card = _StatCard(label, value, accent)
                        sub_layout.replaceWidget(old_card, new_card)
                        old_card.deleteLater()
                        return new_card
        # Fallback: just update the old card visually
        return old_card

    def _run(self) -> None:
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            set_banner(self._message, "error", "请选择活动")
            return

        # Confirmation dialog
        reply = QMessageBox.question(
            self,
            "确认重新排班",
            "重新排班将覆盖现有的排班结果，此操作不可撤销。\n\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        set_banner(self._message, "info", "")
        try:
            count = self._scheduling_service.run(activity_id)
            set_banner(self._message, "success", f"排班完成，共生成 {count} 条结果")
            self._load_results()
        except ValidationError as exc:
            set_banner(self._message, "error", str(exc))

    def _export(self) -> None:
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            set_banner(self._message, "error", "请选择活动")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出排班结果", "schedule.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        set_banner(self._message, "info", "")
        rows = self._schedule_repo.list_by_activity(activity_id)
        try:
            export_to_excel(rows, path)
        except Exception as exc:
            set_banner(self._message, "error", f"导出失败：{exc}")
            return
        set_banner(self._message, "success", f"导出完成：{path}")
