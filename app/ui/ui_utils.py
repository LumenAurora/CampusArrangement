from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

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
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    return dt.strftime("%Y-%m-%d %H:%M")


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
    }
    fg, bg = color_map.get(text, (p.text_secondary, p.bg_base))
    item.setForeground(QBrush(QColor(fg)))
    item.setBackground(QBrush(QColor(bg)))
    return item
