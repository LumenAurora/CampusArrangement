from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QActionGroup, QFont
from PySide6.QtWidgets import QApplication, QMainWindow

THEME_LIGHT = "light"
THEME_DARK = "dark"
DENSITY_COMFORTABLE = "comfortable"
DENSITY_COMPACT = "compact"

LIGHT_STYLE = """
* {
    font-family: "Segoe UI";
    font-size: 12px;
}
QMainWindow, QDialog {
    background-color: #f5f7fb;
    color: #2b2f36;
}
QLabel {
    color: #2b2f36;
}
QMenuBar, QMenu {
    background-color: #f5f7fb;
    color: #2b2f36;
}
QFrame#topBar {
    background: #ffffff;
    border: 1px solid #d6dbe3;
    border-radius: 12px;
}
QLabel#appTitle {
    font-size: 18px;
    font-weight: 700;
    color: #1f2430;
}
QLabel#appSubtitle {
    color: #5b6270;
}
QLabel#userBadge {
    background: #eef2f8;
    border: 1px solid #d6dbe3;
    border-radius: 10px;
    padding: 4px 10px;
    color: #2b2f36;
}
QFrame#statCard {
    background: #ffffff;
    border: 1px solid #d6dbe3;
    border-radius: 12px;
}
QLabel#statValue {
    font-size: 22px;
    font-weight: 700;
    color: #1f2430;
}
QLabel#statLabel {
    color: #5b6270;
}
QListWidget#navList {
    background: #ffffff;
    border: 1px solid #d6dbe3;
    border-radius: 12px;
}
QListWidget#navList::item {
    padding: 10px 12px;
    border-radius: 8px;
    margin: 4px 6px;
    color: #2b2f36;
}
QListWidget#navList::item:selected {
    background: #4b7bec;
    color: #ffffff;
}
QGroupBox {
    border: 1px solid #d6dbe3;
    border-radius: 10px;
    margin-top: 12px;
    background-color: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #2b2f36;
    font-weight: 600;
}
QLineEdit, QComboBox, QDateTimeEdit, QSpinBox {
    background: #ffffff;
    color: #2b2f36;
    border: 1px solid #cfd5df;
    border-radius: 8px;
    padding: 6px 8px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #2b2f36;
}
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus, QSpinBox:focus {
    border: 1px solid #4b7bec;
}
QPushButton {
    background: #4b7bec;
    color: #ffffff;
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 600;
}
QPushButton:hover {
    background: #3b6ad9;
}
QPushButton:disabled {
    background: #a8b6d6;
}
QTableWidget {
    background: #ffffff;
    alternate-background-color: #f6f8fc;
    border: 1px solid #d6dbe3;
    border-radius: 8px;
}
QTableView::item {
    color: #2b2f36;
    padding: 4px;
}
QTableView::item:selected {
    background: #dbe7ff;
    color: #1c2540;
}
QHeaderView::section {
    background: #eef2f8;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #d6dbe3;
    font-weight: 600;
    color: #3b3f45;
}
QTabWidget::pane {
    border: 1px solid #d6dbe3;
    border-radius: 10px;
    background: #ffffff;
}
QTabBar::tab {
    background: #e9edf5;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 6px 12px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #2b2f36;
    border: 1px solid #d6dbe3;
    border-bottom-color: #ffffff;
}
QLabel#titleLabel {
    font-size: 18px;
    font-weight: 700;
    color: #2b2f36;
}
QLabel#sectionLabel {
    font-weight: 600;
    color: #2b2f36;
}
QLabel#pageTitle {
    font-size: 20px;
    font-weight: 700;
    color: #1f2430;
}
QLabel#pageSubtitle {
    color: #5b6270;
}
QLabel#bannerSuccess {
    background: #e7f6ed;
    border: 1px solid #bfe6cf;
    border-radius: 8px;
    color: #1f6b3d;
    padding: 6px 10px;
}
QLabel#bannerError {
    background: #fdeaea;
    border: 1px solid #f4b9b9;
    border-radius: 8px;
    color: #8f1d1d;
    padding: 6px 10px;
}
QLabel#bannerInfo {
    background: #eef2f8;
    border: 1px solid #d6dbe3;
    border-radius: 8px;
    color: #2b2f36;
    padding: 6px 10px;
}
QPushButton#secondaryButton {
    background: #eef2f8;
    color: #2b2f36;
}
QPushButton#secondaryButton:hover {
    background: #e1e7f2;
}
QStatusBar {
    background: #f5f7fb;
    color: #5b6270;
}
"""

DARK_STYLE = """
* {
    font-family: "Segoe UI";
    font-size: 12px;
}
QMainWindow, QDialog {
    background-color: #1f2430;
    color: #e6e9f0;
}
QLabel {
    color: #e6e9f0;
}
QMenuBar, QMenu {
    background-color: #1f2430;
    color: #e6e9f0;
}
QFrame#topBar {
    background: #252b3a;
    border: 1px solid #333b4d;
    border-radius: 12px;
}
QLabel#appTitle {
    font-size: 18px;
    font-weight: 700;
    color: #f3f5f8;
}
QLabel#appSubtitle {
    color: #aab3c2;
}
QLabel#userBadge {
    background: #2b3244;
    border: 1px solid #3b4256;
    border-radius: 10px;
    padding: 4px 10px;
    color: #e6e9f0;
}
QFrame#statCard {
    background: #252b3a;
    border: 1px solid #333b4d;
    border-radius: 12px;
}
QLabel#statValue {
    font-size: 22px;
    font-weight: 700;
    color: #f3f5f8;
}
QLabel#statLabel {
    color: #aab3c2;
}
QListWidget#navList {
    background: #252b3a;
    border: 1px solid #333b4d;
    border-radius: 12px;
}
QListWidget#navList::item {
    padding: 10px 12px;
    border-radius: 8px;
    margin: 4px 6px;
    color: #e6e9f0;
}
QListWidget#navList::item:selected {
    background: #6aa6ff;
    color: #0d1117;
}
QGroupBox {
    border: 1px solid #333b4d;
    border-radius: 10px;
    margin-top: 12px;
    background-color: #252b3a;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #e6e9f0;
    font-weight: 600;
}
QLineEdit, QComboBox, QDateTimeEdit, QSpinBox {
    background: #2b3244;
    color: #f3f5f8;
    border: 1px solid #3b4256;
    border-radius: 8px;
    padding: 6px 8px;
}
QComboBox QAbstractItemView {
    background: #2b3244;
    color: #f3f5f8;
}
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus, QSpinBox:focus {
    border: 1px solid #6aa6ff;
}
QPushButton {
    background: #6aa6ff;
    color: #0d1117;
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 600;
}
QPushButton:hover {
    background: #82b4ff;
}
QPushButton:disabled {
    background: #4a556d;
    color: #aab3c2;
}
QTableWidget {
    background: #252b3a;
    alternate-background-color: #2b3244;
    border: 1px solid #333b4d;
    border-radius: 8px;
    color: #e6e9f0;
}
QTableView::item {
    color: #e6e9f0;
    padding: 4px;
}
QTableView::item:selected {
    background: #3b4a66;
    color: #ffffff;
}
QHeaderView::section {
    background: #2b3244;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #3b4256;
    font-weight: 600;
    color: #e6e9f0;
}
QTabWidget::pane {
    border: 1px solid #333b4d;
    border-radius: 10px;
    background: #252b3a;
}
QTabBar::tab {
    background: #2b3244;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 6px 12px;
    margin-right: 2px;
    color: #e6e9f0;
}
QTabBar::tab:selected {
    background: #252b3a;
    color: #ffffff;
    border: 1px solid #3b4256;
    border-bottom-color: #252b3a;
}
QLabel#titleLabel {
    font-size: 18px;
    font-weight: 700;
    color: #f3f5f8;
}
QLabel#sectionLabel {
    font-weight: 600;
    color: #f3f5f8;
}
QLabel#pageTitle {
    font-size: 20px;
    font-weight: 700;
    color: #f3f5f8;
}
QLabel#pageSubtitle {
    color: #aab3c2;
}
QLabel#bannerSuccess {
    background: #223428;
    border: 1px solid #2f5b3a;
    border-radius: 8px;
    color: #bdeccf;
    padding: 6px 10px;
}
QLabel#bannerError {
    background: #3a1f22;
    border: 1px solid #6a2b34;
    border-radius: 8px;
    color: #f2b6b6;
    padding: 6px 10px;
}
QLabel#bannerInfo {
    background: #2b3244;
    border: 1px solid #3b4256;
    border-radius: 8px;
    color: #e6e9f0;
    padding: 6px 10px;
}
QPushButton#secondaryButton {
    background: #2b3244;
    color: #e6e9f0;
    border: 1px solid #3b4256;
}
QPushButton#secondaryButton:hover {
    background: #333b4d;
}
QStatusBar {
    background: #1f2430;
    color: #aab3c2;
}
"""


def apply_app_style(app: QApplication, theme: str) -> None:
    density = get_density()
    base = DARK_STYLE if theme == THEME_DARK else LIGHT_STYLE
    overrides = ""
    if density == DENSITY_COMPACT:
        overrides = """
* { font-size: 11px; }
QLineEdit, QComboBox, QDateTimeEdit, QSpinBox { padding: 4px 6px; }
QPushButton { padding: 4px 10px; }
QListWidget#navList::item { padding: 8px 10px; }
"""
    app.setStyleSheet(base + overrides)
    app.setFont(QFont("Segoe UI", 10))


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


def attach_theme_menu(window: QMainWindow, app: QApplication) -> None:
    menu = window.menuBar().addMenu("视图")
    light_action = QAction("浅色主题", window)
    light_action.setCheckable(True)
    dark_action = QAction("深色主题", window)
    dark_action.setCheckable(True)
    group = QActionGroup(window)
    group.setExclusive(True)
    group.addAction(light_action)
    group.addAction(dark_action)

    def apply_theme(theme: str) -> None:
        set_theme(theme)
        apply_app_style(app, theme)
        if theme == THEME_LIGHT:
            light_action.setChecked(True)
        else:
            dark_action.setChecked(True)

    light_action.triggered.connect(lambda: apply_theme(THEME_LIGHT))
    dark_action.triggered.connect(lambda: apply_theme(THEME_DARK))
    apply_theme(get_theme())

    menu.addAction(light_action)
    menu.addAction(dark_action)
