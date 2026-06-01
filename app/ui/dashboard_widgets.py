from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.domain.models import User
from app.infrastructure.repositories import (
    ActivityRepository,
    RegistrationRepository,
    ScheduleRepository,
    TimeSlotRepository,
)
from app.ui.style import get_palette


class DashboardPanel(QWidget):
    def __init__(
        self,
        user: User,
        activity_repo: ActivityRepository,
        slot_repo: TimeSlotRepository,
        reg_repo: RegistrationRepository,
        schedule_repo: ScheduleRepository,
    ) -> None:
        super().__init__()
        self._user = user
        self._activity_repo = activity_repo
        self._slot_repo = slot_repo
        self._reg_repo = reg_repo
        self._schedule_repo = schedule_repo

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        # 标题
        header = QLabel("概览")
        header.setObjectName("pageTitle")
        layout.addWidget(header)

        desc = QLabel("关键指标与最新动态")
        desc.setObjectName("pageSubtitle")
        layout.addWidget(desc)

        layout.addSpacing(8)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(16)
        layout.addLayout(self._grid)
        layout.addStretch(1)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        for i in reversed(range(self._grid.count())):
            item = self._grid.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

        icons = ["📋", "⏰", "📝", "📊"]
        if self._user.role.value in {"super_admin", "organizer"}:
            cards = [
                ("活动总数", self._activity_repo.count_all()),
                ("时段总数", self._slot_repo.count_all()),
                ("报名总数", self._reg_repo.count_all()),
                ("排班结果", self._schedule_repo.count_all()),
            ]
        else:
            cards = [
                ("可报名活动", self._activity_repo.count_all()),
                ("我的报名", self._reg_repo.count_by_user(self._user.id)),
                ("我的排班", self._schedule_repo.count_by_user(self._user.id)),
                ("已发布时段", self._slot_repo.count_all()),
            ]

        for index, (label, value) in enumerate(cards):
            icon = icons[index % len(icons)]
            card = _StatCard(icon, label, value)
            row, col = divmod(index, 2)
            self._grid.addWidget(card, row, col)


class _StatCard(QFrame):
    """Claude 风格统计卡片 — 带图标和大数字。"""

    def __init__(self, icon: str, label: str, value: int) -> None:
        super().__init__()
        self.setObjectName("statCard")
        self.setFixedHeight(120)

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)

        # 图标 + 标签
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 18px; background: transparent;")
        name_label = QLabel(label)
        name_label.setObjectName("statLabel")
        top_row.addWidget(icon_label)
        top_row.addWidget(name_label)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        # 大数字
        value_label = QLabel(str(value))
        value_label.setObjectName("statValue")
        layout.addWidget(value_label)

        layout.addStretch(1)
        self.setLayout(layout)
