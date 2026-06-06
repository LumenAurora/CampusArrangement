from __future__ import annotations

from PySide6.QtWidgets import QApplication

from app.application.activity_service import ActivityService
from app.application.checkin_service import CheckInService
from app.application.scheduling_service import SchedulingService
from app.application.user_service import UserService
from app.domain.models import User
from app.infrastructure.repositories import ActivityRepository, CheckInRepository, ScheduleRepository, TimeSlotRepository, RegistrationRepository, UserRepository
from app.ui.activity_widgets import ActivityPanel
from app.ui.checkin_widgets import CheckInPanel
from app.ui.dashboard_widgets import DashboardPanel
from app.ui.icon_loader import load_icon
from app.ui.scheduling_widgets import SchedulingPanel
from app.ui.user_admin_widgets import UserAdminPanel
from app.ui.shell import NavigationWindow


class AdminWindow(NavigationWindow):
    def __init__(
        self,
        user: User,
        activity_service: ActivityService,
        scheduling_service: SchedulingService,
        schedule_repo: ScheduleRepository,
        activity_repo: ActivityRepository,
        slot_repo: TimeSlotRepository,
        reg_repo: RegistrationRepository,
        user_service: UserService,
        user_repo: UserRepository,
        checkin_service: CheckInService,
        checkin_repo: CheckInRepository,
    ) -> None:
        super().__init__("校园报名与排班系统 - 管理端", f"{user.username} · {user.role.value}")

        pages = [
            ("dashboard", "概览", DashboardPanel(user, activity_repo, slot_repo, reg_repo, schedule_repo), load_icon("dashboard")),
            ("activities", "活动管理", ActivityPanel(activity_service, user, scheduling_service, activity_repo), load_icon("activities")),
            ("scheduling", "排班管理", SchedulingPanel(activity_service, scheduling_service, schedule_repo, user_repo), load_icon("scheduling")),
            ("checkin", "签到管理", CheckInPanel(checkin_service, activity_service, schedule_repo, user_repo, user), load_icon("checkin")),
            ("users", "用户管理", UserAdminPanel(user_service, user_repo, user), load_icon("users")),
        ]
        self.set_pages(pages)
        self.attach_menus(QApplication.instance())
