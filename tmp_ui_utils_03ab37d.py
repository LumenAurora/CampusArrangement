from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
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


def format_slot_name(slot: dict) -> str:
    """缁熶竴鐨?slot 鍚嶇О鏄剧ず锛氫紭鍏堝悕绉?鈫?鏃堕棿鑼冨洿 鈫?ID 鈫?鍗犱綅绗?""
    if slot.get("name"):
        return slot["name"]
    if slot.get("start_time"):
        return f"{format_datetime(slot['start_time'])} ~ {format_datetime(slot['end_time'])}"
    if slot.get("id"):
        return str(slot["id"])
    return "-"


def format_datetime(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    return dt.strftime("%Y-%m-%d %H:%M")


def format_status(status_str: str) -> str:
    mapping = {
        "open": "鎶ュ悕涓?,
        "closed": "鎶ュ悕宸茬粨鏉?,
        "archived": "宸插綊妗?,
        "draft": "鑽夌",
        "pending_review": "寰呭鏍?,
        "pending": "寰呭鐞?,
        "confirmed": "宸茬‘璁?,
        "assigned": "宸插垎閰?,
        "cancelled": "宸插彇娑?,
        "not_assigned": "鏈腑绛?,
        "checked_in": "宸茬鍒?,
        "absent": "缂哄嫟",
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


def set_table_empty(table: QTableWidget, columns: int, message: str = "鏆傛棤鏁版嵁") -> None:
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
        "鎶ュ悕涓?: (p.success_fg, p.success_bg),
        "宸茬粨鏉?: (p.error_fg, p.error_bg),
        "宸插綊妗?: (p.text_tertiary, p.bg_sidebar),
        "鑽夌": (p.warning_fg, p.warning_bg),
        "寰呭鏍?: (p.accent, p.accent_soft),
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
            self.setText("宸茬粨鏉?)
            self._timer.stop()
            return
        if now >= self._start:
            self.setText("鎶ュ悕杩涜涓?)
            return
        delta = self._start - now
        if delta.total_seconds() <= 60:
            self.setText("鍗冲皢寮€濮?)
            return
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts: list[str] = []
        if days > 0:
            parts.append(f"{days}澶?)
        if hours > 0 or days > 0:
            parts.append(f"{hours}鏃?)
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes}鍒?)
        parts.append(f"{seconds}绉?)
        self.setText("".join(parts))


class SearchBox(QLineEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("鎼滅储...")
        self.setClearButtonEnabled(True)
        self.setObjectName("searchBox")
