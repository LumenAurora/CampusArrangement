import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

os.environ["CAMPUS_DB_PATH"] = os.path.join(tempfile.gettempdir(), "campus_test.db")

from app.infrastructure.db import init_db  # noqa: E402
from app.infrastructure.repositories import ActivityRepository, RegistrationRepository, TimeSlotRepository, UserRepository  # noqa: E402
from app.domain.models import Activity, Role, TimeSlot, User  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
