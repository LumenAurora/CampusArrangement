from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QDate, QDateTime, Qt
from PySide6.QtGui import QAction, QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.activity_service import ActivityService
from app.application.remote_services import RemoteSchedulingService
from app.application.scheduling_service import SchedulingService
from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import AllocationMode, ActivityType, CheckInMode, Role, SignupMode, SlotType, User
from app.infrastructure.notifications import notify
from app.infrastructure.repositories import ActivityRepository, RegistrationRepository
from app.ui.activity_guided import GuidedActivityPanel
from app.ui.activity_workflow import ActivityCard, WorkflowTimeline
from app.ui.style import FORM_LAYOUT_FLAT, FORM_LAYOUT_GUIDED, get_form_layout_mode, get_palette
from app.ui.ui_utils import (
    ItemDetailDialog,
    ModeSelector,
    SearchBox,
    StyledComboBox,
    configure_table,
    configure_tree,
    format_activity_status,
    format_datetime,
    format_slot_name,
    format_status,
    make_page_header,
    make_status_item,
    set_banner,
    set_table_empty,
    to_utc,
)


class _CapacityBar(QWidget):
    """A compact visual capacity bar colored by usage ratio."""

    def __init__(self, used: int, capacity: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._used = used
        self._capacity = capacity
        self.setFixedHeight(22)
        # 移除 setMinimumWidth(90)：原值会阻止 _slot_tree 第 7 列在窄窗口下收缩，
        # 配合 configure_tree 的 Stretch 模式，让 widget 完全自适应容器宽度。
        self.setMinimumWidth(0)

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

        self._guided_panel = None  # 仅在向导模式下初始化

        self._activity_table = QTableWidget(0, 9)
        self._activity_table.setHorizontalHeaderLabels(["ID", "名称", "报名开始", "报名截止", "名额显示", "分配策略", "地点", "状态", "操作"])
        configure_table(self._activity_table)

        # 选项列表改用 TreeWidget 以支持层级展示
        self._slot_tree = QTreeWidget()
        self._slot_tree.setHeaderLabels(["名称", "类型", "开始", "结束", "容量", "已用", "剩余", "使用率"])
        self._slot_tree.setAnimated(True)
        self._slot_tree.setExpandsOnDoubleClick(True)
        # 关键修复：原代码硬编码 8 列共 780px，窄窗口下必然横向溢出。
        # 改用 configure_tree 统一配置 Stretch + 禁用横向滚动条，列宽随容器自适应。
        configure_tree(self._slot_tree)
        # 名称列稍宽，其余列等比拉伸
        self._slot_tree.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self._slot_tree.header().resizeSection(0, 180)

        self._activity_selector = StyledComboBox()
        self._activity_selector.setMinimumWidth(180)

        self._search_box = SearchBox()
        self._search_box.textChanged.connect(self._apply_filters)
        self._all_activities: list[dict] = []

        self._init_activity_form()
        self._init_slot_form()

        self._activity_list_group = QGroupBox("活动列表")
        activity_list_layout = QVBoxLayout()
        activity_list_layout.setContentsMargins(12, 12, 12, 12)

        # 状态筛选：覆盖活动生命周期细粒度状态
        self._status_filter = StyledComboBox()
        self._status_filter.addItem("全部状态", "all")
        self._status_filter.addItem("报名中", "报名中")
        self._status_filter.addItem("报名未开始", "报名未开始")
        self._status_filter.addItem("报名已截止", "报名已截止")
        self._status_filter.addItem("签到中", "签到中")
        self._status_filter.addItem("签到未开始", "签到未开始")
        self._status_filter.addItem("签到已结束", "签到已结束")
        self._status_filter.addItem("草稿", "草稿")
        self._status_filter.addItem("待审核", "待审核")
        self._status_filter.addItem("已归档", "已归档")
        self._status_filter.currentIndexChanged.connect(self._apply_filters)

        # 时间筛选：按报名开始时间过滤
        self._time_filter = StyledComboBox()
        self._time_filter.addItem("全部时间", "all")
        self._time_filter.addItem("本周", "week")
        self._time_filter.addItem("本月", "month")
        self._time_filter.addItem("近 30 天", "30d")
        self._time_filter.addItem("近 90 天", "90d")
        self._time_filter.currentIndexChanged.connect(self._apply_filters)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索"))
        search_layout.addWidget(self._search_box, 1)
        search_layout.addWidget(QLabel("状态"))
        search_layout.addWidget(self._status_filter)
        search_layout.addWidget(QLabel("时间"))
        search_layout.addWidget(self._time_filter)
        activity_list_layout.addLayout(search_layout)

        activity_list_layout.addWidget(self._activity_table)

        self._status_btn_row = QHBoxLayout()
        self._status_btn_row.setSpacing(6)
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
        self._status_btn_row.addWidget(self._submit_review_btn)
        self._status_btn_row.addWidget(self._publish_btn)
        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setFrameShadow(QFrame.Sunken)
        sep1.setFixedWidth(1)
        p = get_palette()
        sep1.setStyleSheet(f"color: {p.border_light};")
        self._status_btn_row.addWidget(sep1)
        # Moderation group
        self._status_btn_row.addWidget(self._reject_btn)
        self._status_btn_row.addWidget(self._close_btn)
        self._status_btn_row.addWidget(self._archive_btn)
        # Spacer + separator + destructive
        self._status_btn_row.addStretch(1)
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setFrameShadow(QFrame.Sunken)
        sep2.setFixedWidth(1)
        sep2.setStyleSheet(f"color: {p.border_light};")
        self._status_btn_row.addWidget(sep2)
        self._status_btn_row.addWidget(self._delete_btn)

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

        # Left column: always use guided (workflow) layout
        p = get_palette()
        self._layout_mode = FORM_LAYOUT_GUIDED

        # ── 主内容区（卡片列表 + 工作流时间线）─────────────────
        self._right_widget = QWidget()
        self._build_right_panel(True)

        header = make_page_header("活动管理", "创建活动、配置时段与报名策略")

        # ── 顶部工具栏（创建按钮 + 搜索筛选）─────────────────
        p_tb = get_palette()
        top_toolbar = QFrame()
        top_toolbar.setStyleSheet(
            f"QFrame {{ background: {p_tb.bg_card}; border: 1px solid {p_tb.border_light}; "
            f"border-radius: 10px; }}"
        )
        tb_layout = QHBoxLayout()
        tb_layout.setContentsMargins(12, 10, 12, 10)
        tb_layout.setSpacing(12)

        create_btn = QPushButton("+ 创建活动")
        create_btn.setObjectName("primaryButton")
        create_btn.setMinimumHeight(40)
        create_btn.clicked.connect(self._open_create_dialog)
        tb_layout.addWidget(create_btn)

        tb_layout.addWidget(self._search_box, 1)
        tb_layout.addWidget(self._status_filter)
        tb_layout.addWidget(self._time_filter)
        top_toolbar.setLayout(tb_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addWidget(top_toolbar)
        layout.addWidget(self._right_widget, 1)
        self.setLayout(layout)

        self._activity_selector.currentIndexChanged.connect(self._load_slots)
        # 修复：活动列表选中后自动同步「添加选项」子页面的 _activity_selector，
        # 原代码仅更新按钮状态，用户需手动到下拉框里再选一次，体验割裂。
        self._activity_table.itemSelectionChanged.connect(self._on_activity_selection_changed)
        self._activity_table.cellDoubleClicked.connect(self._on_activity_double_clicked)
        self.refresh()

    # ═══════════════════════════════════════════════════════════
    # 左侧面板构建 / 热切换
    # ═══════════════════════════════════════════════════════════

    def _open_create_dialog(self) -> None:
        """打开创建活动弹窗（模态对话框）。"""
        dialog = QDialog(self)
        dialog.setWindowTitle("创建新活动")
        dialog.setMinimumWidth(580)
        dialog.setMinimumHeight(600)
        p = get_palette()
        dialog.setStyleSheet(f"QDialog {{ background: {p.bg_card}; }}")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 嵌入 GuidedActivityPanel
        guided = GuidedActivityPanel(
            activity_service=self._service,
            user=self._user,
            group_repo=self._group_repo,
            parent=dialog,
        )

        # 创建成功后关闭弹窗并刷新
        def _on_created() -> None:
            self.refresh()
            dialog.accept()

        guided.set_on_created(_on_created)
        layout.addWidget(guided)
        dialog.setLayout(layout)
        dialog.exec()

    def _build_right_panel(self, use_guided: bool) -> None:
        """根据模式构建右侧面板（卡片+时间线或表格+选项）。"""
        # 清除旧布局
        old_layout = self._right_widget.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
                elif item.layout():
                    # 递归清理子布局
                    self._clear_layout(item.layout())

        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(12)

        if use_guided:
            # 活动卡片 + 工作流时间线
            content_row = QHBoxLayout()
            content_row.setSpacing(12)

            # 活动卡片列表
            self._card_scroll = QScrollArea()
            self._card_scroll.setWidgetResizable(True)
            self._card_scroll.setFrameShape(QFrame.NoFrame)
            self._card_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._card_container = QWidget()
            self._card_layout = QVBoxLayout()
            self._card_layout.setContentsMargins(0, 0, 0, 0)
            self._card_layout.setSpacing(8)
            self._card_layout.addStretch()
            self._card_container.setLayout(self._card_layout)
            self._card_scroll.setWidget(self._card_container)

            card_area = QVBoxLayout()
            card_area.setSpacing(8)
            card_area.addWidget(self._card_scroll, 1)
            card_area.addLayout(self._status_btn_row)

            content_row.addLayout(card_area, 2)

            self._workflow_timeline = WorkflowTimeline()
            self._workflow_timeline.add_slot_clicked = self._on_workflow_add_slot
            self._workflow_timeline.submit_review_clicked = lambda: self._change_status("submit_review")
            self._workflow_timeline.edit_config_clicked = self._on_workflow_edit_config
            content_row.addWidget(self._workflow_timeline, 1)

            right_col.addLayout(content_row)
        else:
            # 平铺模式：原有布局
            right_col.addWidget(self._activity_list_group, 1)
            right_col.addWidget(self._slot_list_group, 1)

        self._right_widget.setLayout(right_col)

    @staticmethod
    def _clear_layout(layout) -> None:
        """递归清理布局中的所有子项。"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
            elif item.layout():
                ActivityPanel._clear_layout(item.layout())

    def _on_activity_selection_changed(self) -> None:
        """活动列表选中变化时：更新按钮状态 + 同步 _activity_selector + 更新时间线。"""
        self._update_status_buttons()
        activity_id, _ = self._get_selected_activity()
        # 更新时间线
        activity = next((a for a in self._all_activities if a["id"] == activity_id), None) if activity_id else None
        if hasattr(self, '_workflow_timeline') and activity:
            self._workflow_timeline.set_activity(activity)
        if not activity_id:
            return
        # 避免重复 setCurrentIndex 触发不必要刷新
        current_id = self._activity_selector.currentData()
        if current_id == activity_id:
            return
        for i in range(self._activity_selector.count()):
            if self._activity_selector.itemData(i) == activity_id:
                self._activity_selector.setCurrentIndex(i)
                break

    def _on_workflow_add_slot(self) -> None:
        """工作流中点击「添加时段」：弹出简洁的时段添加对话框。"""
        activity = self._workflow_timeline._activity if hasattr(self, '_workflow_timeline') else None
        if not activity:
            QMessageBox.information(self, "添加时段", "请先在左侧选择一个活动")
            return
        activity_id = activity.get("id", "")
        is_time_slot = activity.get("activity_type") != ActivityType.NON_TIME_SLOT.value

        dlg = QDialog(self)
        dlg.setWindowTitle("添加时段")
        dlg.setMinimumWidth(400)
        layout = QVBoxLayout()
        layout.setSpacing(12)

        name_edit = QLineEdit()
        name_edit.setPlaceholderText("如：周一上午")
        layout.addWidget(QLabel("名称"))
        layout.addWidget(name_edit)

        if is_time_slot:
            start = QDateTimeEdit(QDateTime.currentDateTime())
            start.setCalendarPopup(True)
            start.setDisplayFormat("yyyy-MM-dd HH:mm")
            end = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
            end.setCalendarPopup(True)
            end.setDisplayFormat("yyyy-MM-dd HH:mm")
            layout.addWidget(QLabel("开始时间"))
            layout.addWidget(start)
            layout.addWidget(QLabel("结束时间"))
            layout.addWidget(end)

        cap = QSpinBox()
        cap.setRange(1, 10000)
        cap.setValue(30)
        layout.addWidget(QLabel("容量"))
        layout.addWidget(cap)

        err = QLabel("")
        err.setStyleSheet("color: #e53e3e; font-size: 11px;")
        err.setVisible(False)
        layout.addWidget(err)

        btn_row = QHBoxLayout()
        cancel = QPushButton("取消")
        cancel.clicked.connect(dlg.reject)
        ok = QPushButton("添加")
        ok.setObjectName("primaryButton")

        def _do_add():
            name = name_edit.text().strip()
            capacity = cap.value()
            try:
                if is_time_slot:
                    s = start.dateTime().toPython()
                    e = end.dateTime().toPython()
                    if e <= s:
                        err.setText("结束时间必须晚于开始时间")
                        err.setVisible(True)
                        return
                    self._service.add_slot(
                        user=self._user, activity_id=activity_id,
                        start_time=s, end_time=e, capacity=capacity, name=name,
                    )
                else:
                    self._service.add_slot_generic(
                        user=self._user, activity_id=activity_id,
                        slot_type=SlotType.CUSTOM_OPTION, name=name,
                        capacity=capacity, metadata="",
                    )
                self.refresh()
                dlg.accept()
            except (PermissionDenied, ValidationError) as exc:
                err.setText(str(exc))
                err.setVisible(True)
            except Exception as exc:
                err.setText(f"添加失败：{exc}")
                err.setVisible(True)

        ok.clicked.connect(_do_add)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        dlg.setLayout(layout)
        dlg.exec()

    def _on_workflow_edit_config(self) -> None:
        """工作流中点击「编辑配置」：弹出编辑对话框修改活动基本信息。"""
        activity = self._workflow_timeline._activity if hasattr(self, '_workflow_timeline') else None
        if not activity:
            QMessageBox.information(self, "编辑配置", "请先在左侧选择一个活动")
            return
        activity_id = activity.get("id", "")

        dlg = QDialog(self)
        dlg.setWindowTitle("编辑活动配置")
        dlg.setMinimumWidth(450)
        layout = QVBoxLayout()
        layout.setSpacing(10)

        name_edit = QLineEdit(activity.get("name", ""))
        layout.addWidget(QLabel("活动名称"))
        layout.addWidget(name_edit)

        details_edit = QLineEdit(activity.get("details", ""))
        layout.addWidget(QLabel("活动描述"))
        layout.addWidget(details_edit)

        loc_edit = QLineEdit(activity.get("location", ""))
        layout.addWidget(QLabel("地点"))
        layout.addWidget(loc_edit)

        signup_start_str = activity.get("signup_start", "")
        signup_end_str = activity.get("signup_end", "")
        try:
            ss = datetime.fromisoformat(str(signup_start_str)) if signup_start_str else datetime.now()
            se = datetime.fromisoformat(str(signup_end_str)) if signup_end_str else datetime.now()
        except (ValueError, TypeError):
            ss = datetime.now()
            se = datetime.now()

        start_edit = QDateTimeEdit(QDateTime(ss.year, ss.month, ss.day, ss.hour, ss.minute, ss.second))
        start_edit.setCalendarPopup(True)
        start_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        end_edit = QDateTimeEdit(QDateTime(se.year, se.month, se.day, se.hour, se.minute, se.second))
        end_edit.setCalendarPopup(True)
        end_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        layout.addWidget(QLabel("报名开始时间"))
        layout.addWidget(start_edit)
        layout.addWidget(QLabel("报名截止时间"))
        layout.addWidget(end_edit)

        err = QLabel("")
        err.setStyleSheet("color: #e53e3e; font-size: 11px;")
        err.setVisible(False)
        layout.addWidget(err)

        btn_row = QHBoxLayout()
        cancel = QPushButton("取消")
        cancel.clicked.connect(dlg.reject)
        save_btn = QPushButton("保存")
        save_btn.setObjectName("primaryButton")

        def _do_save():
            name = name_edit.text().strip()
            if not name:
                err.setText("活动名称不能为空")
                err.setVisible(True)
                return
            s = start_edit.dateTime().toPython()
            e = end_edit.dateTime().toPython()
            if e <= s:
                err.setText("报名截止时间必须晚于开始时间")
                err.setVisible(True)
                return
            try:
                if not hasattr(self._service, "update_activity"):
                    raise ValidationError("当前模式下不支持编辑活动配置")
                self._service.update_activity(user=self._user, activity_id=activity_id, fields={
                    "name": name,
                    "details": details_edit.text().strip(),
                    "location": loc_edit.text().strip(),
                    "signup_start": s.isoformat(),
                    "signup_end": e.isoformat(),
                })
                self.refresh()
                dlg.accept()
            except (PermissionDenied, ValidationError) as exc:
                err.setText(str(exc))
                err.setVisible(True)
            except Exception as exc:
                err.setText(f"保存失败：{exc}")
                err.setVisible(True)

        save_btn.clicked.connect(_do_save)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        dlg.setLayout(layout)
        dlg.exec()

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
        self._allocation_mode.addItem("意愿点（99点高者优先）", AllocationMode.POINTS)
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

        # 字段级实时错误提示（默认隐藏）
        p = get_palette()
        err_style = f"color: {p.error_fg}; font-size: 11px; border: none; padding: 0 4px;"
        self._signup_err = QLabel("")
        self._signup_err.setStyleSheet(err_style)
        self._signup_err.setVisible(False)
        self._checkin_err = QLabel("")
        self._checkin_err.setStyleSheet(err_style)
        self._checkin_err.setVisible(False)
        # 时间变化即触发实时校验，无需等待点击「创建活动」
        for w in (self._signup_start, self._signup_end, self._checkin_start, self._checkin_end):
            w.dateTimeChanged.connect(self._validate_activity_form)

        self._activity_message = QLabel("")
        set_banner(self._activity_message, "info", "")
        create_btn = QPushButton("创建活动")
        create_btn.setObjectName("primaryButton")
        create_btn.clicked.connect(self._create_activity)
        # 向导模式入口：保留平铺布局为默认，另提供分步向导作为可选布局
        wizard_btn = QPushButton("向导模式创建")
        wizard_btn.setObjectName("secondaryButton")
        wizard_btn.clicked.connect(self._open_wizard)
        form_buttons = QHBoxLayout()
        form_buttons.setSpacing(8)
        form_buttons.addWidget(create_btn)
        form_buttons.addWidget(wizard_btn)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow("模式", self._activity_type)
        form.addRow("名称", self._activity_name)
        form.addRow("报名开始", self._signup_start)
        form.addRow("报名截止", self._signup_end)
        form.addRow(self._signup_err)
        form.addRow("详情", self._details)
        form.addRow("地点", self._location)
        form.addRow("名额显示", self._signup_mode)
        form.addRow("分配策略", self._allocation_mode)
        form.addRow("签到模式", self._checkin_mode)
        form.addRow("签到开始", self._checkin_start)
        form.addRow("签到截止", self._checkin_end)
        form.addRow(self._checkin_err)
        # 允许兼报多个时段/岗位（默认关闭，兼顾快速创建）
        self._allow_multiple_slots = QCheckBox("允许同一用户兼报多个时段/岗位")
        self._allow_multiple_slots.setToolTip("开启后，同一用户可报名同一活动下的多个时段或岗位；\n关闭时每用户仅可报一个时段。")
        form.addRow("兼报设置", self._allow_multiple_slots)
        # 小组限制
        self._group_selector = StyledComboBox()
        self._group_selector.addItem("公开（全体用户）", None)
        form.addRow("报名范围", self._group_selector)
        form.addRow(form_buttons)
        form.addRow(self._activity_message)

        self._activity_group = QGroupBox("创建活动")
        self._activity_group.setLayout(form)

        # 模式切换联动：选题模式（NON_TIME_SLOT）下隐藏地点/签到相关字段，
        # 因为选题无需物理到场，签到与坐标无意义。
        self._activity_type.currentIndexChanged.connect(self._update_activity_form_mode)
        self._update_activity_form_mode()

    def _validate_activity_form(self, *args) -> bool:
        """实时校验活动表单的时间字段，更新字段级错误提示并返回是否全部有效。"""
        signup_start = self._signup_start.dateTime().toPython()
        signup_end = self._signup_end.dateTime().toPython()
        signup_ok = signup_end > signup_start
        self._signup_err.setVisible(not signup_ok)
        if not signup_ok:
            self._signup_err.setText("⚠ 报名截止必须晚于报名开始")

        checkin_start = self._checkin_start.dateTime().toPython()
        checkin_end = self._checkin_end.dateTime().toPython()
        checkin_ok = True
        checkin_msg = ""
        if checkin_end <= checkin_start:
            checkin_ok = False
            checkin_msg = "⚠ 签到截止必须晚于签到开始"
        elif checkin_start < signup_start:
            checkin_ok = False
            checkin_msg = "⚠ 签到开始不应早于报名开始"
        self._checkin_err.setVisible(not checkin_ok)
        if not checkin_ok:
            self._checkin_err.setText(checkin_msg)
        return signup_ok and checkin_ok

    def _update_activity_form_mode(self) -> None:
        """根据活动模式动态联动创建活动表单字段。

        时段模式：显示全部字段（含地点、签到模式、签到开始/截止）
        选题模式：隐藏地点与签到相关字段，避免用户填写无效信息。
        """
        is_time_slot = self._activity_type.currentData() == ActivityType.TIME_SLOT
        # 需要联动的字段：(widget, label_row_widget)
        # QFormLayout 的 label 通过 labelForField 获取
        form = self._activity_group.layout()
        fields_to_toggle = [
            self._location,
            self._checkin_mode,
            self._checkin_start,
            self._checkin_end,
            self._checkin_err,
        ]
        for widget in fields_to_toggle:
            label = form.labelForField(widget)
            if label is not None:
                label.setVisible(is_time_slot)
            widget.setVisible(is_time_slot)
        # 切换到选题模式时清空无关字段，避免脏数据残留
        if not is_time_slot:
            self._location.clear()
            self._checkin_mode.setCurrentIndex(0)  # 重置为手动签到
            self._checkin_err.setVisible(False)

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

        # 时段时间字段级实时校验
        p = get_palette()
        err_style = f"color: {p.error_fg}; font-size: 11px; border: none; padding: 0 4px;"
        self._slot_time_err = QLabel("")
        self._slot_time_err.setStyleSheet(err_style)
        self._slot_time_err.setVisible(False)
        for w in (self._slot_start, self._slot_end):
            w.dateTimeChanged.connect(self._validate_slot_form)

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
        self._slot_form.addRow(self._slot_time_err)
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
        # 切换模式后触发一次实时校验，更新时段错误提示可见性
        self._slot_time_err.setVisible(is_time_slot_mode and not self._validate_slot_form())

    def _validate_slot_form(self, *args) -> bool:
        """实时校验时段表单的时间字段，返回是否有效。"""
        start = self._slot_start.dateTime().toPython()
        end = self._slot_end.dateTime().toPython()
        ok = end > start
        self._slot_time_err.setVisible(not ok)
        if not ok:
            self._slot_time_err.setText("⚠ 结束时间不能早于开始时间")
        return ok

    def refresh(self) -> None:
        self._all_activities = self._service.list_activities()
        self._apply_filters()
        # 更新小组选择器 — 区分向导/平铺模式
        if self._group_repo and self._guided_panel is not None:
            guided_gs = getattr(self._guided_panel, "_group_selector", None)
            if guided_gs is not None:
                self._update_group_selector(guided_gs)
        elif self._group_repo:
            self._update_group_selector(self._group_selector)

    def _update_group_selector(self, selector) -> None:
        """安全更新小组下拉选择器，保留当前选中项。"""
        try:
            current = selector.currentData()
        except RuntimeError:
            return  # Widget 已被销毁
        selector.blockSignals(True)
        selector.clear()
        selector.addItem("公开（全体用户）", None)
        for g in self._group_repo.list_all():
            selector.addItem(g["name"], g["id"])
        if current:
            for i in range(selector.count()):
                if selector.itemData(i) == current:
                    selector.setCurrentIndex(i)
                    break
        selector.blockSignals(False)

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
            AllocationMode.POINTS.value: "意愿点",
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

    def _apply_filters(self, *args) -> None:
        """统一应用搜索 + 状态 + 时间筛选。

        - 搜索：按名称/详情模糊匹配（不区分大小写）
        - 状态：按 format_activity_status 输出的细粒度状态匹配
        - 时间：按报名开始时间过滤（本周/本月/近 N 天）

        空状态文案区分「无任何活动」与「有活动但筛选后为空」，便于用户调整筛选条件。
        """
        query = self._search_box.text().strip().lower()
        status_filter = self._status_filter.currentData() or "all"
        time_filter = self._time_filter.currentData() or "all"

        now = datetime.now(timezone.utc)
        time_window_start: datetime | None = None
        if time_filter == "week":
            # 本周：从本周周一开始（与日历复制弹窗一致）
            today = now.date()
            monday = today - timedelta(days=today.weekday())
            time_window_start = datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc)
        elif time_filter == "month":
            time_window_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif time_filter in ("30d", "90d"):
            days = 30 if time_filter == "30d" else 90
            time_window_start = now - timedelta(days=days)

        def _matches(activity: dict) -> bool:
            # 搜索匹配
            if query:
                name = activity.get("name", "").lower()
                details = activity.get("details", "").lower()
                if query not in name and query not in details:
                    return False
            # 状态匹配
            if status_filter != "all":
                if format_activity_status(activity) != status_filter:
                    return False
            # 时间匹配（按报名开始时间）
            if time_window_start is not None:
                signup_start = activity.get("signup_start")
                if not signup_start:
                    return False
                try:
                    if to_utc(signup_start) < time_window_start:
                        return False
                except (ValueError, TypeError):
                    return False
            return True

        activities = [a for a in self._all_activities if _matches(a)]

        if not activities:
            # 区分两种空状态：完全没活动 vs 筛选条件导致为空
            if not self._all_activities:
                empty_msg = "暂无活动，请先创建活动"
            else:
                empty_msg = "无符合筛选条件的活动，请调整搜索/筛选条件"
            set_table_empty(self._activity_table, 9, empty_msg)
            self._activity_selector.blockSignals(True)
            self._activity_selector.clear()
            self._activity_selector.blockSignals(False)
            self._load_slots()
            return
        self._activity_table.clearSpans()
        self._activity_table.setRowCount(len(activities))
        # 保留当前选中的活动 ID，refresh 后恢复选择，避免跳回列表第一个
        preserved_activity_id = self._activity_selector.currentData()
        self._activity_selector.blockSignals(True)
        self._activity_selector.clear()
        p = get_palette()
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
                AllocationMode.POINTS.value: "意愿点",
            }.get(allocation_mode, "志愿优先")
            self._activity_table.setItem(row_index, 4, QTableWidgetItem(signup_mode_text))
            self._activity_table.setItem(row_index, 5, QTableWidgetItem(allocation_text))
            # Location with prominent styling
            location_text = activity.get("location") or "-"
            location_label = QLabel(f"📍 {location_text}")
            location_label.setStyleSheet(
                f"color: {p.accent}; font-weight: 500; padding: 2px 6px; "
                f"background: {p.accent_soft}; border-radius: 4px;"
            )
            location_label.setAlignment(Qt.AlignCenter)
            self._activity_table.setCellWidget(row_index, 6, location_label)
            # 状态徽章：dot + 文字（参考 HTML 设计）
            status_text = format_activity_status(activity)
            status_item = make_status_item(status_text)
            self._activity_table.setItem(row_index, 7, status_item)
            # 行内操作：复制 + 更多下拉（详情/归档/删除）
            self._activity_table.setCellWidget(row_index, 8, self._make_row_actions(activity, p))

            # 活动选择器显示模式标签
            at = activity.get("activity_type", "time_slot")
            mode_tag = "时段" if at == ActivityType.TIME_SLOT.value else "选项"
            self._activity_selector.addItem(f"{activity['name']} [{mode_tag}]", activity["id"])
        # 恢复之前选中的活动，refresh 后用户仍停在原活动上
        if preserved_activity_id:
            for i in range(self._activity_selector.count()):
                if self._activity_selector.itemData(i) == preserved_activity_id:
                    self._activity_selector.setCurrentIndex(i)
                    break
        self._activity_selector.blockSignals(False)
        # 显式触发一次 _load_slots，因为重建期间信号被阻塞，未自动加载
        self._load_slots()

        self._activity_table.setColumnHidden(0, True)
        self._update_status_buttons()

        # 渲染活动卡片列表
        self._render_activity_cards(activities)

    def _render_activity_cards(self, activities: list[dict]) -> None:
        """在向导模式下渲染活动卡片列表。"""
        if not hasattr(self, '_card_layout'):
            return
        # 清除旧卡片
        self._clear_layout(self._card_layout)

        if not activities:
            p = get_palette()
            empty = QLabel("暂无活动，请先创建活动")
            empty.setStyleSheet(f"color: {p.text_tertiary}; font-size: 13px; padding: 24px; border: none;")
            empty.setAlignment(Qt.AlignCenter)
            self._card_layout.insertWidget(0, empty)
            self._card_layout.addStretch()
            return

        for i, a in enumerate(activities):
            card = ActivityCard(a)
            card.mousePressEvent = lambda e, aid=a["id"]: self._on_card_clicked(aid)
            self._card_layout.insertWidget(i, card)
        self._card_layout.addStretch()

    def _on_card_clicked(self, activity_id: str) -> None:
        """活动卡片点击：在表格中选中对应行并更新工作流时间线。"""
        # 同步表格选择
        for row in range(self._activity_table.rowCount()):
            item = self._activity_table.item(row, 0)
            if item and item.text() == activity_id:
                self._activity_table.selectRow(row)
                break
        # 更新工作流时间线
        activity = next((a for a in self._all_activities if a["id"] == activity_id), None)
        if hasattr(self, '_workflow_timeline') and activity:
            self._workflow_timeline.set_activity(activity)

    def _select_activity_by_id(self, activity_id: str) -> None:
        """在活动选择器中选中指定 ID 的活动并加载其时段。

        用于「创建活动 → 自动聚焦新活动 → 引导添加时段」的分步流程。
        若选择器中找不到（如被筛选条件排除），则不改动当前选择。
        """
        for i in range(self._activity_selector.count()):
            if self._activity_selector.itemData(i) == activity_id:
                # setCurrentIndex 会触发 currentIndexChanged → _load_slots
                self._activity_selector.setCurrentIndex(i)
                return

    def _make_row_actions(self, activity: dict, p) -> QWidget:
        """构建行内操作区：复制 + 更多下拉（详情/归档/删除）。"""
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(6)

        copy_btn = QPushButton("复制")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.setProperty("activity_id", activity["id"])
        copy_btn.clicked.connect(self._on_copy_activity)
        layout.addWidget(copy_btn)

        more_btn = QToolButton()
        more_btn.setObjectName("secondaryButton")
        more_btn.setText("更多")
        more_btn.setPopupMode(QToolButton.InstantPopup)
        more_btn.setStyleSheet(
            f"QToolButton#secondaryButton::menu-indicator {{ image: none; }}"
        )
        more_menu = QMenu(more_btn)
        more_menu.setStyleSheet(
            f"QMenu {{ background: {p.bg_card}; color: {p.text_primary}; "
            f"border: 1px solid {p.border_light}; border-radius: 8px; padding: 4px; }}"
            f"QMenu::item {{ padding: 6px 24px 6px 16px; border-radius: 4px; }}"
            f"QMenu::item:selected {{ background: {p.accent_soft}; }}"
        )
        detail_action = QAction("查看详情", more_menu)
        detail_action.triggered.connect(lambda _=False, aid=activity["id"]: self._open_detail_by_id(aid))
        more_menu.addAction(detail_action)
        more_menu.addSeparator()
        archive_action = QAction("归档", more_menu)
        archive_action.triggered.connect(lambda _=False, aid=activity["id"]: self._archive_activity_by_id(aid))
        more_menu.addAction(archive_action)
        delete_action = QAction("删除", more_menu)
        delete_action.triggered.connect(lambda _=False, aid=activity["id"]: self._delete_activity_by_id(aid))
        more_menu.addAction(delete_action)
        more_btn.setMenu(more_menu)
        layout.addWidget(more_btn)

        container.setLayout(layout)
        return container

    def _open_detail_by_id(self, activity_id: str) -> None:
        activity = next((a for a in self._all_activities if a["id"] == activity_id), None)
        if not activity:
            return
        signup_mode_text = "实时" if activity.get("signup_mode") == SignupMode.REALTIME.value else "非实时"
        allocation_mode = activity.get("allocation_mode", AllocationMode.GREEDY.value)
        allocation_text = {
            AllocationMode.GREEDY.value: "志愿优先",
            AllocationMode.FIRST_COME.value: "先到先得",
            AllocationMode.LOTTERY.value: "抽签",
            AllocationMode.POINTS.value: "意愿点",
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

    def _archive_activity_by_id(self, activity_id: str) -> None:
        """通过行内菜单归档指定活动。"""
        activity = next((a for a in self._all_activities if a["id"] == activity_id), None)
        if not activity:
            return
        try:
            self._service.archive_activity(user=self._user, activity_id=activity_id)
            self.refresh()
            set_banner(self._activity_message, "success", f"活动「{activity['name']}」已归档")
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._activity_message, "error", str(exc))
        except Exception as exc:
            set_banner(self._activity_message, "error", f"归档失败：{exc}")

    def _delete_activity_by_id(self, activity_id: str) -> None:
        """通过行内菜单删除指定活动（带确认）。"""
        activity = next((a for a in self._all_activities if a["id"] == activity_id), None)
        name = activity["name"] if activity else activity_id
        confirm = QMessageBox.question(
            self, "确认删除", f"确定删除活动「{name}」吗？此操作不可撤销。"
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._service.delete_activity(activity_id=activity_id, user=self._user)
            self.refresh()
            set_banner(self._activity_message, "success", "活动已删除")
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._activity_message, "error", str(exc))
        except Exception as exc:
            set_banner(self._activity_message, "error", f"删除失败：{exc}")


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
            name = self._activity_name.text().strip()
            if not name:
                set_banner(self._activity_message, "error", "活动名称不能为空")
                return
            # 实时校验不通过时阻止创建（错误提示已在字段旁显示）
            if not self._validate_activity_form():
                set_banner(self._activity_message, "error", "请修正表单中的时间错误后再创建")
                return
            signup_start = self._signup_start.dateTime().toPython()
            signup_end = self._signup_end.dateTime().toPython()
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
                allow_multiple_slots=self._allow_multiple_slots.isChecked(),
            )
            self.refresh()
            # 创建活动后自动聚焦新活动，并引导用户继续添加时段/选项
            self._select_activity_by_id(activity.id)
            next_step = "请在下方继续添加时段/选项"
            set_banner(self._activity_message, "success", f"已创建活动：{activity.name}，{next_step}")
            self._activity_name.clear()
            self._details.clear()
            self._location.clear()
            from datetime import datetime, timedelta
            now = datetime.now()
            self._signup_start.setDateTime(now)
            self._signup_end.setDateTime(now + timedelta(days=1))
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._activity_message, "error", str(exc))
        except Exception as exc:
            set_banner(self._activity_message, "error", f"创建失败：{exc}")

    def _open_wizard(self) -> None:
        """打开向导式创建活动对话框。

        向导将表单字段分步收集：基本信息 → 报名设置 → 签到设置(可选) → 确认创建。
        选题模式自动跳过签到设置步骤。
        """
        dialog = ActivityWizardDialog(self._service, self._user, self._group_repo, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()
            activity = dialog.created_activity
            if activity:
                set_banner(self._activity_message, "success", f"已创建活动：{activity.name}")

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
        sel = self._activity_table.selectionModel()
        if sel is None:
            return None, None
        rows = sel.selectedRows()
        if not rows:
            return None, None
        row = rows[0].row()
        id_item = self._activity_table.item(row, 0)
        name_item = self._activity_table.item(row, 1)
        if not id_item or not name_item:
            return None, None
        return id_item.text(), name_item.text()

    def _get_selected_activity_status(self) -> str:
        sel = self._activity_table.selectionModel()
        if sel is None:
            return ""
        rows = sel.selectedRows()
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
            # 修复活动状态管理 bug：原代码只要 status==open 就启用「结束报名」，
            # 但「报名已截止」（signup_end 过期）派生状态下点击结束报名会触发
            # OPEN→CLOSED 跃迁 + 排班，UI 状态从「报名已截止」直接跳到「签到已结束」，
            # 语义割裂。改为：报名已截止时禁用「结束报名」（报名已自然截止，无需手动关闭）。
            activity_id, _ = self._get_selected_activity()
            derived_status = ""
            if activity_id:
                activity = self._service.get_activity(activity_id)
                if activity:
                    derived_status = format_activity_status(activity)
            if derived_status == "报名已截止":
                self._close_btn.setEnabled(False)
                self._close_btn.setToolTip("报名已自然截止，无需手动结束报名")
            else:
                self._close_btn.setEnabled(True)
                self._close_btn.setToolTip("")
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
            AllocationMode.POINTS.value: "意愿点",
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

            # 时段模式：实时校验时间，结束时间不得早于开始时间
            if is_time_slot_mode and not self._validate_slot_form():
                set_banner(self._slot_message, "error", "结束时间不能早于开始时间")
                return

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


class ActivityWizardDialog(QDialog):
    """向导式创建活动对话框。

    分步收集活动信息，降低表单视觉密度：
    Step 1: 基本信息（模式、名称、详情）
    Step 2: 报名设置（报名开始/截止、名额显示、分配策略、报名范围）
    Step 3: 签到设置（地点、签到模式、签到开始/截止）— 仅时段模式，选题模式自动跳过
    Step 4: 确认并创建（汇总信息 + 创建按钮）

    与平铺模式共享同一个 ActivityService.create_activity 调用，
    两种布局收集的数据完全等价。
    """

    def __init__(self, activity_service: ActivityService, user: User, group_repo=None, parent=None) -> None:
        super().__init__(parent)
        self._service = activity_service
        self._user = user
        self._group_repo = group_repo
        self.created_activity = None
        self.setWindowTitle("向导式创建活动")
        self.setMinimumWidth(540)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # 步骤指示器
        self._step_label = QLabel()
        self._step_label.setObjectName("pageTitle")
        layout.addWidget(self._step_label)

        # 步骤容器
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_step1())
        self._stack.addWidget(self._build_step2())
        self._stack.addWidget(self._build_step3())
        self._stack.addWidget(self._build_step4())
        layout.addWidget(self._stack, 1)

        # 错误提示
        self._message = QLabel("")
        set_banner(self._message, "info", "")
        layout.addWidget(self._message)

        # 导航按钮
        nav = QHBoxLayout()
        nav.addStretch()
        self._prev_btn = QPushButton("上一步")
        self._prev_btn.setObjectName("secondaryButton")
        self._prev_btn.clicked.connect(self._go_prev)
        self._next_btn = QPushButton("下一步")
        self._next_btn.setObjectName("primaryButton")
        self._next_btn.clicked.connect(self._go_next)
        nav.addWidget(self._prev_btn)
        nav.addWidget(self._next_btn)
        layout.addLayout(nav)

        self.setLayout(layout)
        self._activity_type.currentIndexChanged.connect(self._on_type_changed)
        self._stack.currentChanged.connect(self._on_step_changed)
        self._go_step(0)

    def _build_step1(self) -> QWidget:
        page = QWidget()
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._activity_type = ModeSelector()
        self._activity_type.addItem("活动报名（时段模式）", ActivityType.TIME_SLOT)
        self._activity_type.addItem("选课/选题（非时段模式）", ActivityType.NON_TIME_SLOT)

        self._name = QLineEdit()
        self._name.setPlaceholderText("例如：志愿服务（图书馆）")

        self._details = QLineEdit()
        self._details.setPlaceholderText("简要说明活动内容与要求")

        form.addRow("活动模式", self._activity_type)
        form.addRow("活动名称", self._name)
        form.addRow("活动详情", self._details)
        page.setLayout(form)
        return page

    def _build_step2(self) -> QWidget:
        page = QWidget()
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._signup_start = QDateTimeEdit(QDateTime.currentDateTime())
        self._signup_start.setCalendarPopup(True)
        self._signup_start.setDisplayFormat("yyyy-MM-dd HH:mm")

        self._signup_end = QDateTimeEdit(QDateTime.currentDateTime().addDays(1))
        self._signup_end.setCalendarPopup(True)
        self._signup_end.setDisplayFormat("yyyy-MM-dd HH:mm")

        self._signup_mode = ModeSelector()
        self._signup_mode.addItem("实时显示名额", SignupMode.REALTIME)
        self._signup_mode.addItem("非实时显示名额", SignupMode.BLIND)

        self._allocation_mode = ModeSelector()
        self._allocation_mode.addItem("志愿优先(贪心)", AllocationMode.GREEDY)
        self._allocation_mode.addItem("先到先得", AllocationMode.FIRST_COME)
        self._allocation_mode.addItem("抽签随机", AllocationMode.LOTTERY)
        self._allocation_mode.addItem("意愿点（99点高者优先）", AllocationMode.POINTS)

        self._group_selector = StyledComboBox()
        self._group_selector.addItem("公开（全体用户）", None)
        if self._group_repo:
            for g in self._group_repo.list_all():
                self._group_selector.addItem(g["name"], g["id"])

        form.addRow("报名开始", self._signup_start)
        form.addRow("报名截止", self._signup_end)
        form.addRow("名额显示", self._signup_mode)
        form.addRow("分配策略", self._allocation_mode)
        form.addRow("报名范围", self._group_selector)
        page.setLayout(form)
        return page

    def _build_step3(self) -> QWidget:
        page = QWidget()
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._location = QLineEdit()
        self._location.setPlaceholderText("例如：图书馆一楼大厅")

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

        form.addRow("地点", self._location)
        form.addRow("签到模式", self._checkin_mode)
        form.addRow("签到开始", self._checkin_start)
        form.addRow("签到截止", self._checkin_end)
        page.setLayout(form)
        return page

    def _build_step4(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(8)
        title = QLabel("请确认以下信息：")
        p = get_palette()
        title.setStyleSheet(f"font-weight: 600; color: {p.text_primary}; margin-bottom: 8px;")
        layout.addWidget(title)

        self._summary_label = QLabel()
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet(
            f"background: {p.bg_input}; border: 1px solid {p.border_light}; "
            f"border-radius: 8px; padding: 12px; color: {p.text_secondary};"
        )
        layout.addWidget(self._summary_label)
        layout.addStretch()
        page.setLayout(layout)
        return page

    def _is_time_slot(self) -> bool:
        return self._activity_type.currentData() == ActivityType.TIME_SLOT

    def _on_type_changed(self) -> None:
        # 选题模式隐藏签到设置步骤的页面内容
        is_ts = self._is_time_slot()
        self._stack.widget(2).setVisible(is_ts)
        # 如果当前停留在被隐藏的签到设置页，自动导航到下一步
        if not is_ts and self._stack.currentIndex() == 2:
            self._go_step(3)

    def _on_step_changed(self, index: int) -> None:
        is_ts = self._is_time_slot()
        total = 4 if is_ts else 3
        step_titles = ["基本信息", "报名设置", "签到设置", "确认创建"]
        # 选题模式跳过签到设置页，步骤编号映射：0→1, 1→2, 3→3
        if not is_ts and index == 3:
            display_index = 3
        elif not is_ts and index == 2:
            display_index = 3  # 选题模式不应到达此页，设置兜底值
        else:
            display_index = index + 1
        title = step_titles[index] if index < len(step_titles) else ""
        if not is_ts and index == 3:
            title = "确认创建"
        self._step_label.setText(f"第 {display_index}/{total} 步：{title}")

        self._prev_btn.setEnabled(index > 0)
        if index == self._stack.count() - 1:
            self._next_btn.setText("创建活动")
        else:
            self._next_btn.setText("下一步")

        # 在确认页更新汇总信息
        if index == self._stack.count() - 1:
            self._update_summary()

    def _update_summary(self) -> None:
        is_ts = self._is_time_slot()
        mode_text = "时段模式" if is_ts else "选题模式"
        alloc_text = {
            AllocationMode.GREEDY.value: "志愿优先",
            AllocationMode.FIRST_COME.value: "先到先得",
            AllocationMode.LOTTERY.value: "抽签",
            AllocationMode.POINTS.value: "意愿点",
        }.get(self._allocation_mode.currentData(), "—")
        signup_text = "实时" if self._signup_mode.currentData() == SignupMode.REALTIME else "非实时"
        lines = [
            f"<b>模式：</b> {mode_text}",
            f"<b>名称：</b> {self._name.text() or '—'}",
            f"<b>详情：</b> {self._details.text() or '—'}",
            f"<b>报名：</b> {self._signup_start.dateTime().toString('yyyy-MM-dd HH:mm')} ~ {self._signup_end.dateTime().toString('yyyy-MM-dd HH:mm')}",
            f"<b>名额显示：</b> {signup_text}",
            f"<b>分配策略：</b> {alloc_text}",
        ]
        if is_ts:
            lines.extend([
                f"<b>地点：</b> {self._location.text() or '—'}",
                f"<b>签到模式：</b> {self._checkin_mode.currentText()}",
                f"<b>签到时间：</b> {self._checkin_start.dateTime().toString('yyyy-MM-dd HH:mm')} ~ {self._checkin_end.dateTime().toString('yyyy-MM-dd HH:mm')}",
            ])
        self._summary_label.setText("<br>".join(lines))

    def _go_step(self, index: int) -> None:
        # 选题模式跳过签到设置页（index=2）
        if not self._is_time_slot() and index == 2:
            index = 3
        self._stack.setCurrentIndex(index)

    def _go_next(self) -> None:
        current = self._stack.currentIndex()
        if current == self._stack.count() - 1:
            self._create_activity()
            return
        # 跳过选题模式下的签到设置页
        next_index = current + 1
        if not self._is_time_slot() and next_index == 2:
            next_index = 3
        self._go_step(next_index)

    def _go_prev(self) -> None:
        current = self._stack.currentIndex()
        if current == 0:
            return
        prev_index = current - 1
        # 跳过选题模式下的签到设置页
        if not self._is_time_slot() and prev_index == 2:
            prev_index = 1
        self._go_step(prev_index)

    def _create_activity(self) -> None:
        try:
            set_banner(self._message, "info", "")
            is_time_slot = self._is_time_slot()
            self.created_activity = self._service.create_activity(
                user=self._user,
                name=self._name.text().strip(),
                signup_start=self._signup_start.dateTime().toPython(),
                signup_end=self._signup_end.dateTime().toPython(),
                details=self._details.text().strip(),
                signup_mode=SignupMode(self._signup_mode.currentData()),
                allocation_mode=AllocationMode(self._allocation_mode.currentData()),
                location=self._location.text().strip() if is_time_slot else "",
                activity_type=ActivityType(self._activity_type.currentData()),
                checkin_mode=self._checkin_mode.currentData() if is_time_slot else CheckInMode.MANUAL.value,
                checkin_start=self._checkin_start.dateTime().toPython() if is_time_slot else None,
                checkin_end=self._checkin_end.dateTime().toPython() if is_time_slot else None,
                group_id=self._group_selector.currentData(),
            )
            self.accept()
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))
