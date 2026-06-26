from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QDate, QDateTime, QTime, Qt, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import User
from app.infrastructure.repositories import CheckInRepository, ScheduleRepository, ActivityRepository, TimeSlotRepository
from app.ui.style import get_palette
from app.ui.ui_utils import StyledComboBox, ModeSelector, to_utc


# ─── 调色板辅助 ──────────────────────────────────────────────

def _p():
    return get_palette()


def _color(hex_str: str) -> QColor:
    return QColor(hex_str)


# ─── 自定义日程存储 ──────────────────────────────────────────

class _CustomEventStore:
    """管理用户自定义日程的 JSON 持久化存储。"""

    _PATH = Path.home() / ".campus_arrangement" / "custom_events.json"

    @classmethod
    def _ensure_file(cls) -> None:
        cls._PATH.parent.mkdir(parents=True, exist_ok=True)
        if not cls._PATH.exists():
            cls._PATH.write_text("{}", encoding="utf-8")

    @classmethod
    def load(cls, user_id: str) -> list[dict]:
        cls._ensure_file()
        try:
            data = json.loads(cls._PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        return data.get(user_id, {}).get("events", [])

    @classmethod
    def save(cls, user_id: str, events: list[dict]) -> None:
        cls._ensure_file()
        try:
            data = json.loads(cls._PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        data.setdefault(user_id, {})["events"] = events
        cls._PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def add_event(cls, user_id: str, event: dict) -> None:
        events = cls.load(user_id)
        events.append(event)
        cls.save(user_id, events)

    @classmethod
    def delete_event(cls, user_id: str, event_id: str) -> None:
        events = cls.load(user_id)
        events = [e for e in events if e.get("id") != event_id]
        cls.save(user_id, events)

    @classmethod
    def load_reminders(cls, user_id: str) -> dict[str, int]:
        """加载提醒配置：{event_id: minutes_before}"""
        cls._ensure_file()
        try:
            data = json.loads(cls._PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        return data.get(user_id, {}).get("reminders", {})

    @classmethod
    def save_reminder(cls, user_id: str, event_id: str, minutes_before: int) -> None:
        cls._ensure_file()
        try:
            data = json.loads(cls._PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        data.setdefault(user_id, {}).setdefault("reminders", {})[event_id] = minutes_before
        cls._PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def delete_reminder(cls, user_id: str, event_id: str) -> None:
        cls._ensure_file()
        try:
            data = json.loads(cls._PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        reminders = data.get(user_id, {}).get("reminders", {})
        reminders.pop(event_id, None)
        cls._PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load_fired_reminders(cls, user_id: str) -> set[str]:
        """加载已触发的提醒ID集合"""
        cls._ensure_file()
        try:
            data = json.loads(cls._PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        return set(data.get(user_id, {}).get("fired_reminders", []))

    @classmethod
    def save_fired_reminder(cls, user_id: str, event_id: str) -> None:
        """持久化一个已触发的提醒ID"""
        cls._ensure_file()
        try:
            data = json.loads(cls._PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        fired = data.setdefault(user_id, {}).setdefault("fired_reminders", [])
        if event_id not in fired:
            fired.append(event_id)
        cls._PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── 自定义日历控件 ────────────────────────────────────────────

class ActivityCalendar(QCalendarWidget):
    """带活动标记的月历控件，在日期格子中直接显示活动条目。"""
    date_selected = Signal(QDate)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events_by_date: dict[QDate, list[dict]] = {}
        self.setGridVisible(True)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        self.setSelectionMode(QCalendarWidget.SingleSelection)
        self.clicked.connect(self.date_selected.emit)

    def set_events(self, events_by_date: dict[QDate, list[dict]]) -> None:
        self._events_by_date = events_by_date
        self.updateCells()

    def paintCell(self, painter: QPainter, rect, date: QDate) -> None:
        p = _p()
        painter.save()

        # 背景
        is_selected = date == self.selectedDate()
        is_today = date == QDate.currentDate()
        is_current_month = date.month() == self.monthShown() and date.year() == self.yearShown()

        if is_selected:
            painter.fillRect(rect, _color(p.accent_soft))
        elif is_today:
            painter.fillRect(rect, _color(p.bg_input))
        else:
            painter.fillRect(rect, _color(p.bg_card))

        # 日期数字
        if is_current_month:
            painter.setPen(_color(p.text_primary))
        else:
            painter.setPen(_color(p.text_tertiary))

        font = painter.font()
        font.setPointSize(9)
        font.setBold(is_today or is_selected)
        painter.setFont(font)
        painter.drawText(rect.adjusted(4, 2, -2, 0), Qt.AlignTop | Qt.AlignLeft, str(date.day()))

        # 活动条目
        events = self._events_by_date.get(date, [])
        if events:
            y_offset = 18
            max_events = min(len(events), 3)  # 最多显示3条
            bar_height = 14
            bar_margin = 2
            for i in range(max_events):
                event = events[i]
                bar_rect = rect.adjusted(3, y_offset + i * (bar_height + bar_margin), -3, 0)
                bar_rect.setHeight(bar_height)

                # 条目颜色
                etype = event.get("type", "schedule")
                if etype == "activity":
                    bg = _color(p.accent)
                    fg = _color(p.text_on_accent)
                elif etype == "custom":
                    bg = _color(p.warning_fg)
                    fg = _color(p.text_on_accent)
                else:
                    bg = _color(p.success_fg)
                    fg = _color(p.text_on_accent)

                painter.setPen(Qt.NoPen)
                painter.setBrush(bg)
                painter.drawRoundedRect(bar_rect, 3, 3)

                # 条目文字
                painter.setPen(fg)
                font.setPointSize(7)
                font.setBold(False)
                painter.setFont(font)
                title = event.get("title", "")
                if len(title) > 8:
                    title = title[:7] + "…"
                painter.drawText(bar_rect.adjusted(3, 0, -1, 0), Qt.AlignVCenter | Qt.AlignLeft, title)

            if len(events) > 3:
                painter.setPen(_color(p.text_tertiary))
                font.setPointSize(7)
                painter.setFont(font)
                more_y = y_offset + max_events * (bar_height + bar_margin)
                painter.drawText(rect.adjusted(5, more_y, -2, 0), Qt.AlignTop | Qt.AlignLeft, f"+{len(events) - 3}")

        # 今日下划线
        if is_today:
            pen = QPen(_color(p.accent), 2)
            painter.setPen(pen)
            painter.drawLine(rect.left() + 4, rect.top() + 15, rect.left() + 14, rect.top() + 15)

        # 选中边框
        if is_selected:
            pen = QPen(_color(p.accent), 1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)

        painter.restore()


# ─── 周视图网格内容 ──────────────────────────────────────────

class _WeekGridWidget(QWidget):
    """周视图的网格内容区，拥有自己的 paintEvent 以正确响应重绘。"""
    def __init__(self, week_view: WeekView) -> None:
        super().__init__()
        self._week_view = week_view

    def paintEvent(self, event) -> None:
        self._week_view._paint_grid()


# ─── 周视图 ──────────────────────────────────────────────────

class WeekView(QWidget):
    """周视图：7列时间网格，活动条目直接绘制在对应时段格子中。"""
    date_selected = Signal(QDate)

    def __init__(self) -> None:
        super().__init__()
        self._week_start = QDate.currentDate().addDays(-QDate.currentDate().dayOfWeek() + 1)
        self._events_by_date: dict[QDate, list[dict]] = {}
        self._hour_start = 6
        self._hour_end = 23
        self._cell_height = 48
        self._header_height = 36
        self._time_col_width = 52
        self.setMinimumHeight(400)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 导航栏
        nav = QHBoxLayout()
        nav.setContentsMargins(8, 4, 8, 4)
        self._prev_btn = QPushButton("◀")
        self._prev_btn.setObjectName("secondaryButton")
        self._prev_btn.setFixedSize(32, 28)
        self._prev_btn.clicked.connect(self._go_prev)
        self._next_btn = QPushButton("▶")
        self._next_btn.setObjectName("secondaryButton")
        self._next_btn.setFixedSize(32, 28)
        self._next_btn.clicked.connect(self._go_next)
        self._header_label = QLabel()
        self._header_label.setAlignment(Qt.AlignCenter)
        self._header_label.setObjectName("pageTitle")
        font = self._header_label.font()
        font.setPointSize(13)
        self._header_label.setFont(font)
        nav.addWidget(self._prev_btn)
        nav.addStretch()
        nav.addWidget(self._header_label)
        nav.addStretch()
        nav.addWidget(self._next_btn)
        layout.addLayout(nav)

        # 网格区域（可滚动）
        self._grid_area = QScrollArea()
        self._grid_area.setWidgetResizable(True)
        self._grid_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._grid_content = _WeekGridWidget(self)
        self._grid_content.setMinimumHeight((self._hour_end - self._hour_start) * self._cell_height + self._header_height)
        self._grid_area.setWidget(self._grid_content)

        layout.addWidget(self._grid_area)
        self.setLayout(layout)
        self._update_header()

    def set_events(self, events_by_date: dict[QDate, list[dict]]) -> None:
        self._events_by_date = events_by_date
        self._grid_content.update()

    def set_week_start(self, date: QDate) -> None:
        self._week_start = date.addDays(-date.dayOfWeek() + 1)
        self._update_header()
        self._grid_content.update()

    def _go_prev(self) -> None:
        self._week_start = self._week_start.addDays(-7)
        self._update_header()
        self._grid_content.update()

    def _go_next(self) -> None:
        self._week_start = self._week_start.addDays(7)
        self._update_header()
        self._grid_content.update()

    def _update_header(self) -> None:
        start_str = self._week_start.toString("MM月dd日")
        end_str = self._week_start.addDays(6).toString("MM月dd日")
        self._header_label.setText(f"{start_str} — {end_str}")

    def _paint_grid(self) -> None:
        p = _p()
        painter = QPainter(self._grid_content)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self._grid_content.width()
        day_w = (w - self._time_col_width) / 7
        y_top = self._header_height

        # 绘制星期头
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for i in range(7):
            x = self._time_col_width + i * day_w
            d = self._week_start.addDays(i)
            is_today = d == QDate.currentDate()

            # 头部背景
            painter.setPen(Qt.NoPen)
            painter.setBrush(_color(p.bg_sidebar if not is_today else p.accent_soft))
            painter.drawRect(int(x), 0, int(day_w), self._header_height)

            painter.setPen(_color(p.accent if is_today else p.text_secondary))
            text = f"{weekdays[i]}\n{d.toString('MM/dd')}"
            painter.drawText(int(x), 0, int(day_w), self._header_height, Qt.AlignCenter, text)

        # 时间列头
        painter.setPen(Qt.NoPen)
        painter.setBrush(_color(p.bg_sidebar))
        painter.drawRect(0, 0, self._time_col_width, self._header_height)

        # 绘制时间格和事件
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)

        for hour in range(self._hour_start, self._hour_end):
            y = y_top + (hour - self._hour_start) * self._cell_height

            # 时间标签
            painter.setPen(_color(p.text_tertiary))
            painter.drawText(0, y, self._time_col_width, self._cell_height, Qt.AlignTop | Qt.AlignHCenter, f"{hour:02d}:00")

            # 水平线
            pen = QPen(_color(p.border_light), 1)
            painter.setPen(pen)
            painter.drawLine(self._time_col_width, y, w, y)

            # 每日列
            for day_i in range(7):
                x = self._time_col_width + day_i * day_w
                d = self._week_start.addDays(day_i)

                # 垂直线
                painter.setPen(QPen(_color(p.border_light), 1))
                painter.drawLine(int(x), y, int(x), y + self._cell_height)

                # 今日高亮
                if d == QDate.currentDate():
                    painter.fillRect(int(x) + 1, y, int(day_w) - 1, self._cell_height, _color(p.accent_soft + "30"))

        # 绘制事件条目
        for day_i in range(7):
            d = self._week_start.addDays(day_i)
            events = self._events_by_date.get(d, [])
            x = self._time_col_width + day_i * day_w

            for ev in events:
                start_hour = ev.get("start_hour", 0)
                end_hour = ev.get("end_hour", start_hour + 1)
                if start_hour < self._hour_start:
                    start_hour = self._hour_start
                if end_hour > self._hour_end:
                    end_hour = self._hour_end

                ey = y_top + (start_hour - self._hour_start) * self._cell_height
                eh = (end_hour - start_hour) * self._cell_height
                if eh < 20:
                    eh = 20

                etype = ev.get("type", "schedule")
                if etype == "activity":
                    bg = _color(p.accent)
                    fg = _color(p.text_on_accent)
                elif etype == "custom":
                    bg = _color(p.warning_fg)
                    fg = _color(p.text_on_accent)
                else:
                    bg = _color(p.success_fg)
                    fg = _color(p.text_on_accent)

                bar = QRectF(x + 3, ey + 2, day_w - 6, eh - 4)
                painter.setPen(Qt.NoPen)
                painter.setBrush(bg)
                painter.drawRoundedRect(bar, 5, 5)

                painter.setPen(fg)
                font.setPointSize(8)
                font.setBold(False)
                painter.setFont(font)
                title = ev.get("title", "")
                location = ev.get("location", "")
                text = title
                if location:
                    text += f" · {location}"
                if len(text) > 16:
                    text = text[:15] + "…"
                painter.drawText(bar.adjusted(4, 2, -2, -2), Qt.AlignTop | Qt.AlignLeft, text)

                # 时间行
                time_text = ev.get("time_range", "")
                if time_text:
                    font.setPointSize(7)
                    painter.setFont(font)
                    painter.drawText(bar.adjusted(4, 14, -2, -2), Qt.AlignTop | Qt.AlignLeft, time_text)

        painter.end()


# ─── 日视图网格内容 ──────────────────────────────────────────

class _DayGridWidget(QWidget):
    """日视图的内容区，拥有自己的 paintEvent 以正确响应重绘。"""
    def __init__(self, day_view: DayView) -> None:
        super().__init__()
        self._day_view = day_view

    def paintEvent(self, event) -> None:
        self._day_view._paint_content()


# ─── 日视图 ──────────────────────────────────────────────────

class DayView(QWidget):
    """日视图：单日时间线，活动条目直接绘制在对应时段。"""
    date_selected = Signal(QDate)

    def __init__(self) -> None:
        super().__init__()
        self._date = QDate.currentDate()
        self._events: list[dict] = []
        self._hour_start = 0
        self._hour_end = 24
        self._cell_height = 56
        self._header_height = 48
        self._time_col_width = 60
        self.setMinimumHeight(400)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 导航栏
        nav = QHBoxLayout()
        nav.setContentsMargins(8, 4, 8, 4)
        self._prev_btn = QPushButton("◀")
        self._prev_btn.setObjectName("secondaryButton")
        self._prev_btn.setFixedSize(32, 28)
        self._prev_btn.clicked.connect(self._go_prev)
        self._next_btn = QPushButton("▶")
        self._next_btn.setObjectName("secondaryButton")
        self._next_btn.setFixedSize(32, 28)
        self._next_btn.clicked.connect(self._go_next)
        self._header_label = QLabel()
        self._header_label.setAlignment(Qt.AlignCenter)
        self._header_label.setObjectName("pageTitle")
        font = self._header_label.font()
        font.setPointSize(13)
        self._header_label.setFont(font)
        nav.addWidget(self._prev_btn)
        nav.addStretch()
        nav.addWidget(self._header_label)
        nav.addStretch()
        nav.addWidget(self._next_btn)
        layout.addLayout(nav)

        # 滚动区域
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content = _DayGridWidget(self)
        self._content.setMinimumHeight((self._hour_end - self._hour_start) * self._cell_height + self._header_height)
        self._scroll.setWidget(self._content)

        layout.addWidget(self._scroll)
        self.setLayout(layout)
        self._update_header()

    def set_events(self, events: list[dict]) -> None:
        self._events = events
        self._content.update()

    def set_date(self, date: QDate) -> None:
        self._date = date
        self._update_header()
        self._content.update()

    def _go_prev(self) -> None:
        self._date = self._date.addDays(-1)
        self._update_header()
        self.date_selected.emit(self._date)
        self._content.update()

    def _go_next(self) -> None:
        self._date = self._date.addDays(1)
        self._update_header()
        self.date_selected.emit(self._date)
        self._content.update()

    def _update_header(self) -> None:
        date_str = self._date.toString("yyyy年MM月dd日")
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][self._date.dayOfWeek() - 1]
        self._header_label.setText(f"{date_str} {weekday}")

    def _paint_content(self) -> None:
        p = _p()
        painter = QPainter(self._content)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self._content.width()
        y_top = self._header_height

        # 头部
        painter.setPen(Qt.NoPen)
        painter.setBrush(_color(p.bg_sidebar))
        painter.drawRect(0, 0, w, self._header_height)
        painter.setPen(_color(p.text_primary))
        font = painter.font()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        date_str = self._date.toString("yyyy年MM月dd日")
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][self._date.dayOfWeek() - 1]
        painter.drawText(0, 0, w, self._header_height, Qt.AlignCenter, f"{date_str} {weekday}")

        # 时间格
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)

        for hour in range(self._hour_start, self._hour_end):
            y = y_top + (hour - self._hour_start) * self._cell_height

            # 时间标签
            painter.setPen(_color(p.text_tertiary))
            painter.drawText(4, y, self._time_col_width - 4, self._cell_height, Qt.AlignTop | Qt.AlignRight, f"{hour:02d}:00")

            # 水平线
            painter.setPen(QPen(_color(p.border_light), 1))
            painter.drawLine(self._time_col_width, y, w, y)

            # 当前时间线
            now = QDateTime.currentDateTime()
            if self._date == now.date() and hour == now.time().hour():
                minute_y = y + now.time().minute() / 60.0 * self._cell_height
                painter.setPen(QPen(_color(p.error_fg), 2))
                painter.drawLine(self._time_col_width, int(minute_y), w, int(minute_y))

        # 绘制事件
        for ev in self._events:
            start_hour = ev.get("start_hour", 0)
            end_hour = ev.get("end_hour", start_hour + 1)
            if start_hour < self._hour_start:
                start_hour = self._hour_start
            if end_hour > self._hour_end:
                end_hour = self._hour_end

            ey = y_top + (start_hour - self._hour_start) * self._cell_height
            eh = (end_hour - start_hour) * self._cell_height
            if eh < 28:
                eh = 28

            etype = ev.get("type", "schedule")
            if etype == "activity":
                bg = _color(p.accent)
                fg = _color(p.text_on_accent)
            elif etype == "custom":
                bg = _color(p.warning_fg)
                fg = _color(p.text_on_accent)
            else:
                bg = _color(p.success_fg)
                fg = _color("#ffffff")

            bar = QRectF(self._time_col_width + 4, ey + 2, w - self._time_col_width - 8, eh - 4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(bar, 8, 8)

            painter.setPen(fg)
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            title = ev.get("title", "")
            painter.drawText(bar.adjusted(10, 6, -6, -6), Qt.AlignTop | Qt.AlignLeft, title)

            font.setPointSize(9)
            font.setBold(False)
            painter.setFont(font)
            time_range = ev.get("time_range", "")
            location = ev.get("location", "")
            detail_parts = []
            if time_range:
                detail_parts.append(time_range)
            if location:
                detail_parts.append(location)
            if detail_parts:
                painter.drawText(bar.adjusted(10, 24, -6, -6), Qt.AlignTop | Qt.AlignLeft, " · ".join(detail_parts))

        painter.end()


# ─── 事件详情对话框 ──────────────────────────────────────────

class EventDetailDialog(QDialog):
    event_deleted = Signal(str)  # 发送被删除事件的 id
    reminder_set = Signal(str, int)  # (event_id, minutes_before)

    def __init__(self, event: dict, parent=None) -> None:
        super().__init__(parent)
        p = _p()
        self._event = event
        self.setWindowTitle("日程详情")
        self.setMinimumWidth(360)
        self.setStyleSheet(f"background: {p.bg_card}; border-radius: 16px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = event.get("title", "未知活动")
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {p.border_light};")
        layout.addWidget(sep)

        type_map = {"activity": "活动报名", "custom": "个人日程", "schedule": "排班"}
        fields = [
            ("时间", event.get("time_range", event.get("time", "—"))),
            ("地点", event.get("location", "—")),
            ("类型", type_map.get(event.get("type"), "排班")),
        ]
        if event.get("type") == "custom" and event.get("description"):
            fields.append(("备注", event.get("description")))
        for label_text, value in fields:
            row = QHBoxLayout()
            lbl = QLabel(f"{label_text}:")
            lbl.setStyleSheet(f"color: {p.text_secondary}; font-weight: 600;")
            lbl.setFixedWidth(50)
            val = QLabel(str(value) if value else "—")
            val.setWordWrap(True)
            row.addWidget(lbl)
            row.addWidget(val, 1)
            layout.addLayout(row)

        layout.addStretch()

        reminder_btn = QPushButton("🔔 设置提醒")
        reminder_btn.setObjectName("secondaryButton")
        reminder_btn.clicked.connect(self._set_reminder)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(reminder_btn)
        if event.get("type") == "custom":
            delete_btn = QPushButton("删除")
            delete_btn.setObjectName("dangerButton")
            delete_btn.clicked.connect(self._on_delete)
            btn_layout.addWidget(delete_btn)
        btn_layout.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _set_reminder(self) -> None:
        """设置日程提醒"""
        from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox
        event_id = self._event.get("id", "")
        if not event_id:
            QMessageBox.warning(self, "提示", "无法为此日程设置提醒")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("设置提醒")
        dlg.setMinimumWidth(300)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("在日程开始前多久提醒？"))
        combo = QComboBox()
        combo.addItem("5 分钟前", 5)
        combo.addItem("15 分钟前", 15)
        combo.addItem("30 分钟前", 30)
        combo.addItem("1 小时前", 60)
        combo.setCurrentIndex(1)  # 默认15分钟
        layout.addWidget(combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() == QDialog.Accepted:
            minutes = combo.currentData()
            self.reminder_set.emit(event_id, minutes)
            QMessageBox.information(self, "提醒已设置",
                                    f"将在日程开始前 {minutes} 分钟提醒您")

    def _on_delete(self) -> None:
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除此日程吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            event_id = self._event.get("id", "")
            if event_id:
                self.event_deleted.emit(event_id)
            self.accept()


# ─── 日程面板 ────────────────────────────────────────────────

class CalendarPanel(QWidget):
    def __init__(
        self,
        schedule_repo: ScheduleRepository,
        activity_repo: ActivityRepository,
        slot_repo: TimeSlotRepository,
        user: User,
        checkin_repo: CheckInRepository | None = None,
    ) -> None:
        super().__init__()
        self._schedule_repo = schedule_repo
        self._activity_repo = activity_repo
        self._slot_repo = slot_repo
        self._user = user
        self._checkin_repo = checkin_repo
        self._selected_date = QDate.currentDate()
        self._events_by_date: dict[QDate, list[dict]] = {}
        self._all_events: list[dict] = []
        self._fired_reminders: set[str] = _CustomEventStore.load_fired_reminders(user.id)  # 已触发的提醒事件ID（持久化）

        self._init_ui()
        self.refresh()

        # 提醒定时器：每30秒检查一次
        self._reminder_timer = QTimer(self)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start(30000)

    def _init_ui(self) -> None:
        p = _p()
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 顶部工具栏
        header = QHBoxLayout()
        header.setSpacing(8)

        self._view_mode = ModeSelector()
        self._view_mode.addItems(["月视图", "周视图", "日视图"])
        self._view_mode.setFixedWidth(100)
        self._view_mode.currentIndexChanged.connect(self._on_view_changed)

        self._jump_date = QDateEdit(QDate.currentDate())
        self._jump_date.setCalendarPopup(True)
        self._jump_date.setDisplayFormat("yyyy-MM-dd")
        self._jump_date.setFixedWidth(120)
        self._jump_date.dateChanged.connect(self._on_date_jump)

        jump_btn = QPushButton("跳转")
        jump_btn.setObjectName("secondaryButton")
        jump_btn.clicked.connect(self._jump_to_date)

        today_btn = QPushButton("今天")
        today_btn.setObjectName("secondaryButton")
        today_btn.clicked.connect(self._go_to_today)

        add_event_btn = QPushButton("添加日程")
        add_event_btn.setObjectName("secondaryButton")
        add_event_btn.clicked.connect(self._on_add_event)

        header.addWidget(QLabel("视图:"))
        header.addWidget(self._view_mode)
        header.addSpacing(16)
        header.addWidget(QLabel("日期:"))
        header.addWidget(self._jump_date)
        header.addWidget(jump_btn)
        header.addWidget(today_btn)
        header.addWidget(add_event_btn)
        header.addStretch(1)

        # 日历视图
        self._calendar = ActivityCalendar()
        self._calendar.date_selected.connect(self._on_calendar_date_selected)

        self._week_view = WeekView()
        self._week_view.date_selected.connect(self._on_calendar_date_selected)

        self._day_view = DayView()
        self._day_view.date_selected.connect(self._on_calendar_date_selected)

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self._calendar)
        self._view_stack.addWidget(self._week_view)
        self._view_stack.addWidget(self._day_view)

        # 右侧面板
        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)

        # 当日安排
        self._date_info = QGroupBox("当日安排")
        self._date_info_layout = QVBoxLayout()
        self._date_info_layout.setSpacing(4)
        self._date_info.setLayout(self._date_info_layout)

        # 我的日程
        self._my_events = QGroupBox("我的日程")
        my_events_layout = QVBoxLayout()
        my_events_layout.setSpacing(4)
        self._my_events_list = QListWidget()
        self._my_events_list.itemClicked.connect(self._on_event_click)
        my_events_layout.addWidget(self._my_events_list)
        self._my_events.setLayout(my_events_layout)

        right_panel.addWidget(self._date_info, 1)
        right_panel.addWidget(self._my_events, 2)

        # 主布局
        main_layout = QHBoxLayout()
        main_layout.setSpacing(12)
        main_layout.addWidget(self._view_stack, 3)
        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        right_widget.setMinimumWidth(240)
        right_widget.setMaximumWidth(380)
        main_layout.addWidget(right_widget, 0)

        layout.addLayout(header)
        layout.addLayout(main_layout, 1)
        self.setLayout(layout)

    # ─── 事件处理 ────────────────────────────────────────────

    def _on_view_changed(self, index: int) -> None:
        self._view_stack.setCurrentIndex(index)
        self._apply_events_to_views()
        self._update_date_info()

    def _on_calendar_date_selected(self, date: QDate) -> None:
        self._selected_date = date
        self._jump_date.setDate(date)
        if self._view_mode.currentIndex() == 2:
            self._day_view.set_date(date)
        self._update_date_info()
        self._update_my_events()

    def _on_date_jump(self, date: QDate) -> None:
        self._selected_date = date
        self._navigate_to_date(date)

    def _jump_to_date(self) -> None:
        date = self._jump_date.date()
        self._selected_date = date
        self._navigate_to_date(date)

    def _go_to_today(self) -> None:
        today = QDate.currentDate()
        self._jump_date.setDate(today)
        self._selected_date = today
        self._navigate_to_date(today)

    def _navigate_to_date(self, date: QDate) -> None:
        idx = self._view_mode.currentIndex()
        if idx == 0:
            self._calendar.setSelectedDate(date)
            self._calendar.showSelectedDate()
        elif idx == 1:
            self._week_view.set_week_start(date)
        elif idx == 2:
            self._day_view.set_date(date)
        self._update_date_info()

    def _on_event_click(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data:
            dlg = EventDetailDialog(data, self)
            dlg.event_deleted.connect(self._on_delete_custom_event)
            dlg.reminder_set.connect(self._on_set_reminder)
            dlg.exec()

    def _on_set_reminder(self, event_id: str, minutes_before: int) -> None:
        """保存提醒设置"""
        _CustomEventStore.save_reminder(self._user.id, event_id, minutes_before)

    def _on_add_event(self) -> None:
        dlg = AddEventDialog(self._selected_date, self)
        if dlg.exec() == QDialog.Accepted:
            raw = dlg.get_event_data()
            if not raw.get("title"):
                return
            event_id = str(uuid.uuid4())
            start_dt = self._parse_dt(raw["start_time"])
            end_dt = self._parse_dt(raw["end_time"])
            if not start_dt:
                return
            end_hour = end_dt.hour if end_dt else min(start_dt.hour + 1, 24)
            time_range = start_dt.strftime("%H:%M")
            if end_dt:
                time_range += f" - {end_dt.strftime('%H:%M')}"
            custom_event = {
                "id": event_id,
                "title": raw["title"],
                "location": raw.get("location", ""),
                "start_time": raw["start_time"],
                "end_time": raw["end_time"],
                "description": raw.get("description", ""),
                "type": "custom",
                "time": raw["start_time"][:16],
                "time_range": time_range,
                "start_hour": start_dt.hour,
                "end_hour": end_hour,
            }
            _CustomEventStore.add_event(self._user.id, {
                "id": event_id,
                "title": raw["title"],
                "location": raw.get("location", ""),
                "start_time": raw["start_time"],
                "end_time": raw["end_time"],
                "description": raw.get("description", ""),
            })
            self.refresh()

    def _on_delete_custom_event(self, event_id: str) -> None:
        _CustomEventStore.delete_event(self._user.id, event_id)
        self.refresh()

    # ─── 数据刷新 ────────────────────────────────────────────

    def refresh(self) -> None:
        try:
            activities = self._activity_repo.list_all()
            schedules = self._schedule_repo.list_by_user(self._user.id)

            # 签到状态映射：slot_id -> checkin_status
            checkin_map: dict[str, str] = {}
            if self._checkin_repo:
                try:
                    user_checkins = self._checkin_repo.list_by_user(self._user.id)
                    for ci in user_checkins:
                        checkin_map[ci["slot_id"]] = ci["status"]
                except Exception:
                    pass

            # 构建活动 ID -> 活动信息映射
            activity_map: dict[str, dict] = {}
            for a in activities:
                activity_map[a["id"]] = a

            # 预加载所有需要的 slot
            needed_activity_ids = {s["activity_id"] for s in schedules}
            slot_cache: dict[str, list[dict]] = {}
            for aid in needed_activity_ids:
                slot_cache[aid] = self._slot_repo.list_by_activity(aid)

            events_by_date: dict[QDate, list[dict]] = {}
            all_events: list[dict] = []

            # 活动报名事件
            for activity in activities:
                start_time_str = activity.get("signup_start")
                if start_time_str:
                    try:
                        dt = self._parse_dt(start_time_str)
                        if dt:
                            qdate = QDate(dt.year, dt.month, dt.day)
                            event = {
                                "title": activity.get("name", "未知活动"),
                                "time": start_time_str[:16],
                                "time_range": dt.strftime("%H:%M") + " 开始报名",
                                "location": activity.get("location", ""),
                                "type": "activity",
                                "start_hour": dt.hour,
                                "end_hour": min(dt.hour + 1, 24),
                            }
                            events_by_date.setdefault(qdate, []).append(event)
                            all_events.append(event)
                    except Exception:
                        pass

            # 排班事件
            for schedule in schedules:
                slot_id = schedule.get("slot_id")
                activity_id = schedule.get("activity_id")
                activity = activity_map.get(activity_id)
                activity_name = activity.get("name", "未知活动") if activity else "未知活动"
                activity_location = activity.get("location", "") if activity else ""

                slots = slot_cache.get(activity_id, [])
                for slot in slots:
                    if slot.get("id") == slot_id:
                        start_time_str = slot.get("start_time")
                        end_time_str = slot.get("end_time")
                        if start_time_str:
                            try:
                                dt = self._parse_dt(start_time_str)
                                end_dt = self._parse_dt(end_time_str) if end_time_str else None
                                if dt:
                                    qdate = QDate(dt.year, dt.month, dt.day)
                                    end_hour = end_dt.hour if end_dt else min(dt.hour + 1, 24)
                                    time_range = dt.strftime("%H:%M")
                                    if end_dt:
                                        time_range += f" - {end_dt.strftime('%H:%M')}"
                                    event = {
                                        "title": activity_name,
                                        "time": start_time_str[:16],
                                        "time_range": time_range,
                                        "location": activity_location,
                                        "type": "schedule",
                                        "start_hour": dt.hour,
                                        "end_hour": end_hour,
                                        "checkin_status": checkin_map.get(slot_id),
                                    }
                                    events_by_date.setdefault(qdate, []).append(event)
                                    all_events.append(event)
                            except Exception:
                                pass
                        break  # 找到匹配的 slot 即可

            # 自定义日程事件
            custom_events = _CustomEventStore.load(self._user.id)
            for ce in custom_events:
                try:
                    start_dt = self._parse_dt(ce.get("start_time", ""))
                    end_dt = self._parse_dt(ce.get("end_time", ""))
                    if not start_dt:
                        continue
                    qdate = QDate(start_dt.year, start_dt.month, start_dt.day)
                    end_hour = end_dt.hour if end_dt else min(start_dt.hour + 1, 24)
                    time_range = start_dt.strftime("%H:%M")
                    if end_dt:
                        time_range += f" - {end_dt.strftime('%H:%M')}"
                    event = {
                        "id": ce.get("id", ""),
                        "title": ce.get("title", "个人日程"),
                        "time": ce.get("start_time", "")[:16],
                        "time_range": time_range,
                        "location": ce.get("location", ""),
                        "description": ce.get("description", ""),
                        "type": "custom",
                        "start_hour": start_dt.hour,
                        "end_hour": end_hour,
                    }
                    events_by_date.setdefault(qdate, []).append(event)
                    all_events.append(event)
                except Exception:
                    pass

            self._events_by_date = events_by_date
            self._all_events = all_events

            self._apply_events_to_views()
            self._update_my_events()
            self._update_date_info()
        except Exception:
            pass

    def _apply_events_to_views(self) -> None:
        self._calendar.set_events(self._events_by_date)
        self._week_view.set_events(self._events_by_date)

        # 日视图只显示选中日期的事件
        day_events = self._events_by_date.get(self._selected_date, [])
        self._day_view.set_events(day_events)
        self._day_view.set_date(self._selected_date)

    def _update_my_events(self) -> None:
        self._my_events_list.clear()
        p = _p()
        # 只显示选中日期的日程
        day_events = self._events_by_date.get(self._selected_date, [])
        if not day_events:
            item = QListWidgetItem("当日无日程")
            item.setFlags(Qt.ItemIsEnabled)
            item.setForeground(QColor(p.text_tertiary))
            self._my_events_list.addItem(item)
            return
        for event in sorted(day_events, key=lambda e: e.get("start_hour", 0)):
            etype = event.get("type", "schedule")
            checkin_status = event.get("checkin_status")

            # 根据类型和签到状态选择颜色和图标
            if etype == "activity":
                prefix = "📋 "
                color = p.accent
            elif etype == "custom":
                prefix = "📌 "
                color = p.warning_fg
            elif checkin_status == "checked_in":
                prefix = "✅ "
                color = p.success_fg
            elif checkin_status == "absent":
                prefix = "❌ "
                color = p.error_fg
            else:
                prefix = "⬜ "
                color = p.text_secondary

            title = event.get("title", "未知活动")
            time_range = event.get("time_range", "")
            location = event.get("location", "")
            parts = [prefix + title]
            if time_range:
                parts.append(time_range)
            if location:
                parts.append(location)
            display = " · ".join(parts)

            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, event)
            item.setForeground(QColor(color))
            self._my_events_list.addItem(item)

    def _update_date_info(self) -> None:
        # 清空
        while self._date_info_layout.count() > 0:
            child = self._date_info_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        p = _p()
        date_str = self._selected_date.toString("yyyy年MM月dd日")
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][self._selected_date.dayOfWeek() - 1]

        header_label = QLabel(f"<b>{date_str} {weekday}</b>")
        self._date_info_layout.addWidget(header_label)

        day_events = self._events_by_date.get(self._selected_date, [])
        if not day_events:
            empty = QLabel("当日暂无安排")
            empty.setStyleSheet(f"color: {p.text_tertiary};")
            self._date_info_layout.addWidget(empty)
        else:
            for event in sorted(day_events, key=lambda e: e.get("start_hour", 0)):
                etype = event.get("type", "schedule")
                if etype == "activity":
                    color = p.accent
                elif etype == "custom":
                    color = p.warning_fg
                else:
                    color = p.success_fg
                title = event.get("title", "未知活动")
                time_range = event.get("time_range", "")
                location = event.get("location", "")

                card = QFrame()
                card.setStyleSheet(f"""
                    QFrame {{
                        background: {p.bg_input};
                        border-left: 3px solid {color};
                        border-radius: 6px;
                        padding: 6px 8px;
                    }}
                """)
                card_layout = QVBoxLayout()
                card_layout.setContentsMargins(8, 4, 4, 4)
                card_layout.setSpacing(2)

                name_label = QLabel(f"<b>{title}</b>")
                name_label.setStyleSheet(f"color: {color}; border: none;")
                card_layout.addWidget(name_label)

                detail_parts = []
                if time_range:
                    detail_parts.append(time_range)
                if location:
                    detail_parts.append(location)
                if detail_parts:
                    detail_label = QLabel(" · ".join(detail_parts))
                    detail_label.setStyleSheet(f"color: {p.text_secondary}; font-size: 11px; border: none;")
                    card_layout.addWidget(detail_label)

                card.setLayout(card_layout)
                self._date_info_layout.addWidget(card)

    def _check_reminders(self) -> None:
        """检查是否有即将到来的日程需要提醒"""
        try:
            reminders = _CustomEventStore.load_reminders(self._user.id)
            if not reminders:
                return
            now = datetime.now(timezone.utc)
            for event_id, minutes_before in reminders.items():
                if event_id in self._fired_reminders:
                    continue
                # 在所有日程和自定义事件中查找匹配的事件
                for event in self._all_events:
                    if event.get("id") == event_id:
                        time_str = event.get("time", "")
                        if time_str:
                            try:
                                event_dt = self._parse_dt(time_str)
                                if event_dt:
                                    delta = (event_dt - now).total_seconds()
                                    if 0 <= delta <= minutes_before * 60:
                                        self._show_reminder(event)
                                        self._fired_reminders.add(event_id)
                                        _CustomEventStore.save_fired_reminder(self._user.id, event_id)
                            except Exception:
                                pass
                        break
        except Exception:
            pass

    def _show_reminder(self, event: dict) -> None:
        """显示提醒通知"""
        title = event.get("title", "日程提醒")
        time_range = event.get("time_range", "")
        location = event.get("location", "")
        msg = f"{title}\n时间：{time_range}"
        if location:
            msg += f"\n地点：{location}"
        # 使用简单的消息框作为提醒
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setWindowTitle("⏰ 日程提醒")
        box.setText(msg)
        box.setIcon(QMessageBox.Information)
        box.setStandardButtons(QMessageBox.Ok)
        box.show()

    @staticmethod
    def _parse_dt(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return to_utc(value)
        except (ValueError, TypeError):
            return None


# ─── 添加日程对话框 ──────────────────────────────────────────

class AddEventDialog(QDialog):
    def __init__(self, date: QDate, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("添加日程")
        self._selected_date = date
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout()

        form = QFormLayout()
        self._title = QLineEdit()
        self._title.setPlaceholderText("日程名称")
        self._location = QLineEdit()
        self._location.setPlaceholderText("地点")
        self._start_time = QDateTimeEdit(QDateTime(self._selected_date, QTime(9, 0)))
        self._start_time.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._end_time = QDateTimeEdit(QDateTime(self._selected_date, QTime(10, 0)))
        self._end_time.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._description = QLineEdit()
        self._description.setPlaceholderText("备注")

        form.addRow("日程名称", self._title)
        form.addRow("地点", self._location)
        form.addRow("开始时间", self._start_time)
        form.addRow("结束时间", self._end_time)
        form.addRow("备注", self._description)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("primaryButton")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch(1)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(form)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def get_event_data(self) -> dict:
        return {
            "title": self._title.text(),
            "location": self._location.text(),
            "start_time": self._start_time.dateTime().toString(Qt.ISODate),
            "end_time": self._end_time.dateTime().toString(Qt.ISODate),
            "description": self._description.text(),
        }
