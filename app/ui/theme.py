"""Claude 风格主题系统 — 无界感、暖色调、极简。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    # 背景
    bg_base: str
    bg_card: str
    bg_elevated: str
    bg_sidebar: str
    bg_input: str
    bg_input_focus: str
    # 文字
    text_primary: str
    text_secondary: str
    text_tertiary: str
    text_on_accent: str
    # 强调色
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    # 语义色
    success_fg: str
    success_bg: str
    error_fg: str
    error_bg: str
    warning_fg: str
    warning_bg: str
    # 边框（仅用于输入框聚焦等必要场景）
    border: str
    border_light: str
    # 导航
    nav_selected_bg: str
    nav_selected_fg: str
    nav_hover_bg: str
    # 表格
    table_header_bg: str
    table_alt_bg: str
    table_selected_bg: str
    # 按钮
    btn_secondary_bg: str
    btn_secondary_hover: str
    btn_secondary_fg: str
    btn_disabled_bg: str
    btn_disabled_fg: str
    btn_danger_bg: str
    btn_danger_hover: str


LIGHT = Palette(
    bg_base="#faf9f7",
    bg_card="#ffffff",
    bg_elevated="#ffffff",
    bg_sidebar="#f5f4f2",
    bg_input="#f5f4f2",
    bg_input_focus="#ffffff",
    text_primary="#1a1a1a",
    text_secondary="#6b6b6b",
    text_tertiary="#9a9a9a",
    text_on_accent="#ffffff",
    accent="#da7756",
    accent_hover="#c4654a",
    accent_pressed="#b05a3f",
    accent_soft="#fdf0eb",
    success_fg="#2e7d32",
    success_bg="#e8f5e9",
    error_fg="#c62828",
    error_bg="#ffebee",
    warning_fg="#e65100",
    warning_bg="#fff3e0",
    border="#e8e8e8",
    border_light="#f0f0f0",
    nav_selected_bg="#ffffff",
    nav_selected_fg="#1a1a1a",
    nav_hover_bg="#ececea",
    table_header_bg="#f5f4f2",
    table_alt_bg="#faf9f7",
    table_selected_bg="#fdf0eb",
    btn_secondary_bg="#f0efed",
    btn_secondary_hover="#e5e4e2",
    btn_secondary_fg="#1a1a1a",
    btn_disabled_bg="#e8e8e8",
    btn_disabled_fg="#b0b0b0",
    btn_danger_bg="#fff0ee",
    btn_danger_hover="#ffe0da",
)

DARK = Palette(
    bg_base="#1a1a1a",
    bg_card="#242424",
    bg_elevated="#2e2e2e",
    bg_sidebar="#202020",
    bg_input="#2a2a2a",
    bg_input_focus="#333333",
    text_primary="#ececec",
    text_secondary="#a0a0a0",
    text_tertiary="#707070",
    text_on_accent="#1a1a1a",
    accent="#e8956f",
    accent_hover="#d4845f",
    accent_pressed="#c07350",
    accent_soft="#3d2a22",
    success_fg="#81c784",
    success_bg="#1b3a1d",
    error_fg="#ef9a9a",
    error_bg="#3d1a1a",
    warning_fg="#ffb74d",
    warning_bg="#3d2e1a",
    border="#333333",
    border_light="#2a2a2a",
    nav_selected_bg="#333333",
    nav_selected_fg="#ececec",
    nav_hover_bg="#2a2a2a",
    table_header_bg="#2a2a2a",
    table_alt_bg="#222222",
    table_selected_bg="#3d2a22",
    btn_secondary_bg="#333333",
    btn_secondary_hover="#3d3d3d",
    btn_secondary_fg="#ececec",
    btn_disabled_bg="#333333",
    btn_disabled_fg="#555555",
    btn_danger_bg="#3d1a1a",
    btn_danger_hover="#4d2020",
)


def build_stylesheet(p: Palette) -> str:
    """从 Palette 生成无界风格 QSS。"""
    return f"""
/* ===== 全局 ===== */
* {{
    font-family: "SF Pro Text", "Helvetica Neue", ".AppleSystemUIFont", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {p.text_primary};
    border: none;
}}

QMainWindow, QDialog {{
    background-color: {p.bg_base};
}}

QLabel {{
    color: {p.text_primary};
    background: transparent;
}}

/* ===== 菜单栏 ===== */
QMenuBar {{
    background: {p.bg_base};
    border: none;
    padding: 4px 8px;
}}
QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 6px;
}}
QMenuBar::item:selected {{
    background: {p.nav_hover_bg};
}}
QMenu {{
    background: {p.bg_card};
    border: none;
    border-radius: 12px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 24px 8px 14px;
    border-radius: 8px;
}}
QMenu::item:selected {{
    background: {p.accent_soft};
    color: {p.accent};
}}

/* ===== 顶栏 ===== */
QFrame#topBar {{
    background: transparent;
}}
QLabel#appTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {p.text_primary};
    letter-spacing: -0.3px;
}}
QLabel#appSubtitle {{
    font-size: 11px;
    color: {p.text_tertiary};
}}
QLabel#userBadge {{
    background: {p.accent_soft};
    color: {p.accent};
    border-radius: 20px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 600;
}}

/* ===== 侧边导航 ===== */
QListWidget#navList {{
    background: {p.bg_sidebar};
    border: none;
    border-radius: 16px;
    outline: none;
}}
QListWidget#navList::item {{
    padding: 11px 16px;
    border-radius: 10px;
    margin: 2px 8px;
    color: {p.text_secondary};
    font-size: 13px;
    font-weight: 500;
}}
QListWidget#navList::item:hover {{
    background: {p.nav_hover_bg};
    color: {p.text_primary};
}}
QListWidget#navList::item:selected {{
    background: {p.nav_selected_bg};
    color: {p.nav_selected_fg};
    font-weight: 600;
}}

/* ===== 分组框 ===== */
QGroupBox {{
    background: {p.bg_card};
    border: 1px solid {p.border_light};
    border-radius: 16px;
    margin-top: 14px;
    padding-top: 16px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: {p.text_secondary};
    font-weight: 600;
    font-size: 12px;
}}

/* ===== 输入框 ===== */
QLineEdit, QDateTimeEdit, QSpinBox {{
    background: {p.bg_input};
    color: {p.text_primary};
    border: 1.5px solid transparent;
    border-radius: 10px;
    padding: 8px 12px;
}}
QLineEdit:focus, QDateTimeEdit:focus, QSpinBox:focus {{
    background: {p.bg_input_focus};
    border-color: {p.accent_soft};
}}

/* ===== 下拉选择框（候选框） ===== */
QComboBox {{
    background: {p.bg_input};
    color: {p.text_primary};
    border: 1.5px solid transparent;
    border-radius: 10px;
    padding: 8px 12px;
    padding-right: 32px;
    min-height: 20px;
}}
QComboBox:focus {{
    background: {p.bg_input_focus};
    border: 1.5px solid {p.accent};
    border-radius: 10px;
}}
QComboBox:hover {{
    background: {p.bg_input_focus};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    border: none;
    width: 28px;
    border-top-right-radius: 10px;
    border-bottom-right-radius: 10px;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {p.text_tertiary};
    margin-right: 6px;
}}
QComboBox:on {{
    border: 1.5px solid {p.accent};
    border-radius: 10px;
    background: {p.bg_input_focus};
}}
QComboBox::down-arrow:on {{
    border-top-color: {p.accent};
}}
QComboBox QAbstractItemView {{
    background: {p.bg_card};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 12px;
    padding: 6px;
    outline: none;
    selection-background-color: {p.accent_soft};
    selection-color: {p.accent};
}}
QComboBox QAbstractItemView::item {{
    padding: 8px 12px;
    border-radius: 8px;
    min-height: 24px;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {p.nav_hover_bg};
    color: {p.text_primary};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {p.accent_soft};
    color: {p.accent};
}}
QComboBox QAbstractItemView::viewport {{
    background: transparent;
}}
QComboBox QListView {{
    background: {p.bg_card};
    border: 1px solid {p.border};
    border-radius: 12px;
    padding: 6px;
    outline: none;
}}
QComboBox QListView::item {{
    padding: 8px 12px;
    border-radius: 8px;
    min-height: 24px;
}}
QComboBox QListView::item:hover {{
    background: {p.nav_hover_bg};
    color: {p.text_primary};
}}
QComboBox QListView::item:selected {{
    background: {p.accent_soft};
    color: {p.accent};
}}
QComboBox QListView::viewport {{
    background: transparent;
}}

/* ===== 模式选择器（pill-style） ===== */
QComboBox#modeSelector {{
    background: {p.btn_secondary_bg};
    color: {p.btn_secondary_fg};
    border: 1px solid {p.border_light};
    border-radius: 20px;
    padding: 6px 16px 6px 14px;
    padding-right: 30px;
    font-weight: 600;
    font-size: 12px;
    min-height: 18px;
}}
QComboBox#modeSelector:hover {{
    background: {p.btn_secondary_hover};
    border-color: {p.border};
}}
QComboBox#modeSelector:on {{
    background: {p.accent_soft};
    color: {p.accent};
    border-color: {p.accent};
}}
QComboBox#modeSelector::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox#modeSelector::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p.text_tertiary};
    margin-right: 4px;
}}

/* ===== 按钮 ===== */
QPushButton {{
    background: {p.accent};
    color: {p.text_on_accent};
    border: none;
    border-radius: 10px;
    padding: 8px 18px;
    font-weight: 600;
    font-size: 13px;
}}
QPushButton:hover {{
    background: {p.accent_hover};
}}
QPushButton:pressed {{
    background: {p.accent_pressed};
    padding-top: 9px;
    padding-bottom: 7px;
}}
QPushButton:disabled {{
    background: {p.btn_disabled_bg};
    color: {p.btn_disabled_fg};
}}
QPushButton#primaryButton {{
    background: {p.accent};
    color: {p.text_on_accent};
}}
QPushButton#primaryButton:hover {{
    background: {p.accent_hover};
}}
QPushButton#secondaryButton {{
    background: {p.btn_secondary_bg};
    color: {p.btn_secondary_fg};
}}
QPushButton#secondaryButton:hover {{
    background: {p.btn_secondary_hover};
}}
QPushButton#dangerButton {{
    background: {p.btn_danger_bg};
    color: {p.error_fg};
}}
QPushButton#dangerButton:hover {{
    background: {p.btn_danger_hover};
}}
QPushButton#sidebarToggle {{
    background: transparent;
    color: {p.text_secondary};
    font-size: 18px;
    padding: 8px;
    border-radius: 8px;
    min-width: 36px;
    max-width: 36px;
}}
QPushButton#sidebarToggle:hover {{
    background: {p.nav_hover_bg};
    color: {p.text_primary};
}}

/* ===== 表格 ===== */
QTableWidget {{
    background: {p.bg_card};
    alternate-background-color: {p.table_alt_bg};
    border: none;
    border-radius: 12px;
    gridline-color: transparent;
}}
QTableView::item {{
    color: {p.text_primary};
    padding: 6px 8px;
}}
QTableView::item:selected {{
    background: {p.table_selected_bg};
    color: {p.accent};
}}
QTableView::item:hover {{
    background: {p.nav_hover_bg};
}}
QHeaderView::section {{
    background: {p.table_header_bg};
    padding: 8px 10px;
    border: none;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.5px;
    color: {p.text_tertiary};
    border-bottom: 1px solid {p.border_light};
}}

/* ===== 页面标题 ===== */
QLabel#pageTitle {{
    font-size: 22px;
    font-weight: 700;
    color: {p.text_primary};
    letter-spacing: -0.5px;
}}
QLabel#pageSubtitle {{
    font-size: 13px;
    color: {p.text_secondary};
}}

/* ===== 统计卡片 ===== */
QFrame#statCard {{
    background: {p.bg_card};
    border: 1px solid {p.border_light};
    border-radius: 16px;
}}
QLabel#statValue {{
    font-size: 28px;
    font-weight: 700;
    color: {p.text_primary};
    letter-spacing: -1px;
}}
QLabel#statLabel {{
    font-size: 12px;
    color: {p.text_secondary};
}}

/* ===== 横幅消息 ===== */
QLabel#bannerSuccess {{
    background: {p.success_bg};
    color: {p.success_fg};
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 500;
}}
QLabel#bannerError {{
    background: {p.error_bg};
    color: {p.error_fg};
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 500;
}}
QLabel#bannerInfo {{
    background: transparent;
    color: {p.text_secondary};
    padding: 8px 14px;
}}

/* ===== 状态栏 ===== */
QStatusBar {{
    background: transparent;
    color: {p.text_tertiary};
}}

/* ===== 滚动条 ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {p.border};
    border-radius: 3px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p.text_tertiary};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {p.border};
    border-radius: 3px;
    min-width: 32px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {p.text_tertiary};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}

/* ===== 登录卡片 ===== */
QFrame#loginCard {{
    background: {p.bg_card};
    border: 1px solid {p.border_light};
    border-radius: 24px;
}}

/* ===== 工具提示 ===== */
QToolTip {{
    background: {p.bg_card};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 6px 10px;
}}

/* ===== 日历控件 ===== */
QCalendarWidget {{
    background: {p.bg_card};
    border: 1px solid {p.border};
    border-radius: 12px;
}}
QCalendarWidget QWidget {{
    alternate-background-color: {p.table_alt_bg};
}}
QCalendarWidget QToolButton {{
    background: transparent;
    color: {p.text_primary};
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 600;
    font-size: 13px;
}}
QCalendarWidget QToolButton:hover {{
    background: {p.nav_hover_bg};
}}
QCalendarWidget QToolButton::menu-indicator {{
    image: none;
}}
QCalendarWidget QMenu {{
    background: {p.bg_card};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 4px;
}}
QCalendarWidget QAbstractItemView {{
    background: {p.bg_card};
    color: {p.text_primary};
    border: none;
    selection-background-color: {p.accent_soft};
    selection-color: {p.accent};
    alternate-background-color: {p.table_alt_bg};
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background: {p.bg_card};
    border-bottom: 1px solid {p.border_light};
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    padding: 4px;
}}
QCalendarWidget QWidget#qt_calendar_monthbutton {{
    background: transparent;
    color: {p.text_primary};
    font-weight: 700;
    font-size: 14px;
    padding: 4px 8px;
    border-radius: 6px;
}}
QCalendarWidget QWidget#qt_calendar_monthbutton:hover {{
    background: {p.nav_hover_bg};
}}
QCalendarWidget QWidget#qt_calendar_yearbutton {{
    background: transparent;
    color: {p.text_primary};
    font-weight: 700;
    font-size: 14px;
    padding: 4px 8px;
    border-radius: 6px;
}}
QCalendarWidget QWidget#qt_calendar_yearbutton:hover {{
    background: {p.nav_hover_bg};
}}
QCalendarWidget QTableView {{
    background: {p.bg_card};
    border: none;
    border-radius: 0 0 12px 12px;
    selection-background-color: {p.accent_soft};
    selection-color: {p.accent};
    outline: none;
    gridline-color: {p.border_light};
}}
QCalendarWidget QTableView::item {{
    padding: 4px;
    border-radius: 6px;
}}
QCalendarWidget QTableView::item:hover {{
    background: {p.nav_hover_bg};
}}
QCalendarWidget QTableView::item:selected {{
    background: {p.accent_soft};
    color: {p.accent};
}}

/* ===== 堆叠页面 ===== */
QStackedWidget {{
    background: transparent;
}}

/* ===== 滚动区域 ===== */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

/* ===== 滚动区域内的分组框 ===== */
QScrollArea QGroupBox {{
    background: {p.bg_card};
    border: 1px solid {p.border_light};
    border-radius: 16px;
    margin-top: 14px;
    padding-top: 16px;
}}
QScrollArea QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: {p.text_secondary};
    font-weight: 600;
    font-size: 12px;
}}

/* ===== 日期编辑弹窗 ===== */
QDateEdit {{
    background: {p.bg_input};
    color: {p.text_primary};
    border: 1.5px solid transparent;
    border-radius: 10px;
    padding: 8px 12px;
}}
QDateEdit:focus {{
    background: {p.bg_input_focus};
    border-color: {p.accent_soft};
}}
QDateEdit::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    border: none;
    width: 28px;
    border-top-right-radius: 10px;
    border-bottom-right-radius: 10px;
}}
QDateEdit::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {p.text_tertiary};
    margin-right: 6px;
}}
QDateEdit QCalendarWidget {{
    background: {p.bg_card};
    border: 1px solid {p.border};
    border-radius: 12px;
}}

/* ===== 统计卡片（带彩色左边框） ===== */
QFrame#statCard {{
    background: {p.bg_card};
    border: 1px solid {p.border_light};
    border-left: 4px solid {p.accent};
    border-radius: 16px;
}}
QFrame#statCard[accentColor="success"] {{
    border-left: 4px solid {p.success_fg};
}}
QFrame#statCard[accentColor="warning"] {{
    border-left: 4px solid {p.warning_fg};
}}
QFrame#statCard[accentColor="error"] {{
    border-left: 4px solid {p.error_fg};
}}
QFrame#statCard[accentColor="accent"] {{
    border-left: 4px solid {p.accent};
}}

/* ===== 签到码卡片 ===== */
QFrame#checkinCodeFrame {{
    background: {p.bg_card};
    border: 2px solid {p.accent};
    border-radius: 16px;
}}
QLabel#checkinCodeTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {p.text_secondary};
}}
QLabel#checkinCodeLabel {{
    font-size: 42px;
    font-weight: 700;
    color: {p.accent};
    letter-spacing: 6px;
}}

/* ===== 分组框内的标签卡片覆盖 ===== */
QGroupBox QLabel {{
    border: none;
    background: transparent;
}}

/* ===== 对话框 ===== */
QDialog {{
    background-color: {p.bg_base};
}}

/* ===== 输入框聚焦增强 ===== */
QLineEdit:focus, QSpinBox:focus, QDateTimeEdit:focus, QDateEdit:focus {{
    background: {p.bg_input_focus};
    border: 1.5px solid {p.accent};
    border-radius: 10px;
}}
QTextEdit {{
    background: {p.bg_input};
    color: {p.text_primary};
    border: 1.5px solid transparent;
    border-radius: 10px;
    padding: 8px 12px;
}}
QTextEdit:focus {{
    background: {p.bg_input_focus};
    border: 1.5px solid {p.accent};
    border-radius: 10px;
}}
QPlainTextEdit {{
    background: {p.bg_input};
    color: {p.text_primary};
    border: 1.5px solid transparent;
    border-radius: 10px;
    padding: 8px 12px;
}}
QPlainTextEdit:focus {{
    background: {p.bg_input_focus};
    border: 1.5px solid {p.accent};
    border-radius: 10px;
}}
"""
