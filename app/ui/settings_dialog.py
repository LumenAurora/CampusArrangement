from __future__ import annotations

import threading

import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.infrastructure.runtime_config import (
    DATA_MODE_LOCAL,
    DATA_MODE_REMOTE,
    DEFAULT_API_BASE_URL,
    get_api_base_url,
    get_data_mode,
    set_api_base_url,
    set_data_mode,
)
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
    set_default_page,
    set_density,
    set_theme,
)


class SettingsDialog(QDialog):
    def __init__(self, app, pages: list[tuple[str, str]]) -> None:
        super().__init__()
        self._app = app
        self._initial_data_mode = get_data_mode()
        self.setWindowTitle("设置")
        self.setMinimumWidth(420)

        p = get_palette()

        # ── 外观设置 ──────────────────────────────────────────
        appearance_header = self._make_section_header("外观设置", p)

        self._theme = QComboBox()
        self._theme.addItem("浅色", THEME_LIGHT)
        self._theme.addItem("深色", THEME_DARK)
        self._theme.setCurrentIndex(0 if get_theme() == THEME_LIGHT else 1)

        self._density = QComboBox()
        self._density.addItem("舒适", DENSITY_COMFORTABLE)
        self._density.addItem("紧凑", DENSITY_COMPACT)
        self._density.setCurrentIndex(0 if get_density() == DENSITY_COMFORTABLE else 1)

        self._default_page = QComboBox()
        for key, title in pages:
            self._default_page.addItem(title, key)
        default_key = get_default_page()
        if default_key:
            index = self._default_page.findData(default_key)
            if index >= 0:
                self._default_page.setCurrentIndex(index)

        appearance_form = QFormLayout()
        appearance_form.setHorizontalSpacing(16)
        appearance_form.setVerticalSpacing(10)
        appearance_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        appearance_form.addRow("主题", self._theme)
        appearance_form.addRow("密度", self._density)
        appearance_form.addRow("默认页面", self._default_page)

        # ── 数据设置 ──────────────────────────────────────────
        data_header = self._make_section_header("数据设置", p)

        self._data_mode = QComboBox()
        self._data_mode.addItem("本地模式（单机）", DATA_MODE_LOCAL)
        self._data_mode.addItem("服务端模式（多端协同）", DATA_MODE_REMOTE)
        self._data_mode.setCurrentIndex(0 if get_data_mode() == DATA_MODE_LOCAL else 1)
        self._data_mode.currentIndexChanged.connect(self._toggle_data_mode)

        self._base_url = QLineEdit()
        self._base_url.setPlaceholderText(DEFAULT_API_BASE_URL)
        self._base_url.setText(get_api_base_url())
        self._base_url.setEnabled(get_data_mode() == DATA_MODE_REMOTE)

        self._test_btn = QPushButton("连接测试")
        self._test_btn.setObjectName("secondaryButton")
        self._test_btn.setFixedWidth(80)
        self._test_btn.setEnabled(get_data_mode() == DATA_MODE_REMOTE)
        self._test_btn.clicked.connect(self._test_connection)

        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        url_row.addWidget(self._base_url, 1)
        url_row.addWidget(self._test_btn)

        data_form = QFormLayout()
        data_form.setHorizontalSpacing(16)
        data_form.setVerticalSpacing(10)
        data_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        data_form.addRow("数据源", self._data_mode)
        data_form.addRow("服务端地址", url_row)

        # ── 重启警告横幅 ──────────────────────────────────────
        self._restart_banner = QLabel("⚠ 数据源已更改，保存后需重启应用方可生效")
        self._restart_banner.setObjectName("restartBanner")
        self._restart_banner.setStyleSheet(
            f"background: {p.warning_bg}; color: {p.warning_fg}; "
            f"border-radius: 8px; padding: 10px 16px; font-weight: 600;"
        )
        self._restart_banner.setVisible(self._initial_data_mode != get_data_mode())

        # ── 底部按钮 ──────────────────────────────────────────
        buttons = QHBoxLayout()
        reset_btn = QPushButton("恢复默认")
        reset_btn.setObjectName("secondaryButton")
        reset_btn.clicked.connect(self._reset_defaults)
        buttons.addWidget(reset_btn)
        buttons.addStretch(1)
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("保存")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)

        # ── 主布局 ────────────────────────────────────────────
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)
        layout.addWidget(appearance_header)
        layout.addLayout(appearance_form)
        layout.addWidget(data_header)
        layout.addLayout(data_form)
        layout.addWidget(self._restart_banner)
        layout.addSpacing(4)
        layout.addLayout(buttons)
        self.setLayout(layout)

    @staticmethod
    def _make_section_header(text: str, p) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {p.accent}; font-weight: 700; font-size: 13px; "
            f"padding: 4px 0 0 0;"
        )
        return label

    def _toggle_data_mode(self) -> None:
        is_remote = self._data_mode.currentData() == DATA_MODE_REMOTE
        self._base_url.setEnabled(is_remote)
        self._test_btn.setEnabled(is_remote)
        self._restart_banner.setVisible(
            self._data_mode.currentData() != self._initial_data_mode
        )

    def _test_connection(self) -> None:
        url = self._base_url.text().strip() or DEFAULT_API_BASE_URL
        self._test_btn.setEnabled(False)
        self._test_btn.setText("测试中…")

        def _do_test() -> None:
            ok = False
            message = ""
            try:
                resp = requests.get(f"{url.rstrip('/')}/health", timeout=5)
                ok = resp.status_code == 200
                if ok:
                    message = "连接成功"
                else:
                    message = f"服务端返回 {resp.status_code}"
            except requests.RequestException:
                message = "无法连接"
            p = get_palette()
            color = p.success_fg if ok else p.error_fg
            # Update UI on main thread
            def _update() -> None:
                self._test_btn.setText(message)
                self._test_btn.setStyleSheet(
                    f"color: {color}; font-weight: 600; border: 1px solid {color}; "
                    f"border-radius: 6px; padding: 5px 8px;"
                )
                # Reset button after 3 seconds
                QTimer.singleShot(3000, self._reset_test_btn)

            QTimer.singleShot(0, _update)

        threading.Thread(target=_do_test, daemon=True).start()

    def _reset_test_btn(self) -> None:
        self._test_btn.setText("连接测试")
        self._test_btn.setStyleSheet("")
        self._test_btn.setEnabled(self._data_mode.currentData() == DATA_MODE_REMOTE)

    def _reset_defaults(self) -> None:
        self._theme.setCurrentIndex(0)
        self._density.setCurrentIndex(0)
        self._data_mode.setCurrentIndex(0)
        self._base_url.setText(DEFAULT_API_BASE_URL)
        if self._default_page.count() > 0:
            self._default_page.setCurrentIndex(0)

    def _save(self) -> None:
        set_theme(self._theme.currentData())
        set_density(self._density.currentData())
        set_default_page(self._default_page.currentData())
        set_data_mode(self._data_mode.currentData())
        set_api_base_url(self._base_url.text().strip() or get_api_base_url())
        apply_app_style(self._app, get_theme())
        self.accept()
