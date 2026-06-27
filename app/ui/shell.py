from __future__ import annotations

import logging

from PySide6.QtCore import QPropertyAnimation, QSize, Qt, QSettings
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import User
from app.ui.settings_dialog import SettingsDialog
from app.ui.style import (
    DENSITY_COMFORTABLE,
    DENSITY_COMPACT,
    THEME_DARK,
    THEME_LIGHT,
    apply_app_style,
    get_default_page,
    get_density,
    get_palette,
    get_theme,
    set_density,
    set_theme,
)

NAV_EXPANDED_WIDTH = 200
NAV_COLLAPSED_WIDTH = 56


class NavigationWindow(QMainWindow):
    def __init__(self, title: str, user: User) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self._user = user
        self._nav_expanded = True
        self._app: QApplication | None = None

        # 恢复窗口几何信息
        settings = QSettings("CampusScheduler", "CampusScheduler")
        geometry = settings.value("ui/window_geometry")
        if geometry:
            self.restoreGeometry(geometry)

        # 状态栏
        self.statusBar().showMessage("就绪")

        # 侧边导航
        self._nav = QListWidget()
        self._nav.setObjectName("navList")
        self._nav.setIconSize(QSize(18, 18))
        self._nav.setMinimumWidth(NAV_COLLAPSED_WIDTH)
        self._nav.setMaximumWidth(NAV_EXPANDED_WIDTH)
        self._nav.resize(NAV_EXPANDED_WIDTH, self._nav.height())
        self._nav.setSpacing(2)
        self._nav.setFocusPolicy(Qt.NoFocus)

        self._stack = QStackedWidget()
        self._nav.currentRowChanged.connect(self._on_page_changed)
        self._page_keys: list[str] = []
        self._pages: list[QWidget] = []

        # 存储页面标题用于折叠时显示
        self._page_titles: list[str] = []

        top_bar = self._build_topbar(user)

        # 顶栏与内容之间的分隔线
        p = get_palette()
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFixedHeight(1)
        separator.setStyleSheet(f"background: {p.border_light}; border: none;")

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)
        body_layout.addWidget(self._nav)
        body_layout.addWidget(self._stack, 1)

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(16, 12, 16, 16)
        root_layout.setSpacing(0)
        root_layout.addWidget(top_bar)
        root_layout.addWidget(separator)
        root_layout.addSpacing(12)
        root_layout.addLayout(body_layout)

        root = QWidget()
        root.setLayout(root_layout)
        self.setCentralWidget(root)

        # 键盘快捷键：Ctrl+1 ~ Ctrl+5 切换页面
        self._page_shortcuts: list[QShortcut] = []
        for i in range(5):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            shortcut.activated.connect(lambda checked=False, idx=i: self._switch_to_page(idx))
            self._page_shortcuts.append(shortcut)

    def closeEvent(self, event) -> None:
        """窗口关闭时保存几何信息。"""
        settings = QSettings("CampusScheduler", "CampusScheduler")
        settings.setValue("ui/window_geometry", self.saveGeometry())
        super().closeEvent(event)

    def set_pages(self, pages: list[tuple[str, str, QWidget, object | None]]) -> None:
        self._nav.clear()
        self._page_titles = []
        self._pages = []
        while self._stack.count() > 0:
            widget = self._stack.widget(0)
            self._stack.removeWidget(widget)
            widget.setParent(None)

        self._page_keys = []
        for key, title, widget, icon in pages:
            item = QListWidgetItem(title)
            if icon:
                item.setIcon(icon)
            self._nav.addItem(item)
            self._stack.addWidget(widget)
            self._page_keys.append(key)
            self._page_titles.append(title)
            self._pages.append(widget)

        self._apply_default_page()

    def _toggle_sidebar(self) -> None:
        self._nav_expanded = not self._nav_expanded
        target = NAV_EXPANDED_WIDTH if self._nav_expanded else NAV_COLLAPSED_WIDTH

        # 更新导航项文字
        for i in range(self._nav.count()):
            item = self._nav.item(i)
            if self._nav_expanded:
                item.setText(self._page_titles[i])
            else:
                item.setText("")

        # 动画
        self._anim = QPropertyAnimation(self._nav, b"minimumWidth")
        self._anim.setDuration(200)
        self._anim.setStartValue(self._nav.width())
        self._anim.setEndValue(target)
        self._anim.start()

        self._anim2 = QPropertyAnimation(self._nav, b"maximumWidth")
        self._anim2.setDuration(200)
        self._anim2.setStartValue(self._nav.width())
        self._anim2.setEndValue(target)
        self._anim2.start()

    def _apply_default_page(self) -> None:
        if not self._page_keys:
            return
        default_key = get_default_page()
        if default_key and default_key in self._page_keys:
            self._nav.setCurrentRow(self._page_keys.index(default_key))
        else:
            self._nav.setCurrentRow(0)

    def _on_page_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        # 更新状态栏显示当前页面名称
        if 0 <= index < len(self._page_titles):
            self.statusBar().showMessage(self._page_titles[index])
        # Refresh the page data when switching tabs
        # 单页面刷新异常不应阻塞页面切换，仅记录日志并在状态栏提示，避免拖垮主框架
        if 0 <= index < len(self._pages):
            page = self._pages[index]
            if hasattr(page, "refresh") and callable(page.refresh):
                try:
                    page.refresh()
                except Exception as exc:  # noqa: BLE001 - UI 层兜底，需保留异常细节用于排查
                    logging.getLogger(__name__).exception("页面 %s 刷新失败: %s", type(page).__name__, exc)
                    self.statusBar().showMessage(f"页面刷新失败：{exc}", 5000)

    def _switch_to_page(self, index: int) -> None:
        """通过快捷键切换到指定页面。"""
        if 0 <= index < self._nav.count():
            self._nav.setCurrentRow(index)

    def _open_settings(self, app: QApplication) -> None:
        pages = list(zip(self._page_keys, self._page_titles))
        dialog = SettingsDialog(app, pages)
        if dialog.exec() == SettingsDialog.Accepted:
            self._apply_default_page()

    @staticmethod
    def _apply_theme(app: QApplication, theme: str) -> None:
        set_theme(theme)
        apply_app_style(app, theme)

    @staticmethod
    def _apply_density(app: QApplication, density: str) -> None:
        set_density(density)
        apply_app_style(app, get_theme())

    def _build_topbar(self, user: User) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topBar")
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        p = get_palette()

        # 左侧：汉堡按钮
        self._toggle_btn = QPushButton("☰")
        self._toggle_btn.setObjectName("sidebarToggle")
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setToolTip("切换侧边栏")
        self._toggle_btn.clicked.connect(self._toggle_sidebar)
        layout.addWidget(self._toggle_btn)

        # 中间：标题（居中）
        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(1)
        title = QLabel("Campus Scheduler")
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("校园报名与排班系统")
        subtitle.setObjectName("appSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        layout.addLayout(title_col, 1)

        # 右侧：用户头像按钮（下拉菜单整合帮助/设置/关于/角色/登出）
        avatar_btn = QPushButton(user.username[:1].upper())
        avatar_btn.setObjectName("userAvatarButton")
        avatar_btn.setCursor(Qt.PointingHandCursor)
        avatar_btn.setToolTip(f"{user.username} · 点击查看菜单")
        avatar_btn.setFixedSize(38, 38)
        avatar_btn.setStyleSheet(f"""
            QPushButton#userAvatarButton {{
                background: {p.accent};
                color: {p.text_on_accent};
                border: none;
                border-radius: 19px;
                font-size: 16px;
                font-weight: 700;
            }}
            QPushButton#userAvatarButton:hover {{
                background: {p.accent_hover};
            }}
            QPushButton#userAvatarButton:pressed {{
                background: {p.accent_pressed};
            }}
        """)

        # 用户名标签（在头像左侧）
        name_label = QLabel(user.username)
        name_label.setObjectName("userNameLabel")
        name_label.setStyleSheet(
            f"color: {p.text_primary}; font-weight: 600; font-size: 13px; border: none;"
        )
        layout.addWidget(name_label)
        layout.addWidget(avatar_btn)

        # 下拉菜单
        menu = QMenu(avatar_btn)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {p.bg_card};
                color: {p.text_primary};
                border: 1px solid {p.border_light};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background: {p.accent_soft};
                color: {p.text_primary};
            }}
            QMenu::separator {{
                height: 1px;
                background: {p.border_light};
                margin: 4px 8px;
            }}
            QMenu::title {{
                background: transparent;
                color: {p.text_tertiary};
                font-size: 11px;
                padding: 4px 12px 2px 12px;
            }}
        """)

        # 菜单标题：用户名 + 角色
        role_text = {
            "super_admin": "超级管理员",
            "organizer": "组织者",
            "student": "学生",
        }.get(user.role.value, user.role.value)
        menu.setTitle(f"{user.username}  ·  {role_text}")

        # 设置...
        settings_action = QAction("设置...", menu)
        settings_action.triggered.connect(lambda: self._open_settings(QApplication.instance()))
        menu.addAction(settings_action)

        menu.addSeparator()

        # 主题子菜单
        theme_menu = menu.addMenu("主题")
        theme_group = QActionGroup(theme_menu)
        light_action = QAction("浅色", theme_menu, checkable=True)
        dark_action = QAction("深色", theme_menu, checkable=True)
        theme_group.addAction(light_action)
        theme_group.addAction(dark_action)
        theme_group.setExclusive(True)
        theme = get_theme()
        light_action.setChecked(theme == THEME_LIGHT)
        dark_action.setChecked(theme == THEME_DARK)
        light_action.triggered.connect(lambda: self._apply_theme(QApplication.instance(), THEME_LIGHT))
        dark_action.triggered.connect(lambda: self._apply_theme(QApplication.instance(), THEME_DARK))
        theme_menu.addAction(light_action)
        theme_menu.addAction(dark_action)

        # 密度子菜单
        density_menu = menu.addMenu("显示密度")
        density_group = QActionGroup(density_menu)
        compact_action = QAction("紧凑", density_menu, checkable=True)
        comfortable_action = QAction("舒适", density_menu, checkable=True)
        density_group.addAction(compact_action)
        density_group.addAction(comfortable_action)
        density_group.setExclusive(True)
        density = get_density()
        compact_action.setChecked(density == DENSITY_COMPACT)
        comfortable_action.setChecked(density == DENSITY_COMFORTABLE)
        compact_action.triggered.connect(lambda: self._apply_density(QApplication.instance(), DENSITY_COMPACT))
        comfortable_action.triggered.connect(lambda: self._apply_density(QApplication.instance(), DENSITY_COMFORTABLE))
        density_menu.addAction(comfortable_action)
        density_menu.addAction(compact_action)

        menu.addSeparator()

        # 关于
        about_action = QAction("关于", menu)
        about_action.triggered.connect(
            lambda: self.statusBar().showMessage("Campus Scheduler · 校园报名与排班系统", 5000)
        )
        menu.addAction(about_action)

        # 登出
        menu.addSeparator()
        logout_action = QAction("登出", menu)
        logout_action.triggered.connect(self.close)
        menu.addAction(logout_action)

        avatar_btn.setMenu(menu)
        # QPushButton.setMenu 已内置「点击即弹出菜单」行为，
        # 无需 setPopupMode（该方法属 QToolButton，对 QPushButton 调用会抛 AttributeError）

        bar.setLayout(layout)
        return bar
