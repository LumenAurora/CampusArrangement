import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from app.application.activity_service import ActivityService
from app.application.registration_service import RegistrationService
from app.application.scheduling_service import SchedulingService
from app.application.user_service import UserService
from app.domain.models import AllocationMode, Role, SignupMode, User
from app.infrastructure.db import init_db
from app.infrastructure.exporter import export_to_excel
from app.infrastructure.repositories import (
    ActivityRepository,
    RegistrationRepository,
    ScheduleRepository,
    TimeSlotRepository,
    UserRepository,
)


class ScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self._db_path = os.path.join(tempfile.gettempdir(), "campus_scenario.db")
        os.environ["CAMPUS_DB_PATH"] = self._db_path
        if os.path.exists(self._db_path):
            os.remove(self._db_path)
        init_db()

        self.user_repo = UserRepository()
        self.activity_repo = ActivityRepository()
        self.slot_repo = TimeSlotRepository()
        self.reg_repo = RegistrationRepository()
        self.schedule_repo = ScheduleRepository()

        self.user_service = UserService(self.user_repo)
        self.activity_service = ActivityService(self.activity_repo, self.slot_repo)
        self.registration_service = RegistrationService(self.slot_repo, self.reg_repo, self.activity_repo)
        self.scheduling_service = SchedulingService(
            self.reg_repo,
            self.slot_repo,
            self.schedule_repo,
            self.activity_repo,
        )

    def test_full_flow_blind_lottery(self) -> None:
        admin = self.user_service.register("admin1", "pass", Role.SUPER_ADMIN)
        user_a = self.user_service.register("user_a", "pass", Role.USER)
        user_b = self.user_service.register("user_b", "pass", Role.USER)

        activity = self.activity_service.create_activity(
            user=admin,
            name="志愿服务",
            signup_start=datetime.now(timezone.utc),
            signup_end=datetime.now(timezone.utc) + timedelta(days=1),
            details="测试",
            signup_mode=SignupMode.BLIND,
            allocation_mode=AllocationMode.LOTTERY,
        )
        slot1 = self.activity_service.add_slot(
            user=admin,
            activity_id=activity.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2),
            capacity=1,
        )
        slot2 = self.activity_service.add_slot(
            user=admin,
            activity_id=activity.id,
            start_time=datetime.now(timezone.utc) + timedelta(hours=3),
            end_time=datetime.now(timezone.utc) + timedelta(hours=5),
            capacity=1,
        )

        self.registration_service.register(user_a.id, activity.id, slot1.id, priority=1)
        self.registration_service.register(user_b.id, activity.id, slot2.id, priority=1)

        assigned = self.scheduling_service.run(activity.id)
        self.assertEqual(assigned, 2)
        rows = self.schedule_repo.list_by_activity(activity.id)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["user_id"] for row in rows}, {user_a.id, user_b.id})

        output_path = os.path.join(tempfile.gettempdir(), "schedule_export.xlsx")
        if os.path.exists(output_path):
            os.remove(output_path)
        export_to_excel(rows, output_path)
        self.assertTrue(os.path.exists(output_path))


if __name__ == "__main__":
    unittest.main()
