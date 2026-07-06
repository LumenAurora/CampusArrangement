"""活动工作流面板 — 参考 activity_workflow_ui.html 设计。

活动以卡片形式展示，每张卡片包含渐变图标、状态徽章、工作流进度条。
右侧展示选中活动的详细信息与垂直时间线工作流。
"""

from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import ActivityStatus
from app.ui.style import get_palette
from app.ui.ui_utils import configure_table, format_activity_status, format_datetime


def _p():
    return get_palette()


# ── 活动卡片（替换表格行） ────────────────────────────────────

class ActivityCard(QFrame):
    """单张活动卡片 — 对应 HTML 的 workflow-card。"""

    def __init__(self, activity: dict, reg_count: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._activity = activity
        self._reg_count = reg_count
        self._selected = False
        self._build()

    def _build(self) -> None:
        p = _p()
        a = self._activity
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"ActivityCard {{ background: {p.bg_card}; border: 1px solid {p.border_light}; "
            f"border-radius: 12px; padding: 14px 16px; }}"
            f"ActivityCard[selected=true] {{ border: 2px solid {p.accent}; background: {p.accent_soft}; }}"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ── 顶部：图标 + 名称 + 状态 ──────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        # 渐变图标
        name = a.get("name", "?")
        icon_char = name.strip()[0] if name.strip() else "?"
        icon = QLabel(icon_char)
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignCenter)
        # 根据状态选色
        status = format_activity_status(a)
        icon_bg = "#6366f1" if "草稿" in status else "#10b981" if "报名" in status or "签到" in status else "#f59e0b"
        icon.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {icon_bg},stop:1 {p.accent}); "
            f"color: white; border-radius: 12px; font-weight: 700; font-size: 15px; border: none;"
        )
        top_row.addWidget(icon)

        # 名称 + 描述
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"font-weight: 600; font-size: 13px; color: {p.text_primary}; border: none;")
        at = a.get("activity_type", "time_slot")
        mode_text = "时段模式" if at == "time_slot" else "选项模式"
        desc_lbl = QLabel(f"{a.get('details', '') or '无描述'} · {mode_text}")
        desc_lbl.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px; border: none;")
        text_col.addWidget(name_lbl)
        text_col.addWidget(desc_lbl)
        top_row.addLayout(text_col, 1)

        # 状态徽章
        status_colors = {
            "草稿": ("#fef3c7", "#92400e"),
            "待审核": ("#dbeafe", "#1e40af"),
            "报名中": ("#dcfce7", "#166534"),
            "签到中": ("#dcfce7", "#166534"),
            "已结束": ("#f3f4f6", "#4b5563"),
            "已归档": ("#f3f4f6", "#9ca3af"),
            "报名未开始": ("#dbeafe", "#1e40af"),
            "报名已截止": ("#f3f4f6", "#4b5563"),
        }
        bg, fg = status_colors.get(status, ("#f3f4f6", "#4b5563"))
        badge = QLabel(status)
        badge.setStyleSheet(
            f"background: {bg}; color: {fg}; border: 1px solid {fg}20; border-radius: 10px; "
            f"padding: 2px 8px; font-size: 11px; font-weight: 600;"
        )
        badge.setFixedHeight(22)
        top_row.addWidget(badge)
        layout.addLayout(top_row)

        # ── 工作流进度条 ─────────────────────────────────
        workflow = self._build_workflow_bar(a, p)
        layout.addWidget(workflow)

        # ── 底部信息行 ────────────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(16)
        ss = (a.get("signup_start") or "")[:16]
        se = (a.get("signup_end") or "")[:16]
        time_lbl = QLabel(f"🗓 报名: {ss} → {se}" if ss else "🗓 未设置")
        time_lbl.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px; border: none;")
        cap_lbl = QLabel(f"👤 {self._reg_count} 人已报名")
        cap_lbl.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px; border: none;")
        bottom_row.addWidget(time_lbl)
        bottom_row.addWidget(cap_lbl)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        self.setLayout(layout)

    def _build_workflow_bar(self, a: dict, p) -> QWidget:
        """构建工作流进度条 — 5 步骤：编辑→提交→发布→进行→结束。"""
        status = a.get("status", "")
        steps = [
            ("draft,pending_review", "编辑", "✏"),
            ("draft,pending_review", "提交审核", "⏳"),
            ("open", "发布报名", "📤"),
            ("open", "进行中", "▶"),
            ("closed,archived", "结束归档", "🏁"),
        ]

        bar = QWidget()
        bar_layout = QHBoxLayout()
        bar_layout.setContentsMargins(8, 0, 8, 0)
        bar_layout.setSpacing(0)

        # 计算当前处于第几步
        step_map = {"draft": 0, "pending_review": 1, "open": 3, "closed": 4, "archived": 4}
        current_step = step_map.get(status, 0)

        for i, (active_statuses, label, icon) in enumerate(steps):
            is_active = i <= current_step
            is_current = i == current_step

            dot_size = 24
            if is_active:
                dot_bg = p.accent
                dot_border = p.accent
                dot_text = "✓" if i < current_step else str(i + 1)
            else:
                dot_bg = "transparent"
                dot_border = p.border_light
                dot_text = str(i + 1)

            dot = QLabel(dot_text)
            dot.setFixedSize(dot_size, dot_size)
            dot.setAlignment(Qt.AlignCenter)
            dot_color = p.text_on_accent if is_active else p.text_tertiary
            dot.setStyleSheet(
                f"background: {dot_bg}; border: 2px solid {dot_border}; border-radius: {dot_size // 2}px; "
                f"color: {dot_color}; font-size: 10px; font-weight: 700;"
            )
            bar_layout.addWidget(dot)

            if i < len(steps) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFixedHeight(2)
                line.setMinimumWidth(20)
                line_bg = p.accent if i < current_step else p.border_light
                line.setStyleSheet(f"background: {line_bg}; border: none;")
                line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                bar_layout.addWidget(line)

        bar.setLayout(bar_layout)
        return bar

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    @property
    def activity_id(self) -> str:
        return self._activity.get("id", "")

    @property
    def activity(self) -> dict:
        return self._activity


# ── 工作流时间线（右侧面板） ──────────────────────────────────

class WorkflowTimeline(QWidget):
    """垂直工作流时间线 — 对应 HTML 右侧 step-item 列表。"""

    add_slot_clicked = None  # 由父面板设置回调
    submit_review_clicked = None
    edit_config_clicked = None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._activity: dict | None = None
        self._build()

    def _build(self) -> None:
        p = _p()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 头部
        self._header = QWidget()
        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(4)

        self._status_badge = QLabel("")
        self._name_label = QLabel("请选择一个活动")
        self._name_label.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {p.text_primary}; border: none;")
        self._desc_label = QLabel("")
        self._desc_label.setStyleSheet(f"color: {p.text_tertiary}; font-size: 12px; border: none;")
        header_layout.addWidget(self._status_badge)
        header_layout.addWidget(self._name_label)
        header_layout.addWidget(self._desc_label)
        self._header.setLayout(header_layout)
        self._header.setStyleSheet(
            f"QWidget {{ background: {p.accent_soft}; border: none; "
            f"border-top-left-radius: 10px; border-top-right-radius: 10px; }}"
        )
        layout.addWidget(self._header)

        # 步骤容器
        self._steps_widget = QWidget()
        self._steps_layout = QVBoxLayout()
        self._steps_layout.setContentsMargins(16, 12, 16, 12)
        self._steps_layout.setSpacing(0)
        self._steps_widget.setLayout(self._steps_layout)
        self._steps_widget.setStyleSheet(f"background: {p.bg_card}; border: none;")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self._steps_widget)
        layout.addWidget(scroll, 1)

        # 配置卡片
        self._config_card = self._build_config_card()
        layout.addWidget(self._config_card)

        self.setLayout(layout)

    def _build_config_card(self) -> QWidget:
        p = _p()
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {p.bg_card}; border-top: 1px solid {p.border_light}; "
            f"border-bottom-left-radius: 10px; border-bottom-right-radius: 10px; }}"
        )
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(8)

        title = QLabel("活动配置")
        title.setStyleSheet(f"font-weight: 600; font-size: 12px; color: {p.text_primary}; border: none;")
        layout.addWidget(title)

        self._config_labels: dict[str, QLabel] = {}
        for key in ["报名开始", "报名截止", "名额显示", "分配策略", "签到模式", "地点"]:
            row = QHBoxLayout()
            row.setSpacing(4)
            k_lbl = QLabel(key)
            k_lbl.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px; border: none;")
            v_lbl = QLabel("-")
            v_lbl.setStyleSheet(f"color: {p.text_primary}; font-size: 11px; border: none;")
            row.addWidget(k_lbl)
            row.addStretch()
            row.addWidget(v_lbl)
            layout.addLayout(row)
            self._config_labels[key] = v_lbl

        edit_btn = QPushButton("✏ 编辑配置")
        edit_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {p.border_light}; "
            f"border-radius: 6px; padding: 6px; font-size: 11px; color: {p.accent}; }}"
            f"QPushButton:hover {{ background: {p.accent_soft}; }}"
        )
        edit_btn.clicked.connect(self._on_edit_config)
        layout.addWidget(edit_btn)
        card.setLayout(layout)
        return card

    def set_activity(self, activity: dict | None) -> None:
        self._activity = activity
        p = _p()
        if not activity:
            self._name_label.setText("请选择一个活动")
            self._desc_label.setText("")
            self._status_badge.setText("")
            self._clear_steps()
            return

        name = activity.get("name", "-")
        self._name_label.setText(name)
        self._desc_label.setText(f"{activity.get('details', '') or '无描述'}")

        status = format_activity_status(activity)
        status_colors = {
            "草稿": ("#fef3c7", "#92400e"), "待审核": ("#dbeafe", "#1e40af"),
            "报名中": ("#dcfce7", "#166534"), "签到中": ("#dcfce7", "#166534"),
        }
        bg, fg = status_colors.get(status, ("#f3f4f6", "#4b5563"))
        self._status_badge.setText(status)
        self._status_badge.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 6px; padding: 2px 8px; "
            f"font-size: 11px; font-weight: 600; border: none;"
        )

        self._build_steps(activity)
        self._update_config(activity)

    def _build_steps(self, activity: dict) -> None:
        self._clear_steps()
        p = _p()
        status = activity.get("status", "draft")
        s = activity.get("status", "draft")

        step_defs = [
            ("create", "创建活动", "已填写活动基本信息", ["draft", "pending_review", "open", "closed", "archived"]),
            ("slots", "添加时段", "必须添加至少一个时段", ["draft", "pending_review", "open", "closed", "archived"]),
            ("review", "提交审核", "完成时段配置后可提交审核", ["pending_review", "open", "closed", "archived"]),
            ("publish", "发布活动", "审核通过后即可发布", ["open", "closed", "archived"]),
            ("end", "结束报名", "报名截止后自动结束", ["closed", "archived"]),
        ]

        # 确定当前活动处于哪个步骤：从最后一个步骤向前找第一个 active 的
        current_key = None
        for key, _title, _desc, active_in in reversed(step_defs):
            if s in active_in:
                current_key = key
                break

        for i, (key, title, desc, active_in) in enumerate(step_defs):
            is_active = s in active_in
            is_current = is_active and key == current_key
            step = self._build_step(i + 1, key, title, desc, is_active, is_current, p)
            self._steps_layout.addWidget(step)

        self._steps_layout.addStretch()

    def _build_step(self, num: int, key: str, title: str, desc: str, active: bool, current: bool, p) -> QWidget:
        step = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(12)

        # 左侧竖线 + 圆点
        left_col = QVBoxLayout()
        left_col.setSpacing(0)

        dot_size = 28
        if active:
            dot_bg = p.accent if not current else p.accent
            dot_border = p.accent
            dot_text = "✓" if not current else str(num)
            dot_color = p.text_on_accent
        else:
            dot_bg = "transparent"
            dot_border = p.border_light
            dot_text = str(num)
            dot_color = p.text_tertiary

        dot = QLabel(dot_text)
        dot.setFixedSize(dot_size, dot_size)
        dot.setAlignment(Qt.AlignCenter)
        dot.setStyleSheet(
            f"background: {dot_bg}; border: 2px solid {dot_border}; border-radius: {dot_size // 2}px; "
            f"color: {dot_color}; font-size: 12px; font-weight: 700;"
        )
        left_col.addWidget(dot)

        # 竖线
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFixedWidth(2)
        line.setMinimumHeight(20)
        line_bg = p.accent if active else p.border_light
        line.setStyleSheet(f"background: {line_bg}; border: none;")
        left_col.addWidget(line, 1)
        left_col.setAlignment(dot, Qt.AlignHCenter)
        left_col.setAlignment(line, Qt.AlignHCenter)

        layout.addLayout(left_col)

        # 右侧文字
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        opacity = "" if active else "opacity: 0.5;"
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"font-weight: 600; font-size: 13px; color: {p.text_primary}; {opacity} border: none;")
        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(f"color: {p.text_tertiary}; font-size: 11px; {opacity} border: none;")
        text_col.addWidget(title_lbl)
        text_col.addWidget(desc_lbl)

        if current and key in ("slots", "review"):
            btn = QPushButton("添加时段" if key == "slots" else "提交审核")
            btn.setStyleSheet(
                f"QPushButton {{ background: {p.accent}; color: white; border: none; border-radius: 6px; "
                f"padding: 4px 10px; font-size: 11px; }}"
                f"QPushButton:hover {{ background: {p.accent_hover}; }}"
            )
            if key == "slots":
                btn.clicked.connect(lambda: self._on_add_slot())
            else:
                btn.clicked.connect(lambda: self._on_submit_review())
            text_col.addWidget(btn)

        layout.addLayout(text_col, 1)
        step.setLayout(layout)
        return step

    def _update_config(self, activity: dict) -> None:
        alloc_map = {"greedy": "志愿优先", "first_come": "先到先得", "lottery": "抽签", "points": "意愿点"}
        self._config_labels.get("报名开始", QLabel("-")).setText((activity.get("signup_start") or "-")[:16])
        self._config_labels.get("报名截止", QLabel("-")).setText((activity.get("signup_end") or "-")[:16])
        sm = activity.get("signup_mode", "")
        self._config_labels.get("名额显示", QLabel("-")).setText("实时" if sm == "realtime" else "非实时")
        self._config_labels.get("分配策略", QLabel("-")).setText(alloc_map.get(activity.get("allocation_mode", ""), "-"))
        self._config_labels.get("签到模式", QLabel("-")).setText(activity.get("checkin_mode", "manual"))
        self._config_labels.get("地点", QLabel("-")).setText(activity.get("location") or "未设置")

    def _clear_steps(self) -> None:
        while self._steps_layout.count() > 0:
            item = self._steps_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().setParent(None)

    def _on_add_slot(self) -> None:
        if callable(self.add_slot_clicked):
            self.add_slot_clicked()

    def _on_submit_review(self) -> None:
        if callable(self.submit_review_clicked):
            self.submit_review_clicked()

    def _on_edit_config(self) -> None:
        if callable(self.edit_config_clicked):
            self.edit_config_clicked()
