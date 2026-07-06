import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.infrastructure.db import init_db
from app.infrastructure.notifications import notify_by_preference, notify_user
from app.infrastructure.repositories import (
    ActivityRepository,
    CheckInRepository,
    NotificationRepository,
    RegistrationRepository,
    TimeSlotRepository,
    UserRepository,
)
from app.domain.models import Activity, NotificationMode, Role, TimeSlot, User


class DatabaseTests(unittest.TestCase):
    """数据库基础行为测试 — 每个测试使用独立 DB（通过 patch DB_PATH）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.mkdtemp(prefix="campus_db_test_")

    def setUp(self) -> None:
        db_path = os.path.join(self._tmpdir, f"{self._testMethodName}.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        # patch DB_PATH 避免模块导入时缓存导致的测试间 DB 共享
        self._db_patcher = patch("app.infrastructure.db.DB_PATH", Path(db_path))
        self._db_patcher.start()
        self.addCleanup(self._db_patcher.stop)
        os.environ.pop("CAMPUS_DB_PATH", None)
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

    def test_notification_center_repository_flow(self) -> None:
        user_repo = UserRepository()
        user = User.create("notice_tester", Role.USER)
        user_repo.create(user, "hashed")

        repo = NotificationRepository()
        created = notify_user(user.id, "报名成功", "你已成功报名活动")

        self.assertIsNotNone(created)
        self.assertEqual(repo.count_unread(user.id), 1)

        rows = repo.list_by_user(user.id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["subject"], "报名成功")
        self.assertEqual(rows[0]["body"], "你已成功报名活动")
        self.assertEqual(rows[0]["is_read"], 0)

        repo.mark_as_read(rows[0]["id"])
        self.assertEqual(repo.count_unread(user.id), 0)
        self.assertEqual(repo.delete_read_by_user(user.id), 1)
        self.assertEqual(repo.list_by_user(user.id), [])

    def test_notify_by_preference_persists_in_app_and_respects_none(self) -> None:
        user_repo = UserRepository()
        in_app_user = User.create("in_app_notice", Role.USER)
        silent_user = User.create("silent_notice", Role.USER)
        user_repo.create(in_app_user, "hashed")
        user_repo.create(silent_user, "hashed")

        notify_by_preference(
            in_app_user.id,
            "",
            NotificationMode.IN_APP.value,
            "系统通知",
            "请查看排班结果",
        )
        notify_by_preference(
            silent_user.id,
            "",
            NotificationMode.NONE.value,
            "不应保存",
            "这条消息不应进入通知中心",
        )

        repo = NotificationRepository()
        self.assertEqual(repo.count_unread(in_app_user.id), 1)
        self.assertEqual(repo.count_unread(silent_user.id), 0)
        self.assertEqual(repo.list_by_user(silent_user.id), [])


if __name__ == "__main__":
    unittest.main()
