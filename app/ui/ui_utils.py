from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from app.ui.style import get_palette


def configure_table(table: QTableWidget) -> None:
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    table.verticalHeader().setDefaultSectionSize(40)
    # 关键：禁用横向滚动条。Stretch 模式下若 cell widget 顶出宽度，
    # 默认 ScrollBarAsNeeded 会冒出滚动条，导致整页可左右滑动（系统性布局 bug 根因）。
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Stretch)
    header.setCascadingSectionResizes(True)


def configure_tree(tree: QTreeWidget) -> None:
    """QTreeWidget 的自适应配置，与 configure_table 对齐。

    关键修复：原 _slot_tree 硬编码 8 列共 780px，窄窗口下必然出现横向滚动条。
    改为 Stretch + 禁用横向滚动条，让列宽随容器自适应。
    """
    tree.setAlternatingRowColors(True)
    tree.setSelectionBehavior(QAbstractItemView.SelectRows)
    tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tree.setRootIsDecorated(False)
    tree.setUniformRowHeights(True)
    tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    header = tree.header()
    header.setSectionResizeMode(QHeaderView.Stretch)
    header.setStretchLastSection(True)
    header.setCascadingSectionResizes(True)


def make_page_header(title: str, subtitle: str | None = None) -> QWidget:
    container = QWidget()
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 4)
    layout.setSpacing(4)
    title_label = QLabel(title)
    title_label.setObjectName("pageTitle")
    layout.addWidget(title_label)
    if subtitle:
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("pageSubtitle")
        layout.addWidget(subtitle_label)
    container.setLayout(layout)
    return container


def format_datetime(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    return dt.strftime("%Y-%m-%d %H:%M")


def format_slot_name(slot: dict) -> str:
    """Format a slot dict into a human-readable label.

    时间格式与 format_datetime 保持一致（含年份），避免年份显示不一致。
    """
    name = slot.get("name")
    if name:
        return name
    start = slot.get("start_time")
    end = slot.get("end_time")
    if start and end:
        try:
            s = datetime.fromisoformat(str(start))
            e = datetime.fromisoformat(str(end))
            # 同日只显示一次日期，跨日显示完整起止
            if s.date() == e.date():
                return f"{s.strftime('%Y-%m-%d %H:%M')} ~ {e.strftime('%H:%M')}"
            return f"{s.strftime('%Y-%m-%d %H:%M')} ~ {e.strftime('%Y-%m-%d %H:%M')}"
        except ValueError:
            pass
    return str(slot.get("id", "—"))


def format_status(status_str: str) -> str:
    mapping = {
        "open": "报名中",
        "closed": "报名已结束",
        "archived": "已归档",
        "draft": "草稿",
        "pending_review": "待审核",
        "pending": "待处理",
        "confirmed": "已确认",
        "assigned": "已分配",
        "cancelled": "已取消",
        "not_assigned": "未中签",
        "checked_in": "已签到",
        "absent": "缺勤",
    }
    return mapping.get(status_str, status_str)


def to_utc(value: str | datetime) -> datetime:
    """将时间值转为UTC-aware datetime。

    无时区信息(naive)的时间视为本地时间，通过 astimezone 正确转换为 UTC。
    有时区信息(aware)的时间也统一转换为 UTC，确保所有比较使用同一时区。

    这是整个应用中时间解析的唯一标准入口。
    """
    dt = datetime.fromisoformat(str(value)) if isinstance(value, str) else value
    return dt.astimezone(timezone.utc)


def to_local(value: str | datetime) -> datetime:
    """将时间值转为本地时区-aware datetime，用于 UI 展示。

    统一入口：先经 to_utc 归一化（naive 视为本地时间），再 astimezone() 转回本地，
    保证 UI 看到的是用户所在时区的「墙上时间」，而非 UTC。
    """
    return to_utc(value).astimezone()


def safe_to_utc(value: str | datetime | None) -> datetime | None:
    """安全的 to_utc：传入 None 或非法字符串返回 None，避免上层异常。

    用于 UI 展示场景，单个字段格式异常不应拖垮整页渲染。
    """
    if value is None or value == "":
        return None
    try:
        return to_utc(value)
    except (ValueError, TypeError):
        return None


def format_activity_status(activity: dict) -> str:
    """根据活动状态和时间，返回细粒度的状态文字。

    活动生命周期：报名前 → 报名中 → 报名结束签到前 → 签到中 → 签到结束 → 已归档
    """
    status = activity.get("status", "draft")

    if status == "draft":
        return "草稿"
    if status == "pending_review":
        return "待审核"
    if status == "archived":
        return "已归档"

    if status == "open":
        now = datetime.now(timezone.utc)
        signup_start = activity.get("signup_start")
        signup_end = activity.get("signup_end")
        if signup_start:
            start = safe_to_utc(signup_start)
            if start and now < start:
                return "报名未开始"
        if signup_end:
            end = safe_to_utc(signup_end)
            if end and now > end:
                return "报名已截止"
        return "报名中"

    if status == "closed":
        # 人工提前结束签到：最高优先级，直接返回"签到已结束"
        if activity.get("checkin_closed"):
            return "签到已结束"
        now = datetime.now(timezone.utc)
        checkin_start = activity.get("checkin_start")
        checkin_end = activity.get("checkin_end")
        # 调整判断顺序：先看签到是否已开始，再看是否已结束。
        # 原逻辑直接判 checkin_end 过期就返回"签到已结束"，
        # 但若 checkin_start 未设置或未到，应优先返回"签到未开始"，
        # 否则会出现"刚关闭报名就显示签到已结束"的语义跳跃。
        if checkin_start:
            start = safe_to_utc(checkin_start)
            if start and now < start:
                return "签到未开始"
        if checkin_end:
            end = safe_to_utc(checkin_end)
            if end and now > end:
                # 仅当签到已开始（或未设开始时间但结束时间已过）才判为"签到已结束"
                if not checkin_start or (start is not None and now >= start):
                    return "签到已结束"
        return "签到中"

    return format_status(status)


_banner_timers: dict[int, "QTimer"] = {}


def set_banner(label: QLabel, kind: str, text: str, auto_dismiss: bool | None = None) -> None:
    """更新 banner 文案与样式。

    默认 toast 行为：success/info 在 2.5 秒后自动消失，error 持久保留直到下次操作。
    显式传入 ``auto_dismiss`` 可覆盖默认行为。

    若 label 已有挂载的自动消失计时器，会先取消，避免旧计时器误清新文案。
    计时器以 label 为父对象，label 销毁时计时器同步销毁；
    此处对 stop() 做异常兜底，避免 label 销毁后 id 复用导致 RuntimeError。
    """
    mapping = {
        "success": "bannerSuccess",
        "error": "bannerError",
        "info": "bannerInfo",
    }
    label.setObjectName(mapping.get(kind, "bannerInfo"))
    label.setText(text)
    label.setVisible(bool(text))
    label.style().unpolish(label)
    label.style().polish(label)

    label_id = id(label)
    existing = _banner_timers.pop(label_id, None)
    if existing is not None:
        try:
            existing.stop()
        except RuntimeError:
            # 旧 label 已销毁、计时器随之销毁，stop 失败可忽略
            pass

    should_dismiss = auto_dismiss if auto_dismiss is not None else kind in ("success", "info")
    if text and should_dismiss:
        timer = QTimer(label)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: _clear_banner(label))
        timer.start(2500)
        _banner_timers[label_id] = timer


def _clear_banner(label: QLabel) -> None:
    """清空 banner 文案与样式，并移除对应的自动消失计时器。"""
    label_id = id(label)
    existing = _banner_timers.pop(label_id, None)
    if existing is not None:
        try:
            existing.stop()
        except RuntimeError:
            pass
    try:
        label.setObjectName("bannerInfo")
        label.setText("")
        label.setVisible(False)
        label.style().unpolish(label)
        label.style().polish(label)
    except RuntimeError:
        # label 已销毁（理论上不会发生，因计时器是 label 子对象），兜底保护
        pass


def set_table_empty(table: QTableWidget, columns: int, message: str = "暂无数据") -> None:
    table.clearSpans()
    table.setRowCount(1)
    table.setColumnCount(columns)
    table.setSpan(0, 0, 1, columns)
    item = QTableWidgetItem(message)
    item.setFlags(Qt.ItemIsEnabled)
    item.setTextAlignment(Qt.AlignCenter)
    p = get_palette()
    item.setForeground(QBrush(QColor(p.text_tertiary)))
    table.setItem(0, 0, item)


def make_status_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignCenter)
    p = get_palette()
    color_map = {
        "报名中": (p.success_fg, p.success_bg),
        "报名未开始": (p.accent, p.accent_soft),
        "报名已截止": (p.text_tertiary, p.bg_sidebar),
        "签到未开始": (p.accent, p.accent_soft),
        "签到中": (p.success_fg, p.success_bg),
        "签到已结束": (p.text_tertiary, p.bg_sidebar),
        "已结束": (p.text_tertiary, p.bg_sidebar),
        "已归档": (p.text_tertiary, p.bg_sidebar),
        "草稿": (p.warning_fg, p.warning_bg),
        "待审核": (p.accent, p.accent_soft),
    }
    fg, bg = color_map.get(text, (p.text_secondary, p.bg_base))
    item.setForeground(QBrush(QColor(fg)))
    item.setBackground(QBrush(QColor(bg)))
    return item


class CountdownLabel(QLabel):
    def __init__(self, start_iso: str, end_iso: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._start: datetime | None = None
        self._end: datetime | None = None
        self.setAlignment(Qt.AlignCenter)
        self.setObjectName("countdownLabel")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.set_times(start_iso, end_iso)

    def set_times(self, start_iso: str, end_iso: str) -> None:
        self._start = self._parse_local(start_iso) if start_iso else None
        self._end = self._parse_local(end_iso) if end_iso else None
        if self._start and self._end:
            if not self._timer.isActive():
                self._timer.start(1000)
            self._tick()
        else:
            self._timer.stop()
            self.setText("")

    @staticmethod
    def _parse_local(value: str) -> datetime:
        """Parse an ISO datetime string into UTC-aware datetime."""
        return to_utc(value)

    def _tick(self) -> None:
        if not self._start or not self._end:
            self.setText("")
            return
        now = datetime.now(timezone.utc)
        if now >= self._end:
            self.setText("已结束")
            self._timer.stop()
            return
        if now >= self._start:
            self.setText("报名进行中")
            return
        delta = self._start - now
        if delta.total_seconds() <= 60:
            self.setText("即将开始")
            return
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts: list[str] = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0 or days > 0:
            parts.append(f"{hours}时")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes}分")
        parts.append(f"{seconds}秒")
        self.setText("".join(parts))


class StyledComboBox(QComboBox):
    """QComboBox 子类。

    Windows 上 QComboBox 弹出窗口是原生顶层窗口，不支持逐像素透明。
    因此不在 showPopup 中做透明化处理，而是通过 QSS 使用 border-radius: 0px
    和实心背景来避免圆角黑边问题。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)


class ModeSelector(StyledComboBox):
    """模式选择器 — pill-style 外观，用于视图切换、模式选择等场景。

    自动设置 objectName="modeSelector" 以匹配主题样式。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("modeSelector")


class SearchBox(QLineEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("搜索...")
        self.setClearButtonEnabled(True)
        self.setObjectName("searchBox")


class ItemDetailDialog(QDialog):
    """Generic dialog to show detailed key-value information from a table row."""
    def __init__(self, title: str, data: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        p = get_palette()
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.setStyleSheet(f"background: {p.bg_card};")

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {p.border_light};")
        layout.addWidget(sep)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        for key, value in data.items():
            key_label = QLabel(f"{key}:")
            key_label.setStyleSheet(f"color: {p.text_secondary}; font-weight: 600;")
            val_label = QLabel(str(value) if value else "—")
            val_label.setWordWrap(True)
            val_label.setStyleSheet(f"color: {p.text_primary};")
            form.addRow(key_label, val_label)
        layout.addLayout(form)

        layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)


class RadioCardGroup(QWidget):
    """卡片式单选组件 — 使用 QWidget 卡片 + 隐藏 QRadioButton。

    每个选项显示为可点选的卡片，QLabel 渲染富文本标题和说明。
    解决 QRadioButton 不支持 HTML 富文本的问题。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self.setLayout(self._layout)
        self._cards: list[QWidget] = []
        self._radios: list[QRadioButton] = []
        self._labels: list[QLabel] = []
        self._data: list = []

    def add_card(self, title: str, description: str = "", data=None, tooltip: str = "") -> None:
        """添加一张选项卡片。"""
        p = get_palette()
        # 外层容器
        card = QWidget()
        card.setCursor(Qt.PointingHandCursor)
        card_layout = QHBoxLayout()
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(10)

        # 隐藏的 radio button（只做选择逻辑）
        radio = QRadioButton()
        radio.setFixedSize(0, 0)

        # 富文本标签
        text = f"<b style='color: {p.text_primary};'>{title}</b>"
        if description:
            text += f"<br><span style='color: {p.text_tertiary}; font-size: 11px;'>{description}</span>"
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("border: none; background: transparent;")
        if tooltip:
            label.setToolTip(tooltip)

        card_layout.addWidget(radio)
        card_layout.addWidget(label, 1)
        card.setLayout(card_layout)
        # 卡片样式
        card.setStyleSheet(f"""
            QWidget {{
                background: {p.bg_input};
                border: 1.5px solid {p.border_light};
                border-radius: 10px;
            }}
        """)
        # hover 和 checked 样式通过 eventFilter 或 paintEvent 实现
        # 简化：用 mousePressEvent 连接 radio 的 click
        card.mousePressEvent = lambda e, r=radio: r.click()
        label.mousePressEvent = lambda e, r=radio: r.click()

        # 监听 radio 状态变化来更新样式
        radio.toggled.connect(lambda checked, c=card, p=p: self._update_card_style(c, checked, p))

        self._layout.addWidget(card)
        self._group.addButton(radio)
        self._cards.append(card)
        self._radios.append(radio)
        self._labels.append(label)
        self._data.append(data)

    @staticmethod
    def _update_card_style(card: QWidget, checked: bool, p) -> None:
        if checked:
            card.setStyleSheet(
                f"QWidget {{ background: {p.accent_soft}; border: 2px solid {p.accent}; border-radius: 10px; }}"
            )
        else:
            card.setStyleSheet(
                f"QWidget {{ background: {p.bg_input}; border: 1.5px solid {p.border_light}; border-radius: 10px; }}"
                f"QWidget:hover {{ border-color: {p.accent}; background: {p.accent_soft}; }}"
            )

    def current_data(self):
        checked = self._group.checkedButton()
        if checked is None:
            return None
        try:
            idx = self._radios.index(checked)
            return self._data[idx] if idx < len(self._data) else None
        except ValueError:
            return None

    def card_text(self, index: int) -> str:
        """返回指定索引卡片的纯文本。"""
        if 0 <= index < len(self._labels):
            return self._labels[index].text().replace("&", "").strip()
        return ""

    def current_index(self) -> int:
        checked = self._group.checkedButton()
        if checked is None:
            return -1
        try:
            return self._radios.index(checked)
        except ValueError:
            return -1

    def set_current_by_data(self, data) -> None:
        try:
            idx = self._data.index(data)
            self._radios[idx].setChecked(True)
        except (ValueError, IndexError):
            pass

    def set_current_index(self, index: int) -> None:
        if 0 <= index < len(self._radios):
            self._radios[index].setChecked(True)


class StepIndicator(QWidget):
    """步骤指示器 — 水平步骤条，显示当前进度。

    用法：StepIndicator(["基本信息", "报名规则", "时段岗位"], current=0)
    """

    def __init__(self, steps: list[str], current: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._steps = steps
        self._current = current
        self._labels: list[QLabel] = []
        self._build()

    def _build(self) -> None:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        p = get_palette()
        for i, step in enumerate(self._steps):
            # 步骤圆点 + 文字
            is_active = i <= self._current
            is_current = i == self._current
            color = p.accent if is_active else p.text_tertiary
            bg = p.accent if is_active else p.border_light

            dot = QLabel()
            dot.setFixedSize(28, 28)
            dot.setAlignment(Qt.AlignCenter)
            dot.setText(str(i + 1))
            dot.setStyleSheet(
                f"background: {bg}; color: {p.text_on_accent if is_active else p.text_secondary}; "
                f"border-radius: 14px; font-weight: bold; font-size: 13px;"
            )
            layout.addWidget(dot)

            label = QLabel(step)
            label.setStyleSheet(
                f"color: {color}; font-weight: {'700' if is_current else '400'}; "
                f"font-size: 12px; margin: 0 8px;"
            )
            self._labels.append(label)
            layout.addWidget(label)

            if i < len(self._steps) - 1:
                # 连接线
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFixedHeight(2)
                line.setMinimumWidth(24)
                line.setStyleSheet(
                    f"background: {p.accent if i < self._current else p.border_light}; "
                    f"border: none; margin: 0 4px;"
                )
                line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                layout.addWidget(line)

        layout.addStretch()
        self.setLayout(layout)

    def set_current(self, index: int) -> None:
        """更新当前步骤索引并刷新样式。"""
        self._current = max(0, min(index, len(self._steps) - 1))
        # 清除并重建
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._labels.clear()
        self._build()
