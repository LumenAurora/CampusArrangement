from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QPropertyAnimation, QRect, QSize, Qt, QSettings
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QPainter, QShortcut, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QStyle,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import User
from app.infrastructure.repositories import UserRepository
from app.ui.account_settings import make_circular_pixmap, make_initial_pixmap
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

# 头像存储根目录：app/resources/uploads/（与 account_settings.py 保持一致）
_AVATAR_ROOT = Path(__file__).resolve().parent.parent / "resources" / "uploads"


class _SidebarItemDelegate(QStyledItemDelegate):
    """Draw sidebar items so collapsed icons stay visually centered."""

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), 54)

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        p = get_palette()
        collapsed = bool(option.widget and option.widget.property("collapsed"))
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        item_rect = option.rect.adjusted(8, 3, -8, -3)
        bg = ""
        if selected:
            bg = p.nav_selected_bg
        elif hovered:
            bg = p.nav_hover_bg
        if bg:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(bg))
            painter.drawRoundedRect(item_rect, 10, 10)

        icon = index.data(Qt.DecorationRole)
        icon_size = 22
        if collapsed:
            icon_rect = QRect(
                item_rect.center().x() - icon_size // 2,
                item_rect.center().y() - icon_size // 2,
                icon_size,
                icon_size,
            )
        else:
            icon_rect = QRect(item_rect.left() + 14, item_rect.center().y() - icon_size // 2, icon_size, icon_size)

        if icon and not icon.isNull():
            icon.paint(painter, icon_rect, Qt.AlignCenter)

        if not collapsed:
            text = index.data(Qt.DisplayRole) or index.data(Qt.UserRole) or ""
            text_rect = item_rect.adjusted(14 + icon_size + 14, 0, -12, 0)
            painter.setPen(QColor(p.nav_selected_fg if selected else p.text_secondary))
            font = option.font
            font.setWeight(600 if selected else 500)
            painter.setFont(font)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, str(text))

        painter.restore()


class NavigationWindow(QMainWindow):
    def __init__(self, title: str, user: User) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self._user = user
        self._nav_expanded = True
        self._app: QApplication | None = None
        self._user_repo: UserRepository | None = None

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
        self._nav.setProperty("collapsed", False)
        self._nav.setIconSize(QSize(18, 18))
        self._nav.setMinimumWidth(NAV_COLLAPSED_WIDTH)
        self._nav.setMaximumWidth(NAV_EXPANDED_WIDTH)
        self._nav.resize(NAV_EXPANDED_WIDTH, self._nav.height())
        self._nav.setSpacing(2)
        self._nav.setFocusPolicy(Qt.NoFocus)
        self._nav.setItemDelegate(_SidebarItemDelegate(self._nav))

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

        # 侧边栏 + 主内容区：用 QHBoxLayout，nav 宽度由动画控制，
        # stack 自动占据剩余空间。nav 收起后的重排在 _on_sidebar_anim_finished 中触发。
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
            item.setData(Qt.UserRole, title)
            item.setToolTip(title)
            item.setSizeHint(QSize(NAV_EXPANDED_WIDTH - 16, 54))
            if icon:
                item.setIcon(icon)
            self._nav.addItem(item)
            self._stack.addWidget(widget)
            self._page_keys.append(key)
            self._page_titles.append(title)
            self._pages.append(widget)

        self._sync_nav_items_for_sidebar_state()
        self._apply_default_page()

    def _toggle_sidebar(self) -> None:
        self._nav_expanded = not self._nav_expanded
        target = NAV_EXPANDED_WIDTH if self._nav_expanded else NAV_COLLAPSED_WIDTH
        self._sync_nav_items_for_sidebar_state()

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

        # 关键修复：动画结束后触发当前页面重排，让其内的表格
        # 按 nav 收起后释放的宽度重新计算几何，避免横向溢出/滚动条残留。
        self._anim2.finished.connect(self._on_sidebar_anim_finished)

        # 更新按钮箭头
        self._toggle_btn.setText("☰" if self._nav_expanded else "≫")

    def _sync_nav_items_for_sidebar_state(self) -> None:
        self._nav.setProperty("collapsed", not self._nav_expanded)
        self._nav.style().unpolish(self._nav)
        self._nav.style().polish(self._nav)
        width = NAV_EXPANDED_WIDTH - 16 if self._nav_expanded else NAV_COLLAPSED_WIDTH - 16
        for i in range(self._nav.count()):
            item = self._nav.item(i)
            title = self._page_titles[i] if i < len(self._page_titles) else item.data(Qt.UserRole) or ""
            item.setText(title if self._nav_expanded else "")
            item.setToolTip(str(title))
            item.setSizeHint(QSize(width, 54))
        self._nav.viewport().update()

    def _on_sidebar_anim_finished(self) -> None:
        """侧边栏收起/展开动画结束后，递归重排所有内部组件几何。

        仅调用 updateGeometry + layout.activate 对嵌套的 QSplitter/QScrollArea 无效，
        需递归遍历子 widget，强制 QSplitter 重算尺寸、QScrollArea 更新视口、
        QAbstractScrollArea 刷新几何，避免「侧边栏收起后内容区仍可横向滚动」的系统性 bug。
        """
        current = self._stack.currentWidget()
        if current is not None:
            current.updateGeometry()
            if current.layout() is not None:
                current.layout().activate()
            # 递归强制内部 QSplitter 和 QScrollArea 重排
            self._recursive_relayout(current)

    @staticmethod
    def _recursive_relayout(widget: QWidget) -> None:
        """递归遍历子组件树，强制 QSplitter 重算尺寸、QScrollArea 刷新视口。"""
        from PySide6.QtWidgets import QAbstractScrollArea, QSplitter
        widget.updateGeometry()
        for child in widget.findChildren(QWidget):
            if isinstance(child, QSplitter):
                # QSplitter 需要逐个刷新子 widget 尺寸来消除横向溢出
                sizes = child.sizes()
                if sizes:
                    child.setSizes(sizes)
                child.updateGeometry()
            elif isinstance(child, QAbstractScrollArea):
                child.updateGeometry()
                child.viewport().updateGeometry()

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
        if app is None:
            return
        for window in app.topLevelWidgets():
            for widget in [window, *window.findChildren(QWidget)]:
                refresh_theme = getattr(widget, "refresh_theme", None)
                if callable(refresh_theme):
                    refresh_theme()

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
        self._avatar_btn = QPushButton(user.username[:1].upper())
        self._avatar_btn.setObjectName("userAvatarButton")
        self._avatar_btn.setCursor(Qt.PointingHandCursor)
        self._avatar_btn.setToolTip(f"{user.username} · 点击查看菜单")
        self._avatar_btn.setFixedSize(38, 38)
        self._avatar_btn.setStyleSheet(f"""
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
        layout.addWidget(self._avatar_btn)

        # 下拉菜单
        menu = QMenu(self._avatar_btn)
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
            "user": "学生",
        }.get(user.role.value, user.role.value)
        menu.setTitle(f"{user.username}  ·  {role_text}")

        # 设置...
        settings_action = QAction("设置...", menu)
        settings_action.triggered.connect(lambda: self._open_settings(QApplication.instance()))
        menu.addAction(settings_action)

        # 账号设置（头像、通知偏好）
        account_action = QAction("账号设置", menu)
        account_action.triggered.connect(self._open_account_settings)
        menu.addAction(account_action)

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
        about_action.triggered.connect(self._show_about)
        menu.addAction(about_action)

        # 登出
        menu.addSeparator()
        logout_action = QAction("登出", menu)
        logout_action.triggered.connect(self.close)
        menu.addAction(logout_action)

        self._avatar_btn.setMenu(menu)
        # QPushButton.setMenu 已内置「点击即弹出菜单」行为，
        # 无需 setPopupMode（该方法属 QToolButton，对 QPushButton 调用会抛 AttributeError）

        bar.setLayout(layout)
        return bar

    def set_user_context(self, user: User, user_repo: UserRepository) -> None:
        """注入用户上下文，启用顶栏头像与账号设置入口。

        由于 __init__ 仅接收 user_label: str，无法直接获取 User/UserRepository，
        由 admin_window/client_window 在构造后调用此方法注入上下文，
        避免修改 __init__ 签名破坏调用方。
        """
        self._user = user
        self._user_repo = user_repo
        self._refresh_topbar_avatar()

    def _refresh_topbar_avatar(self) -> None:
        """根据当前用户上下文刷新顶栏头像显示。"""
        if not self._user or not self._user_repo:
            return
        initial = self._user.username[:1].upper() if self._user.username else "?"
        self._avatar_btn.setText(initial)

    def _open_account_settings(self) -> None:
        """打开账号设置对话框。"""
        if not self._user or not self._user_repo:
            return
        from app.ui.account_settings import AccountSettingsDialog
        dialog = AccountSettingsDialog(self._user, self._user_repo, self)
        dialog.exec()
        # 对话框关闭后刷新顶栏头像（用户可能上传了新头像或修改了偏好）
        self._refresh_topbar_avatar()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于 Campus Scheduler",
            "Campus Scheduler — 校园先到先得报名与智能排班系统\n\nDeveloped by GoF\n\n© 2026",
        )
