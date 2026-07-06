from __future__ import annotations

import threading

import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.infrastructure.api_client import is_loopback_api_url
from app.infrastructure.notifications import get_smtp_config, send_email, set_smtp_config
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
    FORM_LAYOUT_FLAT,
    FORM_LAYOUT_GUIDED,
    THEME_DARK,
    THEME_LIGHT,
    apply_app_style,
    get_default_page,
    get_density,
    get_form_layout_mode,
    get_palette,
    get_theme,
    set_default_page,
    set_density,
    set_form_layout_mode,
    set_theme,
)
from app.ui.ui_utils import StyledComboBox


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

        self._theme = StyledComboBox()
        self._theme.addItem("浅色", THEME_LIGHT)
        self._theme.addItem("深色", THEME_DARK)
        self._theme.setCurrentIndex(0 if get_theme() == THEME_LIGHT else 1)

        self._density = StyledComboBox()
        self._density.addItem("舒适", DENSITY_COMFORTABLE)
        self._density.addItem("紧凑", DENSITY_COMPACT)
        self._density.setCurrentIndex(0 if get_density() == DENSITY_COMFORTABLE else 1)

        self._default_page = StyledComboBox()
        for key, title in pages:
            self._default_page.addItem(title, key)
        default_key = get_default_page()
        if default_key:
            index = self._default_page.findData(default_key)
            if index >= 0:
                self._default_page.setCurrentIndex(index)

        self._form_layout = StyledComboBox()
        self._form_layout.addItem("向导式（分步引导，推荐）", FORM_LAYOUT_GUIDED)
        self._form_layout.addItem("平铺式（极客高效，所有字段一览）", FORM_LAYOUT_FLAT)
        current_layout = get_form_layout_mode()
        idx = 0 if current_layout == FORM_LAYOUT_GUIDED else 1
        self._form_layout.setCurrentIndex(idx)

        appearance_form = QFormLayout()
        appearance_form.setHorizontalSpacing(16)
        appearance_form.setVerticalSpacing(10)
        appearance_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        appearance_form.addRow("主题", self._theme)
        appearance_form.addRow("密度", self._density)
        appearance_form.addRow("默认页面", self._default_page)
        appearance_form.addRow("创建活动布局", self._form_layout)

        # ── 数据设置 ──────────────────────────────────────────
        data_header = self._make_section_header("数据设置", p)

        self._data_mode = StyledComboBox()
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

        # ── 邮件设置 ──────────────────────────────────────────
        email_header = self._make_section_header("邮件提醒设置", p)

        smtp_cfg = get_smtp_config()
        self._email_host = QLineEdit()
        self._email_host.setPlaceholderText("例如：smtp.qq.com")
        self._email_host.setText(smtp_cfg.get("host", ""))

        self._email_port = QSpinBox()
        self._email_port.setRange(1, 65535)
        self._email_port.setValue(smtp_cfg.get("port", 587))

        self._email_username = QLineEdit()
        self._email_username.setPlaceholderText("例如：yourname@qq.com")
        self._email_username.setText(smtp_cfg.get("username", ""))

        self._email_password = QLineEdit()
        self._email_password.setPlaceholderText("SMTP 授权码（非邮箱密码）")
        self._email_password.setEchoMode(QLineEdit.Password)
        self._email_password.setText(smtp_cfg.get("password", ""))

        self._email_tls = QCheckBox("使用 TLS 加密")
        self._email_tls.setChecked(smtp_cfg.get("use_tls", True))

        self._email_test_btn = QPushButton("发送测试邮件")
        self._email_test_btn.setObjectName("secondaryButton")
        self._email_test_btn.setFixedWidth(120)
        self._email_test_btn.clicked.connect(self._test_email)

        email_form = QFormLayout()
        email_form.setHorizontalSpacing(16)
        email_form.setVerticalSpacing(10)
        email_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        email_form.addRow("SMTP 服务器", self._email_host)
        email_form.addRow("端口", self._email_port)
        email_form.addRow("邮箱账号", self._email_username)
        email_form.addRow("授权码", self._email_password)
        email_form.addRow("", self._email_tls)
        email_form.addRow("", self._email_test_btn)

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
        layout.addWidget(email_header)
        layout.addLayout(email_form)
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
                session = requests.Session()
                if is_loopback_api_url(url):
                    session.trust_env = False
                resp = session.get(f"{url.rstrip('/')}/health", timeout=5)
                ok = resp.status_code == 200
                if ok:
                    message = "连接成功"
                else:
                    message = f"服务端返回 {resp.status_code}"
            except requests.RequestException:
                message = "无法连接"
            # QSettings must be accessed from main thread; defer palette read to _update()

            def _update() -> None:
                p = get_palette()
                color = p.success_fg if ok else p.error_fg
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

    def _test_email(self) -> None:
        """发送测试邮件到配置的邮箱地址，验证 SMTP 配置是否有效。"""
        host = self._email_host.text().strip()
        port = self._email_port.value()
        username = self._email_username.text().strip()
        password = self._email_password.text()
        use_tls = self._email_tls.isChecked()

        if not host or not username or not password:
            self._email_test_btn.setText("请完善配置")
            self._email_test_btn.setStyleSheet("color: #c62828; font-weight: 600;")
            QTimer.singleShot(3000, self._reset_email_test_btn)
            return

        self._email_test_btn.setEnabled(False)
        self._email_test_btn.setText("发送中…")

        def _do_test() -> None:
            ok, msg = send_email(
                to=username,
                subject="[CampusArrangement] 邮件配置测试",
                body="✅ 如果您收到此邮件，说明 SMTP 配置正确。\n\n—— CampusArrangement 校园先到先得报名系统",
                host=host, port=port, username=username, password=password, use_tls=use_tls,
            )

            def _update() -> None:
                self._email_test_btn.setText(msg[:12])
                p = get_palette()
                color = p.success_fg if ok else p.error_fg
                self._email_test_btn.setStyleSheet(
                    f"color: {color}; font-weight: 600; border: 1px solid {color}; "
                    f"border-radius: 6px; padding: 5px 8px;"
                )
                QTimer.singleShot(4000, self._reset_email_test_btn)

            QTimer.singleShot(0, _update)

        threading.Thread(target=_do_test, daemon=True).start()

    def _reset_email_test_btn(self) -> None:
        self._email_test_btn.setText("发送测试邮件")
        self._email_test_btn.setStyleSheet("")
        self._email_test_btn.setEnabled(True)

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
        set_form_layout_mode(self._form_layout.currentData())
        set_data_mode(self._data_mode.currentData())
        set_api_base_url(self._base_url.text().strip() or get_api_base_url())
        # 保存邮件设置
        set_smtp_config(
            host=self._email_host.text().strip(),
            port=self._email_port.value(),
            username=self._email_username.text().strip(),
            password=self._email_password.text(),
            use_tls=self._email_tls.isChecked(),
        )
        apply_app_style(self._app, get_theme())
        self.accept()
