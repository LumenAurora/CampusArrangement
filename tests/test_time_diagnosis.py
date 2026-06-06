"""诊断时间处理逻辑的测试 — 复现"报名已结束但还能报名"的bug。

关键发现：DB中存储的是 naive 本地时间ISO字符串（无时区），来自 QDateTimeEdit.toPython()。
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.infrastructure.db import init_db
from app.infrastructure.repositories import (
    ActivityRepository,
    RegistrationRepository,
    TimeSlotRepository,
    UserRepository,
)
from app.domain.models import (
    Activity, ActivityStatus, AllocationMode,
    Role, SignupMode, TimeSlot,
)
from app.application.registration_service import RegistrationService
from app.application.user_service import UserService
from app.ui.ui_utils import to_utc, format_activity_status


class TimeDiagnosisTests(unittest.TestCase):
    """隔离测试时间处理逻辑 — 精确复现 bug 场景。

    每个测试使用独立的临时DB，通过 patch DB_PATH 实现。
    """

    @classmethod
    def setUpClass(cls) -> None:
        """创建临时目录用于存放测试DB"""
        cls._tmpdir = tempfile.mkdtemp(prefix="campus_time_test_")

    def setUp(self) -> None:
        db_path = os.path.join(self._tmpdir, f"{self._testMethodName}.db")
        if os.path.exists(db_path):
            os.remove(db_path)

        # patch DB_PATH 使得所有数据库操作使用独立DB
        self._db_patcher = patch("app.infrastructure.db.DB_PATH", Path(db_path))
        self._db_patcher.start()
        self.addCleanup(self._db_patcher.stop)

        init_db()

        self._user_repo = UserRepository()
        self._activity_repo = ActivityRepository()
        self._slot_repo = TimeSlotRepository()
        self._reg_repo = RegistrationRepository()

        self._user_service = UserService(self._user_repo)
        self._reg_service = RegistrationService(
            self._slot_repo, self._reg_repo, self._activity_repo,
        )

        self._admin = self._user_service.register(
            current_user=None, username="admin", password="pass", role=Role.SUPER_ADMIN,
        )
        self._user = self._user_service.register(
            current_user=self._admin, username="testuser", password="pass", role=Role.USER,
        )

    # ── 辅助方法：模拟UI创建活动的完整链路 ───────────────────────

    def _create_activity_like_ui(self, signup_start: datetime, signup_end: datetime) -> dict:
        """模拟从 QDateTimeEdit.toPython() → Activity.create → DB → 读回的完整链路。

        QDateTimeEdit.toPython() 返回 naive datetime（本地时间），
        存入 DB 时为无时区的 ISO 字符串。
        """
        if signup_start.tzinfo is not None:
            signup_start = signup_start.astimezone().replace(tzinfo=None)
        if signup_end.tzinfo is not None:
            signup_end = signup_end.astimezone().replace(tzinfo=None)

        activity = Activity.create(
            name="测试活动",
            owner_id=self._admin.id,
            signup_start=signup_start,
            signup_end=signup_end,
            details="",
            signup_mode=SignupMode.REALTIME,
            allocation_mode=AllocationMode.GREEDY,
            location="",
        )
        self._activity_repo.create(activity)
        self._activity_repo.update_status(activity.id, ActivityStatus.OPEN)

        row = self._activity_repo.get(activity.id)
        return row

    # ── 1. to_utc 基础行为 ──────────────────────────────────────

    def test_to_utc_naive_string(self):
        """naive ISO 字符串应被当作本地时间转为 UTC"""
        result = to_utc("2026-06-06T14:30:00")
        self.assertIsNotNone(result.tzinfo)
        self.assertEqual(result.utcoffset(), timedelta(0))
        local_offset = result.astimezone().utcoffset()
        print(f"\n  [DIAG] to_utc('2026-06-06T14:30:00') = {result}")
        print(f"  [DIAG] 本地时区偏移 = {local_offset}")
        expected_utc_hour = (14 - local_offset.total_seconds() / 3600) % 24
        self.assertEqual(result.hour, int(expected_utc_hour))

    def test_to_utc_aware_string(self):
        """带时区的 ISO 字符串应正确转为 UTC"""
        result = to_utc("2026-06-06T14:30:00+08:00")
        self.assertEqual(result.utcoffset(), timedelta(0))
        self.assertEqual(result.hour, 6)  # 14:30+08:00 = 06:30 UTC

    def test_to_utc_utc_z_string(self):
        """带 Z 后缀应正确解析"""
        result = to_utc("2026-06-06T14:30:00Z")
        self.assertEqual(result.utcoffset(), timedelta(0))
        self.assertEqual(result.hour, 14)  # Z = UTC

    # ── 2. format_activity_status — 用DB实际格式测试 ────────────

    def test_format_status_signup_ended__naive_storage(self):
        """使用DB中实际的naive本地时间格式测试状态判定"""
        now = datetime.now(timezone.utc)
        end_local = (now - timedelta(hours=1)).astimezone().replace(tzinfo=None)
        start_local = (now - timedelta(hours=3)).astimezone().replace(tzinfo=None)

        activity = {
            "id": "test1", "name": "已结束", "status": "open",
            "signup_start": start_local.isoformat(),
            "signup_end": end_local.isoformat(),
        }

        print(f"\n  [DIAG] now(UTC)                  = {now}")
        print(f"  [DIAG] signup_end(naive,local)   = {activity['signup_end']}")
        print(f"  [DIAG] to_utc(signup_end)         = {to_utc(activity['signup_end'])}")
        print(f"  [DIAG] now > to_utc(end)?          {now > to_utc(activity['signup_end'])}")

        status = format_activity_status(activity)
        print(f"  [DIAG] format_activity_status     = '{status}'")
        self.assertEqual(status, "报名已截止")

    def test_format_status_signup_not_started__naive_storage(self):
        """使用DB实际格式测试未开始状态"""
        now = datetime.now(timezone.utc)
        start_local = (now + timedelta(hours=2)).astimezone().replace(tzinfo=None)
        end_local = (now + timedelta(hours=5)).astimezone().replace(tzinfo=None)

        activity = {
            "id": "test2", "name": "未来活动", "status": "open",
            "signup_start": start_local.isoformat(),
            "signup_end": end_local.isoformat(),
        }

        status = format_activity_status(activity)
        self.assertEqual(status, "报名未开始")

    # ── 3. RegistrationService.register — 完整DB链路 ─────────────

    def test_register_rejected_when_signup_ended__full_flow(self):
        """模拟完整UI流程：QDateTimeEdit → DB → register → 拒绝"""
        now = datetime.now(timezone.utc)
        start_local = (now - timedelta(hours=3)).astimezone().replace(tzinfo=None)
        end_local = (now - timedelta(hours=1)).astimezone().replace(tzinfo=None)

        activity_row = self._create_activity_like_ui(start_local, end_local)

        self.assertNotIn("+", activity_row["signup_start"])
        print(f"\n  [DIAG] DB 中 signup_end = '{activity_row['signup_end']}'")

        slot = TimeSlot.create_time_slot(
            activity_id=activity_row["id"], start_time=start_local,
            end_time=end_local, capacity=10,
        )
        self._slot_repo.create(slot)

        from app.domain.exceptions import ValidationError
        with self.assertRaises(ValidationError) as ctx:
            self._reg_service.register(
                user_id=self._user.id, activity_id=activity_row["id"],
                slot_id=slot.id, priority=1,
            )
        self.assertIn("截止", str(ctx.exception))

    def test_register_rejected_when_not_started__full_flow(self):
        """报名未开始时应拒绝（完整DB链路）"""
        now = datetime.now(timezone.utc)
        start_local = (now + timedelta(hours=2)).astimezone().replace(tzinfo=None)
        end_local = (now + timedelta(hours=5)).astimezone().replace(tzinfo=None)

        activity_row = self._create_activity_like_ui(start_local, end_local)
        slot = TimeSlot.create_time_slot(
            activity_id=activity_row["id"], start_time=start_local,
            end_time=end_local, capacity=10,
        )
        self._slot_repo.create(slot)

        from app.domain.exceptions import ValidationError
        with self.assertRaises(ValidationError) as ctx:
            self._reg_service.register(
                user_id=self._user.id, activity_id=activity_row["id"],
                slot_id=slot.id, priority=1,
            )
        self.assertIn("尚未开始", str(ctx.exception))

    # ── 4. 精确复现：14:30-15:30 报名时段，16:30检查 ─────────────

    def test_scenario_1430_1530_at_1630(self):
        """14:30-15:30报名时段，当前时间16:30 — 应从所有层面拒绝报名。"""
        fake_now_utc = datetime(2026, 6, 6, 8, 30, 0, tzinfo=timezone.utc)
        start_utc = datetime(2026, 6, 6, 6, 30, 0, tzinfo=timezone.utc)  # 14:30 local
        end_utc = datetime(2026, 6, 6, 7, 30, 0, tzinfo=timezone.utc)    # 15:30 local

        start_naive = start_utc.astimezone().replace(tzinfo=None)
        end_naive = end_utc.astimezone().replace(tzinfo=None)

        print(f"\n  [DIAG] === 14:30-15:30报名，16:30查看 ===")
        print(f"  [DIAG] fake_now(UTC)  = {fake_now_utc}")
        print(f"  [DIAG] start_naive    = {start_naive.isoformat()}")
        print(f"  [DIAG] end_naive      = {end_naive.isoformat()}")
        print(f"  [DIAG] to_utc(end)    = {to_utc(end_naive.isoformat())}")
        print(f"  [DIAG] now > end?     {fake_now_utc > to_utc(end_naive.isoformat())}")

        # 1) format_activity_status
        activity_dict = {
            "id": "scenario1", "name": "14:30-15:30活动", "status": "open",
            "signup_start": start_naive.isoformat(),
            "signup_end": end_naive.isoformat(),
        }

        with patch("app.ui.ui_utils.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now_utc
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            status = format_activity_status(activity_dict)

        self.assertEqual(status, "报名已截止",
                         f"16:30时应显示'报名已截止'，实际'{status}'")

        # 2) RegistrationService.register
        activity_row = self._create_activity_like_ui(start_naive, end_naive)
        slot = TimeSlot.create_time_slot(
            activity_id=activity_row["id"], start_time=start_naive,
            end_time=end_naive, capacity=10,
        )
        self._slot_repo.create(slot)

        from app.domain.exceptions import ValidationError
        with patch("app.application.registration_service.datetime") as mock_svc_dt:
            mock_svc_dt.now.return_value = fake_now_utc
            mock_svc_dt.fromisoformat = datetime.fromisoformat
            mock_svc_dt.timezone = timezone
            mock_svc_dt.timedelta = timedelta
            with self.assertRaises(ValidationError) as ctx:
                self._reg_service.register(
                    user_id=self._user.id, activity_id=activity_row["id"],
                    slot_id=slot.id, priority=1,
                )
        self.assertIn("截止", str(ctx.exception))

    # ── 5. 验证 DB 存储格式 ─────────────────────────────────────

    def test_stored_format_is_naive_local_time(self):
        """验证：通过 UI 路径创建的活动，DB 中存储的是 naive 本地时间字符串"""
        now = datetime.now(timezone.utc)
        local_dt = (now + timedelta(hours=2)).astimezone().replace(tzinfo=None)

        activity_row = self._create_activity_like_ui(local_dt, local_dt + timedelta(hours=3))
        stored = activity_row["signup_start"]

        print(f"\n  [DIAG] DB存储值: '{stored}'")
        self.assertIsInstance(stored, str)
        self.assertNotIn("+", stored, "DB存储不应该含+时区标记")
        self.assertNotIn("Z", stored, "DB存储不应该含Z时区标记")

        parsed = to_utc(stored)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.utcoffset(), timedelta(0))


if __name__ == "__main__":
    unittest.main()
