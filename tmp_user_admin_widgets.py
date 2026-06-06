from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from app.application.user_service import UserService
from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import Role, User, UserStatus
from app.infrastructure.repositories import (
    RegistrationRepository,
    ScheduleRepository,
    UserRepository,
)
from app.ui.style import get_palette
from app.ui.ui_utils import configure_table, format_datetime, make_page_header, set_banner, set_table_empty


# 鈹€鈹€鈹€ 杈呭姪鍑芥暟锛氬垱寤哄甫棰滆壊鐨勮鑹?鐘舵€佽〃鏍奸」 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def _make_role_item(role_value: str) -> QTableWidgetItem:
    """鍒涘缓瑙掕壊寰界珷琛ㄦ牸椤癸紝浣跨敤璋冭壊鏉跨潃鑹层€?""
    p = get_palette()
    role_map = {
        Role.SUPER_ADMIN.value: ("瓒呯骇绠＄悊鍛?, p.accent, p.accent_soft),
        Role.ORGANIZER.value: ("缁勭粐鑰?, p.warning_fg, p.warning_bg),
        Role.USER.value: ("鏅€氱敤鎴?, p.text_secondary, p.bg_sidebar),
    }
    text, fg, bg = role_map.get(role_value, (role_value, p.text_secondary, p.bg_sidebar))
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignCenter)
    item.setForeground(QBrush(QColor(fg)))
    item.setBackground(QBrush(QColor(bg)))
    return item


def _make_user_status_item(status_value: str) -> QTableWidgetItem:
    """鍒涘缓鐢ㄦ埛鐘舵€佸窘绔犺〃鏍奸」锛屼娇鐢ㄨ皟鑹叉澘鐫€鑹层€?""
    p = get_palette()
    status_map = {
        UserStatus.APPROVED.value: ("宸查€氳繃", p.success_fg, p.success_bg),
        UserStatus.PENDING_REVIEW.value: ("寰呭鎵?, p.accent, p.accent_soft),
        UserStatus.REJECTED.value: ("宸叉嫆缁?, p.error_fg, p.error_bg),
    }
    text, fg, bg = status_map.get(status_value, (status_value, p.text_secondary, p.bg_sidebar))
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignCenter)
    item.setForeground(QBrush(QColor(fg)))
    item.setBackground(QBrush(QColor(bg)))
    return item


# 鈹€鈹€鈹€ 缁熻鍗＄墖 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class _StatCard(QFrame):
    def __init__(self, label: str, value: int, accent_color: str) -> None:
        super().__init__()
        self.setObjectName("statCard")
        self.setFixedHeight(100)

        p = get_palette()
        self.setStyleSheet(f"""
            QFrame#statCard {{
                background: {p.bg_card};
                border: 1px solid {p.border_light};
                border-left: 4px solid {accent_color};
                border-radius: 16px;
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        name_label = QLabel(label)
        name_label.setObjectName("statLabel")
        layout.addWidget(name_label)

        value_label = QLabel(str(value))
        value_label.setObjectName("statValue")
        layout.addWidget(value_label)

        layout.addStretch(1)
        self.setLayout(layout)


# 鈹€鈹€鈹€ 鐢ㄦ埛绠＄悊闈㈡澘 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class UserAdminPanel(QWidget):
    def __init__(self, user_service: UserService, user_repo: UserRepository, current_user: User) -> None:
        super().__init__()
        self._user_service = user_service
        self._user_repo = user_repo
        self._current_user = current_user
        self._reg_repo = RegistrationRepository()
        self._schedule_repo = ScheduleRepository()

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["ID", "鐢ㄦ埛鍚?, "瑙掕壊", "鐘舵€?, "鍒涘缓鏃堕棿"])
        configure_table(self._table)

        self._init_create_form()
        self._init_pending_section()

        # 鈹€鈹€ 缁熻鍗＄墖鍖哄煙 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        self._stats_grid = QGridLayout()
        self._stats_grid.setSpacing(12)
        self._stats_grid.setContentsMargins(0, 0, 0, 0)

        # 鈹€鈹€ 鐢ㄦ埛鍒楄〃 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        list_group = QGroupBox("鐢ㄦ埛鍒楄〃")
        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(12, 12, 12, 12)
        list_layout.addWidget(self._table)

        # 鍒犻櫎鎸夐挳
        delete_btn_layout = QHBoxLayout()
        delete_btn_layout.addStretch(1)
        self._delete_btn = QPushButton("鍒犻櫎閫変腑鐢ㄦ埛")
        self._delete_btn.setObjectName("dangerButton")
        self._delete_btn.clicked.connect(self._delete_user)
        delete_btn_layout.addWidget(self._delete_btn)
        list_layout.addLayout(delete_btn_layout)

        list_group.setLayout(list_layout)

        header = make_page_header("鐢ㄦ埛绠＄悊", "鍒涘缓璐﹀彿骞舵煡鐪嬬敤鎴峰垪琛?)

        # 宸︿晶锛氬垱寤虹敤鎴?+ 寰呭鎵?        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        left_layout.addWidget(self._create_group)
        if self._current_user.role != Role.USER:
            left_layout.addWidget(self._pending_group)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(16)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        left_widget.setFixedWidth(320)
        body_layout.addWidget(left_widget)
        body_layout.addWidget(list_group, 2)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addLayout(self._stats_grid)
        layout.addLayout(body_layout)
        self.setLayout(layout)

        self.refresh()

    # 鈹€鈹€ 鍒涘缓鐢ㄦ埛琛ㄥ崟 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _init_create_form(self) -> None:
        self._username = QLineEdit()
        self._username.setPlaceholderText("鐢ㄦ埛鍚?)
        self._password = QLineEdit()
        self._password.setPlaceholderText("鍒濆瀵嗙爜")
        self._password.setEchoMode(QLineEdit.Password)
        self._role = QComboBox()

        # 鏍规嵁瑙掕壊鏄剧ず鍙€夎鑹?        if self._current_user.role == Role.SUPER_ADMIN:
            self._role.addItem("瓒呯骇绠＄悊鍛?, Role.SUPER_ADMIN)
            self._role.addItem("缁勭粐鑰?, Role.ORGANIZER)
            self._role.addItem("鏅€氱敤鎴?, Role.USER)
        elif self._current_user.role == Role.ORGANIZER:
            self._role.addItem("鏅€氱敤鎴?, Role.USER)
            self._role.setCurrentIndex(0)
            self._role.setEnabled(False)  # 缁勭粐鑰呭彧鑳藉垱寤烘櫘閫氱敤鎴凤紝鍥哄畾閫夐」

        self._message = QLabel("")
        set_banner(self._message, "info", "")

        create_btn = QPushButton("鍒涘缓鐢ㄦ埛")
        create_btn.setObjectName("primaryButton")
        create_btn.clicked.connect(self._create_user)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow("鐢ㄦ埛鍚?, self._username)
        form.addRow("瀵嗙爜", self._password)
        form.addRow("瑙掕壊", self._role)
        form.addRow(create_btn)
        form.addRow(self._message)

        self._create_group = QGroupBox("鍒涘缓鐢ㄦ埛")
        self._create_group.setLayout(form)

        # 鏅€氱敤鎴蜂笉鑳藉垱寤虹敤鎴?        if self._current_user.role == Role.USER:
            self._create_group.setEnabled(False)
            set_banner(self._message, "info", "鏅€氱敤鎴锋棤鏉冨垱寤虹敤鎴?)

    # 鈹€鈹€ 寰呭鎵圭敤鎴峰尯鍩?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _init_pending_section(self) -> None:
        """鍒濆鍖栧緟瀹℃壒鐢ㄦ埛鍖哄煙"""
        self._pending_table = QTableWidget(0, 4)
        self._pending_table.setHorizontalHeaderLabels(["ID", "鐢ㄦ埛鍚?, "鐘舵€?, "鍒涘缓鏃堕棿"])
        configure_table(self._pending_table)
        self._pending_table.setMaximumHeight(200)

        btn_layout = QHBoxLayout()
        self._approve_btn = QPushButton("閫氳繃")
        self._approve_btn.setObjectName("primaryButton")
        self._approve_btn.clicked.connect(self._approve_user)
        self._reject_btn = QPushButton("鎷掔粷")
        self._reject_btn.setObjectName("dangerButton")
        self._reject_btn.clicked.connect(self._reject_user)
        btn_layout.addWidget(self._approve_btn)
        btn_layout.addWidget(self._reject_btn)

        self._pending_message = QLabel("")
        set_banner(self._pending_message, "info", "")

        pending_layout = QVBoxLayout()
        pending_layout.setContentsMargins(12, 12, 12, 12)
        pending_layout.addWidget(self._pending_table)
        pending_layout.addLayout(btn_layout)
        pending_layout.addWidget(self._pending_message)

        self._pending_group = QGroupBox("寰呭鎵圭敤鎴?)
        self._pending_group.setLayout(pending_layout)

    # 鈹€鈹€ 鍒锋柊缁熻鍗＄墖 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _refresh_stats(self, users: list[dict]) -> None:
        """鍒锋柊鐢ㄦ埛缁熻鍗＄墖銆?""
        p = get_palette()
        total = len(users)
        super_admin_count = sum(1 for u in users if u.get("role") == Role.SUPER_ADMIN.value)
        organizer_count = sum(1 for u in users if u.get("role") == Role.ORGANIZER.value)
        user_count = sum(1 for u in users if u.get("role") == Role.USER.value)

        # 娓呴櫎鏃у崱鐗?        while self._stats_grid.count():
            item = self._stats_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cards = [
            ("鐢ㄦ埛鎬绘暟", total, p.accent),
            ("瓒呯骇绠＄悊鍛?, super_admin_count, p.accent),
            ("缁勭粐鑰?, organizer_count, p.warning_fg),
            ("鏅€氱敤鎴?, user_count, p.text_secondary),
        ]
        for index, (label, value, color) in enumerate(cards):
            card = _StatCard(label, value, color)
            self._stats_grid.addWidget(card, 0, index)

    # 鈹€鈹€ 鍒锋柊寰呭鎵圭敤鎴峰垪琛?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _refresh_pending(self) -> None:
        """鍒锋柊寰呭鎵圭敤鎴峰垪琛?""
        if self._current_user.role == Role.USER:
            return
        try:
            pending_users = self._user_service.list_pending_users(self._current_user)
        except Exception:
            pending_users = []
        if not pending_users:
            set_table_empty(self._pending_table, 4, "鏆傛棤寰呭鎵圭敤鎴?)
            return
        self._pending_table.setRowCount(len(pending_users))
        for row_index, user in enumerate(pending_users):
            self._pending_table.setItem(row_index, 0, QTableWidgetItem(str(user.get("id", ""))))
            self._pending_table.setItem(row_index, 1, QTableWidgetItem(user.get("username", "")))
            # 鐘舵€佹寚绀哄櫒
            self._pending_table.setItem(row_index, 2, _make_user_status_item(user.get("status", UserStatus.PENDING_REVIEW.value)))
            self._pending_table.setItem(row_index, 3, QTableWidgetItem(format_datetime(user.get("created_at", ""))))
        self._pending_table.setColumnHidden(0, True)

    # 鈹€鈹€ 涓诲埛鏂?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def refresh(self) -> None:
        users = self._user_repo.list_all()

        # 鍒锋柊缁熻鍗＄墖
        self._refresh_stats(users)

        if not users:
            set_table_empty(self._table, 5, "鏆傛棤鐢ㄦ埛")
        else:
            self._table.setRowCount(len(users))
            for row_index, user in enumerate(users):
                self._table.setItem(row_index, 0, QTableWidgetItem(str(user.get("id", ""))))
                self._table.setItem(row_index, 1, QTableWidgetItem(user["username"]))
                # 瑙掕壊寰界珷
                self._table.setItem(row_index, 2, _make_role_item(user["role"]))
                # 鐘舵€佸窘绔?                self._table.setItem(row_index, 3, _make_user_status_item(user.get("status", UserStatus.APPROVED.value)))
                self._table.setItem(row_index, 4, QTableWidgetItem(format_datetime(user["created_at"])))
            self._table.setColumnHidden(0, True)
        self._refresh_pending()

    # 鈹€鈹€ 鍒涘缓鐢ㄦ埛 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _create_user(self) -> None:
        if self._current_user.role == Role.USER:
            set_banner(self._message, "error", "鏅€氱敤鎴锋棤鏉冨垱寤虹敤鎴?)
            return
        try:
            set_banner(self._message, "info", "")
            user = self._user_service.register(
                current_user=self._current_user,
                username=self._username.text().strip(),
                password=self._password.text(),
                role=Role(self._role.currentData()),
            )
            set_banner(self._message, "success", f"宸插垱寤虹敤鎴凤細{user.username}")
            self.refresh()
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._message, "error", str(exc))

    # 鈹€鈹€ 瀹℃壒鐢ㄦ埛 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _approve_user(self) -> None:
        selected_rows = self._pending_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "鎻愮ず", "璇峰厛閫夋嫨瑕佸鎵圭殑鐢ㄦ埛")
            return
        row = selected_rows[0].row()
        user_id_item = self._pending_table.item(row, 0)
        username_item = self._pending_table.item(row, 1)
        if not user_id_item:
            return
        user_id = user_id_item.text()
        username = username_item.text() if username_item else ""
        try:
            self._user_service.approve_user(self._current_user, user_id)
            set_banner(self._pending_message, "success", f"宸查€氳繃鐢ㄦ埛锛歿username}")
            self.refresh()
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._pending_message, "error", str(exc))

    def _reject_user(self) -> None:
        selected_rows = self._pending_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "鎻愮ず", "璇峰厛閫夋嫨瑕佹嫆缁濈殑鐢ㄦ埛")
            return
        row = selected_rows[0].row()
        user_id_item = self._pending_table.item(row, 0)
        username_item = self._pending_table.item(row, 1)
        if not user_id_item:
            return
        user_id = user_id_item.text()
        username = username_item.text() if username_item else ""
        try:
            self._user_service.reject_user(self._current_user, user_id)
            set_banner(self._pending_message, "success", f"宸叉嫆缁濈敤鎴凤細{username}")
            self.refresh()
        except (PermissionDenied, ValidationError) as exc:
            set_banner(self._pending_message, "error", str(exc))

    # 鈹€鈹€ 鍒犻櫎鐢ㄦ埛锛堝惈璇︾粏淇℃伅纭锛?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _delete_user(self) -> None:
        if self._current_user.role != Role.SUPER_ADMIN:
            set_banner(self._message, "error", "鏃犳潈闄愬垹闄ょ敤鎴?)
            return

        # 鑾峰彇褰撳墠閫変腑鐨勮
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "鎻愮ず", "璇峰厛閫夋嫨瑕佸垹闄ょ殑鐢ㄦ埛")
            return

        row = selected_rows[0].row()
        user_id_item = self._table.item(row, 0)
        username_item = self._table.item(row, 1)
        if not user_id_item or not username_item:
            QMessageBox.warning(self, "鎻愮ず", "鏁版嵁寮傚父")
            return

        user_id = user_id_item.text()
        username = username_item.text()

        # 鏌ヨ鍏宠仈鏁版嵁
        reg_count = self._reg_repo.count_by_user(user_id)
        schedule_count = self._schedule_repo.count_by_user(user_id)

        # 鏋勫缓璇︾粏纭淇℃伅
        detail_lines = [f"纭畾瑕佸垹闄ょ敤鎴枫€寋username}銆嶅悧锛?]
        if reg_count > 0 or schedule_count > 0:
            detail_lines.append("")
            detail_lines.append("璇ョ敤鎴峰瓨鍦ㄤ互涓嬪叧鑱旀暟鎹細")
            if reg_count > 0:
                detail_lines.append(f"  路 鎶ュ悕璁板綍锛歿reg_count} 鏉?)
            if schedule_count > 0:
                detail_lines.append(f"  路 鎺掔彮缁撴灉锛歿schedule_count} 鏉?)
            detail_lines.append("")
            detail_lines.append("鍒犻櫎鍚庡叧鑱旀暟鎹皢涓€骞舵竻闄わ紝涓旀棤娉曟仮澶嶃€?)
        else:
            detail_lines.append("鍒犻櫎鍚庢棤娉曟仮澶嶃€?)

        reply = QMessageBox.question(
            self,
            "纭鍒犻櫎",
            "\n".join(detail_lines),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                self._user_service.delete_user(current_user=self._current_user, user_id=user_id)
                set_banner(self._message, "success", f"宸插垹闄ょ敤鎴凤細{username}")
                self.refresh()
            except (PermissionDenied, ValidationError) as exc:
                set_banner(self._message, "error", str(exc))
