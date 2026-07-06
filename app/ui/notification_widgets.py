"""学生端通知中心：查看所有收到的应用内通知，支持标记已读和清理。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.domain.models import User
from app.infrastructure.repositories import NotificationRepository
from app.ui.style import get_palette
from app.ui.ui_utils import configure_table, format_datetime, make_page_header


class NotificationCenterPanel(QWidget):
    """学生端通知中心：查看所有收到的应用内通知，支持标记已读和清理。"""

    PAGE_SIZE = 50

    def __init__(
        self,
        user: User,
        notification_repo: NotificationRepository,
    ) -> None:
        super().__init__()
        self._user = user
        self._repo = notification_repo
        self._all_notifications: list[dict] = []
        self._current_offset = 0
        self._has_more = True
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        p = get_palette()
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = make_page_header("通知中心", "查看系统通知与管理员消息")

        # Unread summary
        self._summary_label = QLabel()
        self._summary_label.setStyleSheet(
            f"color: {p.text_secondary}; font-size: 12px; padding: 4px 0;"
        )
        header.layout().addWidget(self._summary_label)
        layout.addWidget(header)

        # Action row
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self._mark_all_btn = QPushButton("全部标记已读")
        self._mark_all_btn.setObjectName("secondaryButton")
        self._mark_all_btn.clicked.connect(self._mark_all_read)

        self._delete_read_btn = QPushButton("删除已读")
        self._delete_read_btn.setObjectName("secondaryButton")
        self._delete_read_btn.clicked.connect(self._delete_read)

        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.setObjectName("secondaryButton")
        self._refresh_btn.clicked.connect(self.refresh)

        action_row.addWidget(self._mark_all_btn)
        action_row.addWidget(self._delete_read_btn)
        action_row.addStretch()
        action_row.addWidget(self._refresh_btn)
        layout.addLayout(action_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {p.border_light}; border: none;")
        layout.addWidget(sep)

        # Notifications table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["状态", "标题", "内容", "时间"])
        configure_table(self._table)
        self._table.setColumnWidth(0, 50)
        self._table.setColumnWidth(2, 240)
        self._table.setColumnWidth(3, 140)
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Fixed)
        h.setSectionResizeMode(3, QHeaderView.Fixed)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table, 1)

        # Load more
        self._load_more_btn = QPushButton("加载更多...")
        self._load_more_btn.setObjectName("secondaryButton")
        self._load_more_btn.clicked.connect(self._load_more)
        self._load_more_btn.setVisible(False)
        layout.addWidget(self._load_more_btn, alignment=Qt.AlignCenter)

        self.setLayout(layout)

    # ── Data ────────────────────────────────────────────────

    def refresh(self) -> None:
        """重新加载通知列表（从第一页开始）。"""
        self._current_offset = 0
        self._all_notifications = []
        self._has_more = True
        self._load_page()

    def _load_page(self) -> None:
        """加载一页通知并追加到本地缓存。"""
        batch = self._repo.list_by_user(
            self._user.id, limit=self.PAGE_SIZE, offset=self._current_offset
        )
        if batch:
            self._all_notifications.extend(batch)
            self._current_offset += len(batch)
            self._has_more = len(batch) >= self.PAGE_SIZE
        else:
            self._has_more = False
        self._render_table()
        self._update_summary()

    def _load_more(self) -> None:
        self._load_page()

    def _update_summary(self) -> None:
        unread = self._repo.count_unread(self._user.id)
        total = len(self._all_notifications)
        if unread > 0:
            self._summary_label.setText(f"你有 {unread} 条未读通知   |   共 {total} 条")
        else:
            self._summary_label.setText(f"全部已读   |   共 {total} 条")
        self._load_more_btn.setVisible(self._has_more)

    def _render_table(self) -> None:
        p = get_palette()
        self._table.setRowCount(len(self._all_notifications))
        for i, n in enumerate(self._all_notifications):
            is_read = bool(n.get("is_read", 0))
            # Status column: ● unread / ○ read
            status_text = "●" if not is_read else "○"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setFlags(Qt.ItemIsEnabled)
            if not is_read:
                status_item.setForeground(QBrush(QColor(p.accent)))
                font = QFont()
                font.setBold(True)
                status_item.setFont(font)
            else:
                status_item.setForeground(QBrush(QColor(p.text_tertiary)))
            status_item.setData(Qt.UserRole, n.get("id", ""))
            self._table.setItem(i, 0, status_item)

            # Subject
            subject = n.get("subject", "")
            subject_item = QTableWidgetItem(subject)
            subject_item.setFlags(Qt.ItemIsEnabled)
            if not is_read:
                font = QFont()
                font.setBold(True)
                subject_item.setFont(font)
            self._table.setItem(i, 1, subject_item)

            # Body preview (truncated)
            body = n.get("body", "")
            preview = body[:60] + "…" if len(body) > 60 else body
            body_item = QTableWidgetItem(preview)
            body_item.setFlags(Qt.ItemIsEnabled)
            self._table.setItem(i, 2, body_item)

            # Time
            created = n.get("created_at", "")
            time_text = format_datetime(created) if created else ""
            time_item = QTableWidgetItem(time_text)
            time_item.setFlags(Qt.ItemIsEnabled)
            time_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 3, time_item)

    # ── Actions ─────────────────────────────────────────────

    def _on_cell_clicked(self, row: int, _col: int) -> None:
        if row < 0 or row >= len(self._all_notifications):
            return
        notification = self._all_notifications[row]
        if notification.get("is_read"):
            return
        nid = notification.get("id", "")
        if nid:
            self._repo.mark_as_read(nid)
            self._all_notifications[row]["is_read"] = 1
            self._render_table()
            self._update_summary()

    def _mark_all_read(self) -> None:
        self._repo.mark_all_as_read(self._user.id)
        for n in self._all_notifications:
            n["is_read"] = 1
        self._render_table()
        self._update_summary()

    def _delete_read(self) -> None:
        count = self._repo.delete_read_by_user(self._user.id)
        if count > 0:
            self.refresh()
