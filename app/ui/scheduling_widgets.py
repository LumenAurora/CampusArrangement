from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
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
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, set_banner, set_table_empty, format_status


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

        self._activity_selector = QComboBox()
        self._activity_selector.setMinimumWidth(220)
        self._message = QLabel("")
        set_banner(self._message, "info", "")
        run_btn = QPushButton("执行排班")
        run_btn.clicked.connect(self._run)
        export_btn = QPushButton("导出排班结果")
        export_btn.clicked.connect(self._export)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow("活动", self._activity_selector)
        form.addRow(run_btn)
        export_btn.setObjectName("secondaryButton")
        form.addRow(export_btn)
        form.addRow(self._message)

        self._result_table = QTableWidget(0, 3)
        self._result_table.setHorizontalHeaderLabels(["用户", "时段", "生成时间"])
        configure_table(self._result_table)

        form_group = QGroupBox("排班操作")
        form_layout = QVBoxLayout()
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.addLayout(form)
        form_group.setLayout(form_layout)

        table_group = QGroupBox("排班结果")
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.addWidget(self._result_table)
        table_group.setLayout(table_layout)

        run_btn.setObjectName("primaryButton")

        header = make_page_header("排班管理", "执行排班并导出结果")

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(16)
        body_layout.addWidget(form_group, 1)
        body_layout.addWidget(table_group, 2)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addLayout(body_layout)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        activities = self._activity_service.list_activities()
        self._activity_selector.clear()
        for activity in activities:
            status_text = format_status(activity.get("status", "draft"))
            self._activity_selector.addItem(f"{activity['name']} ({status_text})", activity["id"])
        self._load_results()

    def _load_results(self) -> None:
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            set_table_empty(self._result_table, 3, "请选择活动")
            return
        results = self._schedule_repo.list_by_activity(activity_id)
        if not results:
            set_table_empty(self._result_table, 3, "暂无排班结果")
            return
        users = {user["id"]: user["username"] for user in self._user_repo.list_all()}
        slots = self._activity_service.list_slots(activity_id)
        slot_map = {
            slot["id"]: f"{format_datetime(slot['start_time'])} - {format_datetime(slot['end_time'])}"
            for slot in slots
        }
        self._result_table.setRowCount(len(results))
        for row_index, row in enumerate(results):
            user_label = users.get(row["user_id"], row["user_id"])
            slot_label = slot_map.get(row["slot_id"], row["slot_id"])
            self._result_table.setItem(row_index, 0, QTableWidgetItem(user_label))
            self._result_table.setItem(row_index, 1, QTableWidgetItem(slot_label))
            self._result_table.setItem(row_index, 2, QTableWidgetItem(format_datetime(row["created_at"])))

    def _run(self) -> None:
        activity_id = self._activity_selector.currentData()
        if not activity_id:
            set_banner(self._message, "error", "请选择活动")
            return
        reply = QMessageBox.question(
            self,
            "确认排班",
            "确定要执行排班吗？\n此操作将根据报名记录生成排班结果。",
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
        export_to_excel(rows, path)
        set_banner(self._message, "success", "导出完成")
