from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from app.domain.models import User
from app.infrastructure.repositories import ActivityRepository, RegistrationRepository, ScheduleRepository, TimeSlotRepository
from app.ui.ui_utils import make_page_header


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
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(make_page_header("概览", "关键指标与最新动态"))

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(12)
        layout.addLayout(self._grid)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        for i in reversed(range(self._grid.count())):
            item = self._grid.itemAt(i)
            if item and item.widget():
                item.widget().setParent(None)

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
            card = _StatCard(label, value)
            row, col = divmod(index, 2)
            self._grid.addWidget(card, row, col)


class _StatCard(QFrame):
    def __init__(self, label: str, value: int) -> None:
        super().__init__()
        self.setObjectName("statCard")
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        value_label = QLabel(str(value))
        value_label.setObjectName("statValue")
        label_label = QLabel(label)
        label_label.setObjectName("statLabel")
        layout.addWidget(value_label)
        layout.addWidget(label_label)
        self.setLayout(layout)
