from __future__ import annotations

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
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

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
    def __init__(self, title: str, user_label: str) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self._nav_expanded = True

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

        top_bar = self._build_topbar(user_label)

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

        # 更新按钮箭头
        self._toggle_btn.setText("☰" if self._nav_expanded else "≫")

    def attach_menus(self, app: QApplication) -> None:
        menu_bar = self.menuBar()
        menu_bar.clear()
        file_menu = menu_bar.addMenu("文件")
        view_menu = menu_bar.addMenu("视图")
        help_menu = menu_bar.addMenu("帮助")

        settings_action = QAction("设置...", self)
        settings_action.triggered.connect(lambda: self._open_settings(app))
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(settings_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        theme_group = QActionGroup(self)
        light_action = QAction("浅色主题", self, checkable=True)
        dark_action = QAction("深色主题", self, checkable=True)
        theme_group.addAction(light_action)
        theme_group.addAction(dark_action)
        theme_group.setExclusive(True)
        theme = get_theme()
        light_action.setChecked(theme == THEME_LIGHT)
        dark_action.setChecked(theme == THEME_DARK)
        light_action.triggered.connect(lambda: self._apply_theme(app, THEME_LIGHT))
        dark_action.triggered.connect(lambda: self._apply_theme(app, THEME_DARK))
        view_menu.addAction(light_action)
        view_menu.addAction(dark_action)
        view_menu.addSeparator()

        density_group = QActionGroup(self)
        density = get_density()
        compact_action = QAction("紧凑密度", self, checkable=True)
        comfortable_action = QAction("舒适密度", self, checkable=True)
        density_group.addAction(compact_action)
        density_group.addAction(comfortable_action)
        density_group.setExclusive(True)
        compact_action.setChecked(density == DENSITY_COMPACT)
        comfortable_action.setChecked(density == DENSITY_COMFORTABLE)
        compact_action.triggered.connect(lambda: self._apply_density(app, DENSITY_COMPACT))
        comfortable_action.triggered.connect(lambda: self._apply_density(app, DENSITY_COMFORTABLE))
        view_menu.addAction(comfortable_action)
        view_menu.addAction(compact_action)

        about_action = QAction("关于", self)
        about_action.triggered.connect(lambda: self.statusBar().showMessage("Campus Scheduler · 校园报名与排班系统"))
        help_menu.addAction(about_action)

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
        if 0 <= index < len(self._pages):
            page = self._pages[index]
            if hasattr(page, "refresh") and callable(page.refresh):
                page.refresh()

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

    def _build_topbar(self, user_label: str) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topBar")
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

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

        # 右侧：用户标签 + 登出按钮
        p = get_palette()
        user = QLabel(user_label)
        user.setObjectName("userBadge")
        layout.addWidget(user)

        logout_btn = QPushButton("登出")
        logout_btn.setObjectName("logoutButton")
        logout_btn.setCursor(Qt.PointingHandCursor)
        logout_btn.setToolTip("退出当前账号")
        logout_btn.setStyleSheet(
            f"QPushButton#logoutButton {{"
            f" background: {p.btn_secondary_bg}; color: {p.text_secondary};"
            f" border: 1px solid {p.border_light}; border-radius: 6px;"
            f" padding: 4px 12px; font-size: 12px; font-weight: 500;"
            f"}}"
            f"QPushButton#logoutButton:hover {{"
            f" background: {p.btn_danger_bg}; color: {p.error_fg};"
            f" border-color: {p.error_fg};"
            f"}}"
        )
        def _logout():
            # Clear remote token if available
            try:
                if hasattr(self, '_api_client') and self._api_client:
                    self._api_client.set_token("")
            except Exception:
                pass
            self.close()
        logout_btn.clicked.connect(_logout)
        layout.addWidget(logout_btn)

        bar.setLayout(layout)
        return bar
