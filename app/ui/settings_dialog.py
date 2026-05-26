from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from app.infrastructure.runtime_config import (
    DATA_MODE_LOCAL,
    DATA_MODE_REMOTE,
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
    get_theme,
    set_default_page,
    set_density,
    set_theme,
)


class SettingsDialog(QDialog):
    def __init__(self, app, pages: list[tuple[str, str]]) -> None:
        super().__init__()
        self._app = app
        self.setWindowTitle("设置")
        self.setMinimumWidth(360)

        self._theme = QComboBox()
        self._theme.addItem("浅色", THEME_LIGHT)
        self._theme.addItem("深色", THEME_DARK)
        self._theme.setCurrentIndex(0 if get_theme() == THEME_LIGHT else 1)

        self._density = QComboBox()
        self._density.addItem("舒适", DENSITY_COMFORTABLE)
        self._density.addItem("紧凑", DENSITY_COMPACT)
        self._density.setCurrentIndex(0 if get_density() == DENSITY_COMFORTABLE else 1)

        self._data_mode = QComboBox()
        self._data_mode.addItem("本地模式（单机）", DATA_MODE_LOCAL)
        self._data_mode.addItem("服务端模式（多端协同）", DATA_MODE_REMOTE)
        self._data_mode.setCurrentIndex(0 if get_data_mode() == DATA_MODE_LOCAL else 1)
        self._data_mode.currentIndexChanged.connect(self._toggle_data_mode)

        self._base_url = QLineEdit()
        self._base_url.setPlaceholderText("http://127.0.0.1:8000")
        self._base_url.setText(get_api_base_url())
        self._base_url.setEnabled(get_data_mode() == DATA_MODE_REMOTE)

        self._default_page = QComboBox()
        for key, title in pages:
            self._default_page.addItem(title, key)
        default_key = get_default_page()
        if default_key:
            index = self._default_page.findData(default_key)
            if index >= 0:
                self._default_page.setCurrentIndex(index)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow("主题", self._theme)
        form.addRow("密度", self._density)
        form.addRow("数据源", self._data_mode)
        form.addRow("服务端地址", self._base_url)
        form.addRow("默认页面", self._default_page)

        info = QLabel("主题与密度会立即生效；数据源切换需重启应用")
        info.setObjectName("bannerInfo")

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("保存")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(info)
        layout.addLayout(buttons)
        self.setLayout(layout)

    def _save(self) -> None:
        set_theme(self._theme.currentData())
        set_density(self._density.currentData())
        set_default_page(self._default_page.currentData())
        set_data_mode(self._data_mode.currentData())
        set_api_base_url(self._base_url.text().strip() or get_api_base_url())
        apply_app_style(self._app, get_theme())
        self.accept()

    def _toggle_data_mode(self) -> None:
        self._base_url.setEnabled(self._data_mode.currentData() == DATA_MODE_REMOTE)
