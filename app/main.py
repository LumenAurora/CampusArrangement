from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.application.activity_service import ActivityService
from app.application.checkin_service import CheckInService
from app.application.group_service import GroupService
from app.application.registration_service import RegistrationService
from app.application.scheduling_service import SchedulingService
from app.application.user_service import UserService
from app.application.remote_services import (
    RemoteActivityService,
    RemoteCheckInService,
    RemoteRegistrationService,
    RemoteSchedulingService,
    RemoteUserService,
)
from app.domain.models import Role
from app.infrastructure.api_client import ApiClient
from app.infrastructure.db import init_db
from app.infrastructure.repositories import (
    ActivityRepository,
    CheckInRepository,
    GroupRepository,
    RegistrationRepository,
    ScheduleRepository,
    TimeSlotRepository,
    UserRepository,
)
from app.infrastructure.remote_repositories import (
    MetricsCache,
    RemoteActivityRepository,
    RemoteCheckInRepository,
    RemoteRegistrationRepository,
    RemoteScheduleRepository,
    RemoteTimeSlotRepository,
    RemoteUserRepository,
)
from app.infrastructure.runtime_config import DATA_MODE_REMOTE, get_api_base_url, get_data_mode
from app.ui.login_dialog import LoginDialog
from app.ui.style import apply_app_style, get_theme
from app.ui.admin_window import AdminWindow
from app.ui.client_window import ClientWindow


def ensure_admin(user_service: UserService, user_repo: UserRepository) -> None:
    if user_repo.get_by_username("admin"):
        return
    user_service.register(current_user=None, username="admin", password="admin", role=Role.SUPER_ADMIN)


def main() -> int:
    app = QApplication(sys.argv)
    apply_app_style(app, get_theme())
    data_mode = get_data_mode()
    api_client: ApiClient | None = None
    if data_mode == DATA_MODE_REMOTE:
        api_client = ApiClient(get_api_base_url())
        user_repo = RemoteUserRepository(api_client)
        user_service = RemoteUserService(api_client)
    else:
        init_db()
        user_repo = UserRepository()
        user_service = UserService(user_repo)
        ensure_admin(user_service, user_repo)
    login = LoginDialog(user_service)
    if login.exec() != LoginDialog.Accepted or not login.user:
        return 0
    if data_mode == DATA_MODE_REMOTE and api_client:
        metrics_cache = MetricsCache(api_client)
        activity_repo = RemoteActivityRepository(api_client, metrics_cache)
        slot_repo = RemoteTimeSlotRepository(api_client, metrics_cache)
        reg_repo = RemoteRegistrationRepository(api_client, metrics_cache)
        schedule_repo = RemoteScheduleRepository(api_client, metrics_cache)
        checkin_repo = RemoteCheckInRepository(api_client)
        activity_service = RemoteActivityService(api_client)
        registration_service = RemoteRegistrationService(api_client)
        scheduling_service = RemoteSchedulingService(api_client)
        checkin_service = RemoteCheckInService(api_client)
    else:
        activity_repo = ActivityRepository()
        slot_repo = TimeSlotRepository()
        reg_repo = RegistrationRepository()
        schedule_repo = ScheduleRepository()
        checkin_repo = CheckInRepository()
        group_repo = GroupRepository()

        activity_service = ActivityService(activity_repo, slot_repo)
        registration_service = RegistrationService(slot_repo, reg_repo, activity_repo, group_repo)
        scheduling_service = SchedulingService(reg_repo, slot_repo, schedule_repo, activity_repo)
        checkin_service = CheckInService(checkin_repo, schedule_repo, activity_repo)
        group_service = GroupService(group_repo, activity_repo)

    if login.user.role in {Role.SUPER_ADMIN, Role.ORGANIZER}:
        window = AdminWindow(
            user=login.user,
            activity_service=activity_service,
            scheduling_service=scheduling_service,
            schedule_repo=schedule_repo,
            activity_repo=activity_repo,
            slot_repo=slot_repo,
            reg_repo=reg_repo,
            user_service=user_service,
            user_repo=user_repo,
            checkin_service=checkin_service,
            checkin_repo=checkin_repo,
            group_service=group_service,
            group_repo=group_repo,
        )
    else:
        window = ClientWindow(
            user=login.user,
            activity_service=activity_service,
            registration_service=registration_service,
            schedule_repo=schedule_repo,
            activity_repo=activity_repo,
            slot_repo=slot_repo,
            reg_repo=reg_repo,
            checkin_service=checkin_service,
            group_service=group_service,
            group_repo=group_repo,
            checkin_repo=checkin_repo,
        )
    window.resize(1100, 700)
    window.setMinimumSize(960, 640)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
