from __future__ import annotations

from PySide6.QtWidgets import QApplication, QStyle

from app.application.activity_service import ActivityService
from app.application.registration_service import RegistrationService
from app.application.scheduling_service import SchedulingService
from app.domain.models import User
from app.infrastructure.repositories import ScheduleRepository
from app.ui.activity_widgets import ActivityPanel
from app.ui.registration_widgets import RegistrationPanel
from app.ui.scheduling_widgets import SchedulingPanel
from app.ui.shell import NavigationWindow


class MainWindow(NavigationWindow):
    def __init__(
        self,
        user: User,
        activity_service: ActivityService,
        registration_service: RegistrationService,
        scheduling_service: SchedulingService,
        schedule_repo: ScheduleRepository,
    ) -> None:
        super().__init__("校园报名与排班系统", f"{user.username}")

        style = QApplication.instance().style()
        pages = [
            ("activities", "活动管理", ActivityPanel(activity_service, user), style.standardIcon(QStyle.SP_FileDialogNewFolder)),
            ("signup", "报名", RegistrationPanel(activity_service, registration_service, user), style.standardIcon(QStyle.SP_DialogYesButton)),
            ("scheduling", "排班", SchedulingPanel(activity_service, scheduling_service, schedule_repo), style.standardIcon(QStyle.SP_FileDialogContentsView)),
        ]
        self.set_pages(pages)
        self.attach_menus(QApplication.instance())
