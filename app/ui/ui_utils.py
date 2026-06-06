from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QLabel,
    QLineEdit,
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
    """Format a slot dict into a human-readable label."""
    name = slot.get("name")
    if name:
        return name
    start = slot.get("start_time")
    end = slot.get("end_time")
    if start and end:
        try:
            s = datetime.fromisoformat(str(start))
            e = datetime.fromisoformat(str(end))
            return f"{s.strftime('%m-%d %H:%M')} ~ {e.strftime('%H:%M')}"
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


def set_banner(label: QLabel, kind: str, text: str) -> None:
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
        "已结束": (p.error_fg, p.error_bg),
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
        """Parse an ISO datetime string and treat naive datetimes as local time."""
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.astimezone(timezone.utc)
        return dt.astimezone(timezone.utc)

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
    """QComboBox 子类，修复弹出菜单圆角后出现黑色背景的问题。

    通过重写 showPopup() 对弹出视图设置透明背景属性。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def showPopup(self) -> None:
        super().showPopup()
        # 修复弹出视图的黑角问题：设置透明背景
        popup = self.findChild(QAbstractItemView)
        if popup is not None:
            popup.setAttribute(Qt.WA_TranslucentBackground)
            popup_window = popup.window()
            if popup_window is not None:
                popup_window.setAttribute(Qt.WA_TranslucentBackground)


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
