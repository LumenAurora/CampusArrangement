from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.style import get_palette


def configure_table(table: QTableWidget) -> None:
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    table.verticalHeader().setDefaultSectionSize(40)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Stretch)


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
    """安全的 to_utc：传入 None 或非法字符串返回 None，避免上层异常。"""
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
        now = datetime.now(timezone.utc)
        checkin_start = activity.get("checkin_start")
        checkin_end = activity.get("checkin_end")
        if checkin_start:
            start = safe_to_utc(checkin_start)
            if start and now < start:
                return "签到未开始"
        if checkin_end:
            end = safe_to_utc(checkin_end)
            if end and now > end:
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
