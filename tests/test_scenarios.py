import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from app.application.activity_service import ActivityService
from app.application.checkin_service import CheckInService
from app.application.registration_service import RegistrationService
from app.application.scheduling_service import SchedulingService
from app.application.user_service import UserService
from app.domain.models import AllocationMode, CheckInStatus, Role, SignupMode, User
from app.infrastructure.db import init_db
from app.infrastructure.exporter import export_to_excel
from app.infrastructure.repositories import (
    ActivityRepository,
    CheckInRepository,
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
        self.checkin_repo = CheckInRepository()

        self.user_service = UserService(self.user_repo)
        self.activity_service = ActivityService(self.activity_repo, self.slot_repo)
        self.registration_service = RegistrationService(self.slot_repo, self.reg_repo, self.activity_repo)
        self.scheduling_service = SchedulingService(
            self.reg_repo,
            self.slot_repo,
            self.schedule_repo,
            self.activity_repo,
        )
        self.checkin_service = CheckInService(self.checkin_repo, self.schedule_repo)

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

        self.activity_service.publish_activity(admin, activity.id)

        self.registration_service.register(user_a.id, activity.id, slot1.id, priority=1)
        self.registration_service.register(user_b.id, activity.id, slot2.id, priority=1)

        self.activity_service.close_activity(admin, activity.id)
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

    def test_registration_cancel_and_checkin(self) -> None:
        admin = self.user_service.register("admin2", "pass", Role.SUPER_ADMIN)
        user_c = self.user_service.register("user_c", "pass", Role.USER)

        activity = self.activity_service.create_activity(
            user=admin,
            name="取消测试",
            signup_start=datetime.now(timezone.utc),
            signup_end=datetime.now(timezone.utc) + timedelta(days=1),
            details="测试取消",
            signup_mode=SignupMode.REALTIME,
            allocation_mode=AllocationMode.FIRST_COME,
        )
        slot = self.activity_service.add_slot(
            user=admin,
            activity_id=activity.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2),
            capacity=5,
        )
        self.activity_service.publish_activity(admin, activity.id)

        reg = self.registration_service.register(user_c.id, activity.id, slot.id, priority=1)
        self.assertEqual(reg.status.value, "pending")

        self.registration_service.cancel(user_c.id, reg.id)
        cancelled = self.reg_repo.get(reg.id)
        self.assertEqual(cancelled["status"], "cancelled")

        reg2 = self.registration_service.register(user_c.id, activity.id, slot.id, priority=1)
        self.activity_service.close_activity(admin, activity.id)
        self.scheduling_service.run(activity.id)

        checkin = self.checkin_service.check_in(
            user=admin,
            activity_id=activity.id,
            user_id=user_c.id,
            slot_id=slot.id,
        )
        self.assertEqual(checkin.status, CheckInStatus.CHECKED_IN)

        result = self.checkin_repo.get_by_user_slot(user_c.id, slot.id)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], CheckInStatus.CHECKED_IN.value)

    def test_registration_requires_open_activity(self) -> None:
        admin = self.user_service.register("admin3", "pass", Role.SUPER_ADMIN)
        user_d = self.user_service.register("user_d", "pass", Role.USER)

        activity = self.activity_service.create_activity(
            user=admin,
            name="状态测试",
            signup_start=datetime.now(timezone.utc),
            signup_end=datetime.now(timezone.utc) + timedelta(days=1),
            details="测试",
        )
        slot = self.activity_service.add_slot(
            user=admin,
            activity_id=activity.id,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2),
            capacity=5,
        )

        from app.domain.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.registration_service.register(user_d.id, activity.id, slot.id, priority=1)


if __name__ == "__main__":
    unittest.main()
