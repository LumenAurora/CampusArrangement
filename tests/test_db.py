import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

os.environ["CAMPUS_DB_PATH"] = os.path.join(tempfile.gettempdir(), "campus_test.db")

from app.infrastructure.db import init_db
from app.infrastructure.repositories import ActivityRepository, CheckInRepository, RegistrationRepository, TimeSlotRepository, UserRepository
from app.domain.models import Activity, Role, TimeSlot, User


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        if os.path.exists(os.environ["CAMPUS_DB_PATH"]):
            os.remove(os.environ["CAMPUS_DB_PATH"])
        init_db()

    def test_slot_locking(self) -> None:
        user_repo = UserRepository()
        user = User.create("tester", Role.ORGANIZER)
        user_repo.create(user, "hashed")

        activity_repo = ActivityRepository()
        activity = Activity.create(
            name="测试活动",
            owner_id=user.id,
            signup_start=datetime.now(timezone.utc),
            signup_end=datetime.now(timezone.utc) + timedelta(days=1),
            details="detail",
        )
        activity_repo.create(activity)

        slot_repo = TimeSlotRepository()
        slot = TimeSlot.create(activity.id, datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(hours=1), capacity=1)
        slot_repo.create(slot)

        self.assertTrue(slot_repo.lock_slot(slot.id))
        self.assertFalse(slot_repo.lock_slot(slot.id))

    def test_checkin_create_and_query(self) -> None:
        user_repo = UserRepository()
        user = User.create("checkin_tester", Role.ORGANIZER)
        user_repo.create(user, "hashed")

        activity_repo = ActivityRepository()
        activity = Activity.create(
            name="签到测试活动",
            owner_id=user.id,
            signup_start=datetime.now(timezone.utc),
            signup_end=datetime.now(timezone.utc) + timedelta(days=1),
            details="detail",
        )
        activity_repo.create(activity)

        slot_repo = TimeSlotRepository()
        slot = TimeSlot.create(activity.id, datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(hours=1), capacity=10)
        slot_repo.create(slot)

        from app.domain.models import CheckIn, CheckInStatus
        checkin_repo = CheckInRepository()
        checkin = CheckIn.create(activity_id=activity.id, user_id=user.id, slot_id=slot.id)
        checkin_repo.create(checkin)

        result = checkin_repo.get_by_user_slot(user.id, slot.id)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], CheckInStatus.CHECKED_IN.value)

        activity_checkins = checkin_repo.list_by_activity(activity.id)
        self.assertEqual(len(activity_checkins), 1)

    def test_foreign_key_cascade(self) -> None:
        user_repo = UserRepository()
        user = User.create("cascade_tester", Role.SUPER_ADMIN)
        user_repo.create(user, "hashed")

        activity_repo = ActivityRepository()
        activity = Activity.create(
            name="级联测试活动",
            owner_id=user.id,
            signup_start=datetime.now(timezone.utc),
            signup_end=datetime.now(timezone.utc) + timedelta(days=1),
            details="detail",
        )
        activity_repo.create(activity)

        slot_repo = TimeSlotRepository()
        slot = TimeSlot.create(activity.id, datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(hours=1), capacity=10)
        slot_repo.create(slot)

        self.assertTrue(activity_repo.delete(activity.id))

        remaining_slots = slot_repo.list_by_activity(activity.id)
        self.assertEqual(len(remaining_slots), 0)


if __name__ == "__main__":
    unittest.main()
