from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.theme import DARK, LIGHT, Palette, build_stylesheet

THEME_LIGHT = "light"
THEME_DARK = "dark"
DENSITY_COMFORTABLE = "comfortable"
DENSITY_COMPACT = "compact"
FORM_LAYOUT_FLAT = "flat"
FORM_LAYOUT_GUIDED = "guided"  # 向导式分步布局（默认）


def _get_palette(theme: str) -> Palette:
    return DARK if theme == THEME_DARK else LIGHT


def apply_app_style(app: QApplication, theme: str) -> None:
    p = _get_palette(theme)
    density = get_density()
    overrides = ""
    if density == DENSITY_COMPACT:
        overrides = """
* { font-size: 12px; }
QLineEdit, QComboBox, QDateTimeEdit, QSpinBox { padding: 5px 8px; }
QPushButton { padding: 5px 14px; }
QListWidget#navList::item { padding: 8px 14px; }
"""
    app.setStyleSheet(build_stylesheet(p) + overrides)
    app.setFont(QFont("Helvetica Neue", 13))


def refresh_dynamic_styles(app: QApplication | None) -> None:
    """Refresh widgets with inline palette-derived styles after theme changes."""
    if app is None:
        return
    for window in app.topLevelWidgets():
        widgets = [window, *window.findChildren(QWidget)]
        for widget in widgets:
            refresh_theme = getattr(widget, "refresh_theme", None)
            if callable(refresh_theme):
                refresh_theme()


def get_theme() -> str:
    settings = QSettings("CampusScheduler", "CampusScheduler")
    return settings.value("ui/theme", THEME_LIGHT)


def get_density() -> str:
    settings = QSettings("CampusScheduler", "CampusScheduler")
    return settings.value("ui/density", DENSITY_COMFORTABLE)


def set_theme(theme: str) -> None:
    settings = QSettings("CampusScheduler", "CampusScheduler")
    settings.setValue("ui/theme", theme)


def set_density(density: str) -> None:
    settings = QSettings("CampusScheduler", "CampusScheduler")
    settings.setValue("ui/density", density)


def get_default_page() -> str:
    settings = QSettings("CampusScheduler", "CampusScheduler")
    return settings.value("ui/default_page", "")


def set_default_page(page_key: str) -> None:
    settings = QSettings("CampusScheduler", "CampusScheduler")
    settings.setValue("ui/default_page", page_key)


def get_palette() -> Palette:
    """获取当前主题的调色板，供自定义绘制控件使用。"""
    return _get_palette(get_theme())


def get_form_layout_mode() -> str:
    """获取活动表单布局模式：guided（向导式，默认）| flat（平铺式）。"""
    settings = QSettings("CampusScheduler", "CampusScheduler")
    return settings.value("ui/form_layout", FORM_LAYOUT_GUIDED)


def set_form_layout_mode(mode: str) -> None:
    """设置活动表单布局模式。"""
    settings = QSettings("CampusScheduler", "CampusScheduler")
    settings.setValue("ui/form_layout", mode)
