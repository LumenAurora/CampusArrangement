from __future__ import annotations

from PySide6.QtWidgets import QApplication

from app.application.activity_service import ActivityService
from app.application.registration_service import RegistrationService
from app.domain.models import User
from app.infrastructure.repositories import ScheduleRepository
from app.ui.dashboard_widgets import DashboardPanel
from app.ui.icon_loader import load_icon
from app.ui.my_results_widgets import MyResultsPanel
from app.ui.registration_widgets import RegistrationPanel
from app.ui.shell import NavigationWindow


class ClientWindow(NavigationWindow):
    def __init__(
        self,
        user: User,
        activity_service: ActivityService,
        registration_service: RegistrationService,
        schedule_repo: ScheduleRepository,
        activity_repo,
        slot_repo,
        reg_repo,
    ) -> None:
        super().__init__("校园报名与排班系统 - 客户端", f"{user.username}")

        pages = [
            ("dashboard", "概览", DashboardPanel(user, activity_repo, slot_repo, reg_repo, schedule_repo), load_icon("dashboard")),
            ("signup", "报名", RegistrationPanel(activity_service, registration_service, user), load_icon("signup")),
            ("results", "我的结果", MyResultsPanel(schedule_repo, activity_service, user), load_icon("results")),
        ]
        self.set_pages(pages)
        self.attach_menus(QApplication.instance())
