"""小组管理面板 — 参考 group_management_ui_redesign.html 设计语言。

布局：
  顶部：统计卡片行（小组总数/成员总数/待审批/活跃小组）
  中部：工具栏（搜索 + 创建小组按钮）+ 主内容
  主内容：QSplitter（小组列表 + 选中成员）
  右侧：待审批申请卡片列表
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QTextEdit,
)

from app.application.group_service import GroupService
from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import MemberStatus, User
from app.infrastructure.repositories import GroupRepository
from app.ui.style import get_palette
from app.ui.ui_utils import (
    SearchBox,
    configure_table,
    make_page_header,
    set_banner,
    set_table_empty,
)


def _p():
    return get_palette()


class _StatCard(QFrame):
    """统计卡片 — 对应 HTML 的 bg-white rounded-xl border shadow-sm + icon。"""

    def __init__(self, title: str, value: str, icon_symbol: str = "", parent=None) -> None:
        super().__init__(parent)
        p = _p()
        self.setStyleSheet(
            f"QFrame {{ background: {p.bg_card}; border: 1px solid {p.border_light}; "
            f"border-radius: 10px; }}"
        )
        layout = QHBoxLayout()
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 左侧：文字区
        text_area = QVBoxLayout()
        text_area.setSpacing(4)
        self._title = QLabel(title)
        self._title.setStyleSheet(f"color: {p.text_tertiary}; font-size: 12px; font-weight: 500; border: none;")
        self._value = QLabel(value)
        self._value.setStyleSheet(f"color: {p.text_primary}; font-size: 24px; font-weight: 700; border: none;")
        self._subtitle = QLabel("")
        self._subtitle.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px; border: none;")
        text_area.addWidget(self._title)
        text_area.addWidget(self._value)
        text_area.addWidget(self._subtitle)
        layout.addLayout(text_area, 1)

        # 右侧：图标区
        icon_lbl = QLabel(icon_symbol)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setStyleSheet(
            f"background: {p.accent_soft}; border-radius: 8px; font-size: 18px; border: none;"
        )
        layout.addWidget(icon_lbl)
        self.setLayout(layout)

    def set_value(self, text: str) -> None:
        self._value.setText(text)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)


class GroupAdminPanel(QWidget):
    def __init__(self, group_service: GroupService, group_repo: GroupRepository, user: User) -> None:
        super().__init__()
        self._service = group_service
        self._repo = group_repo
        self._user = user
        self._selected_group_id: str | None = None
        self._all_groups: list[dict] = []
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        p = _p()
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = make_page_header("小组管理", "创建、管理小组，审核成员申请")
        layout.addWidget(header)

        # ── 统计卡片行 ──────────────────────────────────
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._stat_total = _StatCard("小组总数", "0", "👥")
        self._stat_members = _StatCard("成员总数", "0", "👤")
        self._stat_pending = _StatCard("待审批", "0", "⏳")
        self._stat_active = _StatCard("活跃小组", "0", "🔥")
        for card in [self._stat_total, self._stat_members, self._stat_pending, self._stat_active]:
            stats_row.addWidget(card)
        layout.addLayout(stats_row)

        # ── 工具栏 ──────────────────────────────────────
        toolbar = QFrame()
        toolbar.setStyleSheet(
            f"QFrame {{ background: {p.bg_card}; border: 1px solid {p.border_light}; "
            f"border-radius: 10px; padding: 10px 14px; }}"
        )
        t_layout = QHBoxLayout()
        t_layout.setContentsMargins(10, 8, 10, 8)
        t_layout.setSpacing(12)

        self._search_box = SearchBox()
        self._search_box.textChanged.connect(self._apply_group_filters)

        self._create_btn = QPushButton("+ 创建小组")
        self._create_btn.setObjectName("primaryButton")
        self._create_btn.clicked.connect(self._toggle_create_form)

        t_layout.addWidget(self._search_box, 1)
        self._delete_btn = QPushButton("删除选中")
        self._delete_btn.setObjectName("dangerButton")
        self._delete_btn.clicked.connect(self._delete_group)
        self._delete_btn.setEnabled(False)
        t_layout.addWidget(self._delete_btn)
        t_layout.addWidget(self._create_btn)
        toolbar.setLayout(t_layout)
        layout.addWidget(toolbar)

        # ── 创建小组（可折叠，默认隐藏） ──────────────────
        self._create_section = QWidget()
        self._create_section.setVisible(False)
        create_layout = QVBoxLayout()
        create_layout.setContentsMargins(0, 0, 0, 0)
        create_layout.setSpacing(6)

        self._create_group_box = QGroupBox("创建新小组")
        inner = QVBoxLayout()
        inner.setContentsMargins(12, 12, 12, 12)
        inner.setSpacing(8)

        form = QFormLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("小组名称（必填）")
        self._name_input.setMinimumHeight(36)
        self._desc_input = QTextEdit()
        self._desc_input.setPlaceholderText("小组描述（可选）")
        self._desc_input.setMaximumHeight(60)
        form.addRow("名称 *", self._name_input)
        form.addRow("描述", self._desc_input)
        inner.addLayout(form)

        btn_row = QHBoxLayout()
        self._submit_create_btn = QPushButton("创建")
        self._submit_create_btn.setObjectName("primaryButton")
        self._submit_create_btn.clicked.connect(self._create_group)
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self._toggle_create_form)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._submit_create_btn)
        inner.addLayout(btn_row)

        self._create_msg = QLabel("")
        set_banner(self._create_msg, "info", "")
        inner.addWidget(self._create_msg)
        self._create_group_box.setLayout(inner)
        create_layout.addWidget(self._create_group_box)
        self._create_section.setLayout(create_layout)
        layout.addWidget(self._create_section)

        # ── 主内容：小组列表 + 成员详情 + 待审批 ──────────
        content = QHBoxLayout()
        content.setSpacing(12)

        # 左侧：小组列表 + 成员表
        left_splitter = QSplitter(Qt.Vertical)

        # 小组列表
        group_widget = QWidget()
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_label = QLabel("小组")
        group_label.setStyleSheet(f"font-weight: 600; color: {p.text_secondary}; font-size: 12px; border: none;")
        group_layout.addWidget(group_label)
        self._group_table = QTableWidget(0, 5)
        self._group_table.setHorizontalHeaderLabels(["ID", "名称", "描述", "成员", "创建者"])
        configure_table(self._group_table)
        self._group_table.setColumnHidden(0, True)
        self._group_table.itemSelectionChanged.connect(self._on_group_selected)
        group_layout.addWidget(self._group_table, 1)
        group_widget.setLayout(group_layout)
        left_splitter.addWidget(group_widget)

        # 成员表
        member_widget = QWidget()
        member_layout = QVBoxLayout()
        member_layout.setContentsMargins(0, 0, 0, 0)

        self._member_label = QLabel("请先选择一个小组")
        self._member_label.setStyleSheet(f"color: {p.text_tertiary}; font-size: 12px; font-weight: 500; border: none;")
        member_layout.addWidget(self._member_label)

        self._member_table = QTableWidget(0, 5)
        self._member_table.setHorizontalHeaderLabels(["用户名", "角色", "状态", "加入时间", "操作"])
        configure_table(self._member_table)
        member_layout.addWidget(self._member_table, 1)
        member_widget.setLayout(member_layout)
        left_splitter.addWidget(member_widget)
        left_splitter.setSizes([300, 250])

        content.addWidget(left_splitter, 2)

        # 右侧：待审批卡片列表
        right_panel = QWidget()
        right_panel.setMinimumWidth(240)
        right_panel.setMaximumWidth(360)
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # 待审批标题 + 计数徽章
        pending_header_row = QHBoxLayout()
        pending_header_row.setSpacing(8)
        pending_title = QLabel("待审批申请")
        pending_title.setStyleSheet(f"font-weight: 700; font-size: 13px; color: {p.text_primary}; border: none;")
        self._pending_badge = QLabel("0")
        self._pending_badge.setFixedSize(22, 22)
        self._pending_badge.setAlignment(Qt.AlignCenter)
        self._pending_badge.setStyleSheet(
            f"background: {p.accent_soft}; color: {p.accent}; border-radius: 11px; "
            f"font-size: 11px; font-weight: 700; border: none;"
        )
        pending_header_row.addWidget(pending_title)
        pending_header_row.addWidget(self._pending_badge)
        pending_header_row.addStretch()
        right_layout.addLayout(pending_header_row)

        self._pending_scroll = QScrollArea()
        self._pending_scroll.setWidgetResizable(True)
        self._pending_scroll.setFrameShape(QFrame.NoFrame)
        self._pending_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._pending_list = QWidget()
        self._pending_list_layout = QVBoxLayout()
        self._pending_list_layout.setContentsMargins(0, 0, 0, 0)
        self._pending_list_layout.setSpacing(8)
        self._pending_list_layout.addStretch()
        self._pending_list.setLayout(self._pending_list_layout)
        self._pending_scroll.setWidget(self._pending_list)
        right_layout.addWidget(self._pending_scroll, 1)

        # 快速操作卡片（参考 HTML 的 gradient card）
        quick_card = QFrame()
        quick_card.setStyleSheet(
            f"QFrame {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {p.accent}, stop:1 {p.accent_hover}); border-radius: 12px; }}"
        )
        quick_layout = QVBoxLayout()
        quick_layout.setContentsMargins(14, 14, 14, 14)
        quick_layout.setSpacing(8)
        q_title = QLabel("快速操作")
        q_title.setStyleSheet("font-weight: 700; font-size: 13px; color: white; border: none;")
        q_sub = QLabel("常用管理功能快捷入口")
        q_sub.setStyleSheet(f"color: rgba(255,255,255,0.75); font-size: 11px; border: none;")
        quick_layout.addWidget(q_title)
        quick_layout.addWidget(q_sub)
        for label in ["📤 导出成员名单", "📧 群发通知", "📊 查看统计报表"]:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,0.12); color: white; border: none; "
                "border-radius: 8px; padding: 10px 12px; text-align: left; font-size: 12px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.22); }"
            )
            quick_layout.addWidget(btn)
        quick_card.setLayout(quick_layout)
        right_layout.addWidget(quick_card)
        right_panel.setLayout(right_layout)
        content.addWidget(right_panel, 1)

        layout.addLayout(content, 1)
        self.setLayout(layout)

    # ═══════════════════════════════════════════════════════════
    # 创建表单切换
    # ═══════════════════════════════════════════════════════════

    def _toggle_create_form(self) -> None:
        visible = not self._create_section.isVisible()
        self._create_section.setVisible(visible)
        self._create_btn.setText("关闭" if visible else "+ 创建小组")

    # ═══════════════════════════════════════════════════════════
    # 数据刷新
    # ═══════════════════════════════════════════════════════════

    def refresh(self) -> None:
        self._load_groups()
        self._load_pending()
        self._update_stats()
        if self._selected_group_id:
            self._load_members(self._selected_group_id)

    def _update_stats(self) -> None:
        """更新统计卡片。"""
        groups = self._all_groups
        total = len(groups)
        total_members = 0
        pending_total = 0
        for g in groups:
            members = self._repo.list_members(g["id"])
            total_members += len([m for m in members if m.get("status") == "approved"])
            pending_total += len([m for m in members if m.get("status") == "pending"])

        self._stat_total.set_value(str(total))
        self._stat_members.set_value(str(total_members))
        self._stat_pending.set_value(str(pending_total))
        self._stat_pending.set_subtitle("需要尽快处理" if pending_total > 0 else "")
        self._stat_active.set_value(str(total))
        self._stat_active._title.setText("小组总数")

        # 同步更新待审批徽章
        pending_list = self._service.list_pending_applications(self._user)
        self._pending_badge.setText(str(len(pending_list)))
        self._pending_badge.setVisible(len(pending_list) > 0)

    def _apply_group_filters(self, *args) -> None:
        """搜索过滤小组列表。"""
        query = self._search_box.text().strip().lower()
        groups = self._all_activities if hasattr(self, '_all_activities') else self._all_groups
        if query:
            groups = [g for g in self._all_groups
                      if query in g.get("name", "").lower()
                      or query in g.get("description", "").lower()]
        self._render_group_table(groups)

    def _render_group_table(self, groups: list[dict]) -> None:
        self._group_table.clearSpans()
        if not groups:
            set_table_empty(self._group_table, 5, "暂无符合条件的小组")
            return
        self._group_table.setRowCount(len(groups))
        p = _p()
        for i, g in enumerate(groups):
            self._group_table.setItem(i, 0, QTableWidgetItem(g["id"]))
            # 名称列 — 首字母头像
            name = g.get("name", "?")
            name_item = QTableWidgetItem(f"  {name}")
            self._group_table.setItem(i, 1, name_item)
            self._group_table.setItem(i, 2, QTableWidgetItem(g.get("description", "")))
            members = self._repo.list_members(g["id"])
            approved = len([m for m in members if m.get("status") == "approved"])
            self._group_table.setItem(i, 3, QTableWidgetItem(f"{approved} 人"))
            owner = g.get("owner_id", "")
            self._group_table.setItem(i, 4, QTableWidgetItem(owner[:8] + "..."))

    # ═══════════════════════════════════════════════════════════
    # 小组列表
    # ═══════════════════════════════════════════════════════════

    def _load_groups(self) -> None:
        self._all_groups = self._service.list_all_groups()
        self._render_group_table(self._all_groups)

    # ═══════════════════════════════════════════════════════════
    # 成员管理
    # ═══════════════════════════════════════════════════════════

    def _load_members(self, group_id: str) -> None:
        members = self._repo.list_members(group_id)
        self._member_table.clearSpans()
        if not members:
            set_table_empty(self._member_table, 5, "暂无成员")
            return
        self._member_table.setRowCount(len(members))
        p = _p()
        for i, m in enumerate(members):
            self._member_table.setItem(i, 0, QTableWidgetItem(m.get("username", "-")))
            # 角色徽章
            role = m.get("role", "member")
            role_text = "组长" if role == "admin" else "成员"
            role_color = "#7c3aed" if role == "admin" else "#2563eb"
            role_item = QTableWidgetItem(role_text)
            role_item.setForeground(QTableWidgetItem().foreground())  # use default
            self._member_table.setItem(i, 1, role_item)
            # 状态徽章
            status = m.get("status", "")
            status_map = {"pending": ("待审批", _p().warning_fg), "approved": ("已通过", _p().success_fg), "rejected": ("已拒绝", _p().error_fg)}
            s_text, s_color = status_map.get(status, (status, _p().text_tertiary))
            self._member_table.setItem(i, 2, QTableWidgetItem(s_text))
            self._member_table.setItem(i, 3, QTableWidgetItem(m.get("joined_at", "")[:16]))
            # 操作按钮
            if m.get("status") == "pending":
                approve_btn = QPushButton("通过")
                approve_btn.setObjectName("primaryButton")
                approve_btn.clicked.connect(lambda checked, uid=m["user_id"]: self._approve_member(uid))
                self._member_table.setCellWidget(i, 4, approve_btn)
            elif m.get("user_id") != self._selected_group_owner_id:
                remove_btn = QPushButton("移除")
                remove_btn.setObjectName("dangerButton")
                remove_btn.clicked.connect(lambda checked, uid=m["user_id"]: self._remove_member(uid))
                self._member_table.setCellWidget(i, 4, remove_btn)
            else:
                self._member_table.setItem(i, 4, QTableWidgetItem("创建者"))

    # ═══════════════════════════════════════════════════════════
    # 待审批 — 卡片式列表（参考 HTML）
    # ═══════════════════════════════════════════════════════════

    def _load_pending(self) -> None:
        """加载待审批申请为卡片式列表 — 使用 setParent(None) 即时清除，避免 deleteLater 延迟导致视觉残留。"""
        pending = self._service.list_pending_applications(self._user)

        # 关键修复：用 setParent(None) + hide 即时清空，而非 deleteLater
        for i in reversed(range(self._pending_list_layout.count())):
            item = self._pending_list_layout.itemAt(i)
            if item.widget():
                item.widget().hide()
                item.widget().setParent(None)
            elif item.layout():
                # 清空子布局（如果有的话）
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().hide()
                        sub.widget().setParent(None)
            self._pending_list_layout.removeItem(item)

        # 更新徽章
        self._pending_badge.setText(str(len(pending)))
        self._pending_badge.setVisible(len(pending) > 0)

        if not pending:
            p = _p()
            empty = QLabel("暂无待审批申请 ✓")
            empty.setStyleSheet(f"color: {p.text_tertiary}; font-size: 12px; padding: 16px; border: none;")
            self._pending_list_layout.insertWidget(0, empty)
            self._pending_list_layout.addStretch()
            return

        p = _p()
        for i, app in enumerate(pending):
            card = self._build_pending_card(app, p)
            self._pending_list_layout.insertWidget(i, card)
        self._pending_list_layout.addStretch()

    def _build_pending_card(self, app: dict, p) -> QFrame:
        """构建单张待审批卡片。"""
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {p.bg_card}; border: 1px solid {p.border_light}; "
            f"border-radius: 8px; padding: 10px 12px; }}"
        )
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(6)

        # 用户信息行
        info_row = QHBoxLayout()
        info_row.setSpacing(8)

        avatar = QLabel(app.get("username", "?")[0].upper())
        avatar.setFixedSize(32, 32)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            f"background: {p.accent}; color: {p.text_on_accent}; border-radius: 16px; "
            f"font-weight: 700; font-size: 13px; border: none;"
        )
        name_label = QLabel(app.get("username", "-"))
        name_label.setStyleSheet(f"font-weight: 600; font-size: 12px; color: {p.text_primary}; border: none;")
        group_label = QLabel(f"→ {app.get('group_name', '-')}")
        group_label.setStyleSheet(f"color: {p.accent}; font-size: 11px; border: none;")

        info_row.addWidget(avatar)
        self_info = QVBoxLayout()
        self_info.setSpacing(1)
        self_info.addWidget(name_label)
        self_info.addWidget(group_label)
        info_row.addLayout(self_info, 1)
        card_layout.addLayout(info_row)

        # 申请理由
        reason = app.get("reason", "") or "—"
        reason_lbl = QLabel(reason)
        reason_lbl.setWordWrap(True)
        reason_lbl.setStyleSheet(
            f"color: {p.text_secondary}; font-size: 11px; background: {p.bg_input}; "
            f"border-radius: 4px; padding: 4px 6px; border: none;"
        )
        card_layout.addWidget(reason_lbl)

        # 操作按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        approve_btn = QPushButton("通过")
        approve_btn.setObjectName("primaryButton")
        approve_btn.clicked.connect(
            lambda checked, gid=app["group_id"], uid=app["user_id"]: self._approve_pending(gid, uid))
        reject_btn = QPushButton("拒绝")
        reject_btn.setObjectName("dangerButton")
        reject_btn.clicked.connect(
            lambda checked, gid=app["group_id"], uid=app["user_id"]: self._reject_pending(gid, uid))
        btn_row.addWidget(approve_btn)
        btn_row.addWidget(reject_btn)
        card_layout.addLayout(btn_row)

        card.setLayout(card_layout)
        return card

    # ═══════════════════════════════════════════════════════════
    # 操作
    # ═══════════════════════════════════════════════════════════

    def _create_group(self) -> None:
        try:
            set_banner(self._create_msg, "info", "")
            name = self._name_input.text().strip()
            desc = self._desc_input.toPlainText().strip()
            self._service.create_group(self._user, name, desc)
            set_banner(self._create_msg, "success", f"小组 '{name}' 创建成功")
            self._name_input.clear()
            self._desc_input.clear()
            self._toggle_create_form()
            self.refresh()
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._create_msg, "error", str(exc))

    def _delete_group(self) -> None:
        if not self._selected_group_id:
            return
        reply = QMessageBox.question(self, "确认删除", "确定要删除此小组吗？所有成员将被移除。",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            self._service.delete_group(self._user, self._selected_group_id)
            self._selected_group_id = None
            self._selected_group_owner_id = None
            self._delete_btn.setEnabled(False)
            self._member_label.setText("请先选择一个小组")
            set_table_empty(self._member_table, 5, "")
            self.refresh()
        except (PermissionDenied, ValidationError) as exc:
            QMessageBox.warning(self, "错误", str(exc))

    def _on_group_selected(self) -> None:
        rows = self._group_table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        group_id = self._group_table.item(row, 0).text()
        group = self._repo.get(group_id)
        if group:
            self._selected_group_id = group_id
            self._selected_group_owner_id = group.get("owner_id", "")
            self._delete_btn.setEnabled(True)
            member_count = len(self._repo.list_members(group_id))
            self._member_label.setText(f"小组：{group['name']}（{member_count} 位成员）")
            self._load_members(group_id)

    def _approve_member(self, member_user_id: str) -> None:
        try:
            self._service.approve_member(self._user, self._selected_group_id, member_user_id)
            self._load_members(self._selected_group_id)
            self._load_pending()
            self._update_stats()
        except (PermissionDenied, ValidationError) as exc:
            QMessageBox.warning(self, "错误", str(exc))

    def _remove_member(self, member_user_id: str) -> None:
        try:
            self._service.remove_member(self._user, self._selected_group_id, member_user_id)
            self._load_members(self._selected_group_id)
            self._update_stats()
        except (PermissionDenied, ValidationError) as exc:
            QMessageBox.warning(self, "错误", str(exc))

    def _approve_pending(self, group_id: str, user_id: str) -> None:
        try:
            self._service.approve_member(self._user, group_id, user_id)
            self._load_pending()
            self._update_stats()
            if self._selected_group_id == group_id:
                self._load_members(group_id)
        except (PermissionDenied, ValidationError) as exc:
            QMessageBox.warning(self, "错误", str(exc))

    def _reject_pending(self, group_id: str, user_id: str) -> None:
        try:
            self._service.reject_member(self._user, group_id, user_id)
            self._load_pending()
            self._update_stats()
        except (PermissionDenied, ValidationError) as exc:
            QMessageBox.warning(self, "错误", str(exc))
