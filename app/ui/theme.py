"""Claude 风格主题系统 — 暖色调、圆润、极简。"""

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
    # 边框
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
    bg_input="#ffffff",
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
    btn_danger_bg="#ffebee",
    btn_danger_hover="#ffcdd2",
)

DARK = Palette(
    bg_base="#1a1a1a",
    bg_card="#262626",
    bg_elevated="#2e2e2e",
    bg_sidebar="#222222",
    bg_input="#2e2e2e",
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
    """从 Palette 生成完整 QSS。"""
    return f"""
/* ===== 全局 ===== */
* {{
    font-family: "SF Pro Text", "Helvetica Neue", ".AppleSystemUIFont", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {p.text_primary};
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
    border-bottom: 1px solid {p.border};
    padding: 2px 0;
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
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 24px 8px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {p.accent_soft};
    color: {p.accent};
}}

/* ===== 顶栏 ===== */
QFrame#topBar {{
    background: {p.bg_card};
    border: 1px solid {p.border};
    border-radius: 14px;
}}
QLabel#appTitle {{
    font-size: 17px;
    font-weight: 700;
    color: {p.text_primary};
    letter-spacing: -0.3px;
}}
QLabel#appSubtitle {{
    font-size: 12px;
    color: {p.text_tertiary};
    letter-spacing: 0.5px;
}}
QLabel#userBadge {{
    background: {p.accent_soft};
    color: {p.accent};
    border: none;
    border-radius: 20px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 600;
}}

/* ===== 统计卡片 ===== */
QFrame#statCard {{
    background: {p.bg_card};
    border: 1px solid {p.border};
    border-radius: 14px;
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
    letter-spacing: 0.3px;
}}

/* ===== 侧边导航 ===== */
QListWidget#navList {{
    background: {p.bg_sidebar};
    border: 1px solid {p.border};
    border-radius: 14px;
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
    border: 1px solid {p.border};
    border-radius: 14px;
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
    letter-spacing: 0.3px;
}}

/* ===== 输入框 ===== */
QLineEdit, QComboBox, QDateTimeEdit, QSpinBox {{
    background: {p.bg_input};
    color: {p.text_primary};
    border: 1.5px solid {p.border};
    border-radius: 10px;
    padding: 8px 12px;
    selection-background-color: {p.accent_soft};
}}
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus, QSpinBox:focus {{
    border-color: {p.accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox QAbstractItemView {{
    background: {p.bg_card};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 4px;
    selection-background-color: {p.accent_soft};
    selection-color: {p.accent};
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
    border: 1px solid {p.border};
}}
QPushButton#secondaryButton:hover {{
    background: {p.btn_secondary_hover};
}}
QPushButton#dangerButton {{
    background: {p.btn_danger_bg};
    color: {p.error_fg};
    border: 1px solid transparent;
}}
QPushButton#dangerButton:hover {{
    background: {p.btn_danger_hover};
}}

/* ===== 表格 ===== */
QTableWidget {{
    background: {p.bg_card};
    alternate-background-color: {p.table_alt_bg};
    border: 1px solid {p.border};
    border-radius: 10px;
    gridline-color: transparent;
}}
QTableView::item {{
    color: {p.text_primary};
    padding: 6px 8px;
    border-bottom: 1px solid {p.border_light};
}}
QTableView::item:selected {{
    background: {p.table_selected_bg};
    color: {p.accent};
}}
QHeaderView::section {{
    background: {p.table_header_bg};
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {p.border};
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.5px;
    color: {p.text_tertiary};
    text-transform: uppercase;
}}

/* ===== 标签页 ===== */
QTabWidget::pane {{
    background: {p.bg_card};
    border: 1px solid {p.border};
    border-radius: 12px;
}}
QTabBar::tab {{
    background: transparent;
    padding: 8px 16px;
    border-bottom: 2px solid transparent;
    color: {p.text_secondary};
    font-weight: 500;
}}
QTabBar::tab:selected {{
    color: {p.accent};
    border-bottom-color: {p.accent};
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
    letter-spacing: 0.2px;
}}

/* ===== 横幅消息 ===== */
QLabel#bannerSuccess {{
    background: {p.success_bg};
    color: {p.success_fg};
    border: 1px solid {p.success_fg}20;
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 500;
}}
QLabel#bannerError {{
    background: {p.error_bg};
    color: {p.error_fg};
    border: 1px solid {p.error_fg}20;
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 500;
}}
QLabel#bannerInfo {{
    background: {p.bg_card};
    color: {p.text_secondary};
    border: 1px solid {p.border};
    border-radius: 10px;
    padding: 8px 14px;
}}

/* ===== 状态栏 ===== */
QStatusBar {{
    background: {p.bg_base};
    color: {p.text_tertiary};
    border-top: 1px solid {p.border};
}}

/* ===== 滚动条 ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {p.border};
    border-radius: 4px;
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

/* ===== 工具提示 ===== */
QToolTip {{
    background: {p.bg_card};
    color: {p.text_primary};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 6px 10px;
}}

/* ===== 登录卡片 ===== */
QFrame#loginCard {{
    background: {p.bg_card};
    border: 1px solid {p.border};
    border-radius: 20px;
}}
"""
