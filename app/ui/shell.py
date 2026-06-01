from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
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
    get_theme,
    set_density,
    set_theme,
)


class NavigationWindow(QMainWindow):
    def __init__(self, title: str, user_label: str) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self._nav = QListWidget()
        self._nav.setObjectName("navList")
        self._nav.setIconSize(QSize(18, 18))
        self._nav.setFixedWidth(220)
        self._nav.setSpacing(2)
        self._nav.setFocusPolicy(Qt.NoFocus)

        self._stack = QStackedWidget()
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._page_keys: list[str] = []

        top_bar = self._build_topbar(user_label)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(16)
        body_layout.addWidget(self._nav)
        body_layout.addWidget(self._stack, 1)

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(16)
        root_layout.addWidget(top_bar)
        root_layout.addLayout(body_layout)

        root = QWidget()
        root.setLayout(root_layout)
        self.setCentralWidget(root)

    def set_pages(self, pages: list[tuple[str, str, QWidget, object | None]]) -> None:
        self._nav.clear()
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

        self._apply_default_page()

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

    def _open_settings(self, app: QApplication) -> None:
        pages = list(zip(self._page_keys, [self._nav.item(i).text() for i in range(self._nav.count())]))
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

    @staticmethod
    def _build_topbar(user_label: str) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topBar")
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)

        title = QLabel("Campus Scheduler")
        title.setObjectName("appTitle")
        subtitle = QLabel("校园报名与排班系统")
        subtitle.setObjectName("appSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        user = QLabel(user_label)
        user.setObjectName("userBadge")

        layout.addLayout(title_col)
        layout.addStretch(1)
        layout.addWidget(user)
        bar.setLayout(layout)
        return bar
