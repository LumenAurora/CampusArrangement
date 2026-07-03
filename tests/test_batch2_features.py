"""批次 2 新功能系统化单元测试。

覆盖：POINTS 模式、意愿点校验、提前结束签到、用户设置、points 字段持久化、
远程仓储方法存在性、format_activity_status 含 checkin_closed。
"""

import os
import random
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate

from app.api_server import _to_user
from app.application.activity_service import ActivityService
from app.application.checkin_service import CheckInService
from app.application.registration_service import RegistrationService
from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import (
    Activity,
    ActivityStatus,
    AllocationMode,
    CheckInMode,
    MAX_POINTS,
    NotificationMode,
    Registration,
    RegistrationStatus,
    Role,
    TimeSlot,
    User,
)
from app.domain.services import schedule_registrations
from app.infrastructure.db import init_db, transaction
from app.infrastructure.repositories import (
    ActivityRepository,
    CheckInRepository,
    RegistrationRepository,
    ScheduleRepository,
    TimeSlotRepository,
    UserRepository,
)
from app.ui.activity_widgets import _next_monday_after
from app.ui.ui_utils import format_activity_status


class _IsolatedDBTestCase(unittest.TestCase):
    """每个测试使用独立 DB（通过 patch DB_PATH 避免模块导入缓存）。"""

    _tmpdir: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        if not cls._tmpdir:
            cls._tmpdir = tempfile.mkdtemp(prefix="campus_b2_test_")

    def setUp(self) -> None:
        db_path = os.path.join(self._tmpdir, f"{self.__class__.__name__}_{self._testMethodName}.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        self._db_patcher = patch("app.infrastructure.db.DB_PATH", Path(db_path))
        self._db_patcher.start()
        self.addCleanup(self._db_patcher.stop)
        os.environ.pop("CAMPUS_DB_PATH", None)
        init_db()


class PointsModeTests(unittest.TestCase):
    """POINTS 分配模式：高者优先，同级随机抽签，零点退化为纯随机。"""

    def test_points_mode_higher_points优先(self) -> None:
        now = datetime.now(timezone.utc)
        slot = TimeSlot.create(activity_id="a1", start_time=now, end_time=now + timedelta(hours=1), capacity=1)
        reg_high = Registration.create(user_id="u_high", activity_id="a1", slot_id=slot.id, priority=1, points=80)
        reg_low = Registration.create(user_id="u_low", activity_id="a1", slot_id=slot.id, priority=1, points=20)
        rng = random.Random(42)
        results = schedule_registrations([reg_low, reg_high], [slot], mode=AllocationMode.POINTS, rng=rng)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1].user_id, "u_high")

    def test_points_mode_same_points_random_抽签(self) -> None:
        now = datetime.now(timezone.utc)
        slot = TimeSlot.create(activity_id="a1", start_time=now, end_time=now + timedelta(hours=1), capacity=1)
        reg_a = Registration.create(user_id="u_a", activity_id="a1", slot_id=slot.id, priority=1, points=50)
        reg_b = Registration.create(user_id="u_b", activity_id="a1", slot_id=slot.id, priority=1, points=50)
        rng = random.Random(42)
        results = schedule_registrations([reg_a, reg_b], [slot], mode=AllocationMode.POINTS, rng=rng)
        self.assertEqual(len(results), 1)
        self.assertIn(results[0][1].user_id, {"u_a", "u_b"})

    def test_points_mode_zero_points(self) -> None:
        now = datetime.now(timezone.utc)
        slot = TimeSlot.create(activity_id="a1", start_time=now, end_time=now + timedelta(hours=1), capacity=2)
        regs = [
            Registration.create(user_id=f"u{i}", activity_id="a1", slot_id=slot.id, priority=1, points=0)
            for i in range(5)
        ]
        rng = random.Random(42)
        results = schedule_registrations(regs, [slot], mode=AllocationMode.POINTS, rng=rng)
        self.assertEqual(len(results), 2)
        assigned = {r[1].user_id for r in results}
        self.assertTrue(assigned.issubset({f"u{i}" for i in range(5)}))


class PointsValidationTests(_IsolatedDBTestCase):
    """register 方法及 _validate_points_total_in_txn 的意愿点校验。"""

    def setUp(self) -> None:
        super().setUp()
        self.user_repo = UserRepository()
        self.activity_repo = ActivityRepository()
        self.slot_repo = TimeSlotRepository()
        self.reg_repo = RegistrationRepository()

        self.admin = User.create("points_admin", Role.SUPER_ADMIN)
        self.user_repo.create(self.admin, "hash")

        now = datetime.now(timezone.utc)
        self.activity = Activity.create(
            name="意愿点活动",
            owner_id=self.admin.id,
            signup_start=now,
            signup_end=now + timedelta(days=1),
            details="points test",
            allocation_mode=AllocationMode.POINTS,
        )
        self.activity_repo.create(self.activity)
        self.activity_repo.update_status(self.activity.id, ActivityStatus.OPEN)

        self.slot = TimeSlot.create(self.activity.id, now, now + timedelta(hours=1), capacity=10)
        self.slot_repo.create(self.slot)

        self.reg_service = RegistrationService(self.slot_repo, self.reg_repo, self.activity_repo)

    def _create_user(self, username: str) -> User:
        user = User.create(username, Role.USER)
        self.user_repo.create(user, "hash")
        return user

    def _make_pending_reg(self, user_id: str, points: int) -> Registration:
        reg = Registration(
            id=str(uuid.uuid4()),
            user_id=user_id,
            activity_id=self.activity.id,
            slot_id=self.slot.id,
            priority=1,
            status=RegistrationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            points=points,
        )
        self.reg_repo.create(reg)
        return reg

    def test_register_points_exceeds_max_single(self) -> None:
        user = self._create_user("user_single")
        with self.assertRaises(ValidationError):
            self.reg_service.register(
                user.id, self.activity.id, self.slot.id, priority=1, points=MAX_POINTS + 1
            )

    def test_register_points_total_exceeds_max(self) -> None:
        user = self._create_user("user_total_exceed")
        self._make_pending_reg(user.id, points=90)
        with transaction() as conn:
            with self.assertRaises(ValidationError):
                self.reg_service._validate_points_total_in_txn(conn, user.id, self.activity.id, 10)

    def test_register_points_within_limit(self) -> None:
        user = self._create_user("user_within_limit")
        self._make_pending_reg(user.id, points=50)
        with transaction() as conn:
            self.reg_service._validate_points_total_in_txn(conn, user.id, self.activity.id, 49)


class CheckInCloseReopenTests(_IsolatedDBTestCase):
    """close_checkin / reopen_checkin / 签到拦截。"""

    def setUp(self) -> None:
        super().setUp()
        self.user_repo = UserRepository()
        self.activity_repo = ActivityRepository()
        self.slot_repo = TimeSlotRepository()
        self.checkin_repo = CheckInRepository()
        self.schedule_repo = ScheduleRepository()

        self.admin = User.create("checkin_admin", Role.SUPER_ADMIN)
        self.user_repo.create(self.admin, "hash")
        self.normal_user = User.create("normal_user", Role.USER)
        self.user_repo.create(self.normal_user, "hash")

        now = datetime.now(timezone.utc)
        self.activity = Activity.create(
            name="签到测试活动",
            owner_id=self.admin.id,
            signup_start=now,
            signup_end=now + timedelta(days=1),
            details="checkin test",
        )
        self.activity_repo.create(self.activity)
        self.slot = TimeSlot.create(self.activity.id, now, now + timedelta(hours=1), capacity=10)
        self.slot_repo.create(self.slot)

        self.checkin_service = CheckInService(self.checkin_repo, self.schedule_repo, self.activity_repo)

    def test_close_checkin_success(self) -> None:
        self.checkin_service.close_checkin(self.admin, self.activity.id)
        activity = self.activity_repo.get(self.activity.id)
        self.assertIsNotNone(activity)
        self.assertTrue(activity["checkin_closed"])

    def test_close_checkin_permission_denied(self) -> None:
        with self.assertRaises(PermissionDenied):
            self.checkin_service.close_checkin(self.normal_user, self.activity.id)

    def test_close_checkin_already_closed(self) -> None:
        self.checkin_service.close_checkin(self.admin, self.activity.id)
        with self.assertRaises(ValidationError):
            self.checkin_service.close_checkin(self.admin, self.activity.id)

    def test_reopen_checkin_success(self) -> None:
        self.checkin_service.close_checkin(self.admin, self.activity.id)
        self.checkin_service.reopen_checkin(self.admin, self.activity.id)
        activity = self.activity_repo.get(self.activity.id)
        self.assertIsNotNone(activity)
        self.assertFalse(activity["checkin_closed"])

    def test_checkin_blocked_when_closed(self) -> None:
        self.activity_repo.update_status(self.activity.id, ActivityStatus.CLOSED)
        self.checkin_service.close_checkin(self.admin, self.activity.id)
        with self.assertRaises(ValidationError) as ctx:
            self.checkin_service.check_in(self.admin, self.activity.id, self.normal_user.id, self.slot.id)
        self.assertIn("签到已结束", str(ctx.exception))

    def test_location_checkin_rejects_out_of_range_submitted_coordinates(self) -> None:
        with self.assertRaises(ValidationError):
            self.checkin_service.location_check_in(
                user_id=self.normal_user.id,
                activity_id=self.activity.id,
                slot_id=self.slot.id,
                latitude=999,
                longitude=999,
            )
        self.assertIsNone(self.checkin_repo.get_by_user_slot(self.normal_user.id, self.slot.id))


class UserSettingsTests(_IsolatedDBTestCase):
    """UserRepository 的 avatar / notification_mode 读写 + _to_user 映射。"""

    def setUp(self) -> None:
        super().setUp()
        self.user_repo = UserRepository()
        self.admin = User.create("settings_admin", Role.SUPER_ADMIN)
        self.user_repo.create(self.admin, "hash")

    def test_update_avatar(self) -> None:
        self.user_repo.update_avatar(self.admin.id, "/path/to/avatar.png")
        record = self.user_repo.get_by_id(self.admin.id)
        self.assertIsNotNone(record)
        self.assertEqual(record["avatar_path"], "/path/to/avatar.png")

    def test_update_notification_mode(self) -> None:
        self.user_repo.update_notification_mode(self.admin.id, NotificationMode.EMAIL.value)
        record = self.user_repo.get_by_id(self.admin.id)
        self.assertIsNotNone(record)
        self.assertEqual(record["notification_mode"], NotificationMode.EMAIL.value)

    def test_to_user_includes_new_fields(self) -> None:
        self.user_repo.update_avatar(self.admin.id, "/avatar.png")
        self.user_repo.update_notification_mode(self.admin.id, NotificationMode.NONE.value)
        record = self.user_repo.get_by_id(self.admin.id)
        self.assertIsNotNone(record)
        user = _to_user(record)
        self.assertEqual(user.avatar_path, "/avatar.png")
        self.assertEqual(user.notification_mode, NotificationMode.NONE)

    def test_api_get_user_me_alias_returns_current_user(self) -> None:
        from app.api_server import get_user

        with patch("app.api_server.user_repo", self.user_repo):
            result = get_user("me", self.admin)
        self.assertEqual(result["id"], self.admin.id)
        self.assertNotIn("password_hash", result)


class RegistrationPointsRepositoryTests(_IsolatedDBTestCase):
    """RegistrationRepository.to_models 保留 points 字段。"""

    def setUp(self) -> None:
        super().setUp()
        self.user_repo = UserRepository()
        self.activity_repo = ActivityRepository()
        self.slot_repo = TimeSlotRepository()
        self.reg_repo = RegistrationRepository()

        self.owner = User.create("reg_owner", Role.ORGANIZER)
        self.user_repo.create(self.owner, "hash")
        self.registrant = User.create("registrant", Role.USER)
        self.user_repo.create(self.registrant, "hash")

        now = datetime.now(timezone.utc)
        self.activity = Activity.create("活动", self.owner.id, now, now + timedelta(days=1), "d")
        self.activity_repo.create(self.activity)
        self.slot = TimeSlot.create(self.activity.id, now, now + timedelta(hours=1), capacity=5)
        self.slot_repo.create(self.slot)

    def test_to_models_includes_points(self) -> None:
        reg = Registration.create(
            user_id=self.registrant.id,
            activity_id=self.activity.id,
            slot_id=self.slot.id,
            priority=1,
            points=77,
        )
        self.reg_repo.create(reg)
        rows = self.reg_repo.list_by_user_activity(self.registrant.id, self.activity.id)
        models = RegistrationRepository.to_models(rows)
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].points, 77)


class ActivityUpdateServiceTests(_IsolatedDBTestCase):
    """活动配置编辑入口支持本地/远程统一调用。"""

    def setUp(self) -> None:
        super().setUp()
        self.user_repo = UserRepository()
        self.activity_repo = ActivityRepository()
        self.slot_repo = TimeSlotRepository()
        self.service = ActivityService(self.activity_repo, self.slot_repo)
        self.owner = User.create("activity_owner", Role.ORGANIZER)
        self.user_repo.create(self.owner, "hash")
        now = datetime.now(timezone.utc)
        self.activity = Activity.create(
            "待编辑活动",
            self.owner.id,
            now,
            now + timedelta(days=1),
            "old",
            location="old-place",
        )
        self.activity_repo.create(self.activity)

    def test_update_activity_changes_basic_fields(self) -> None:
        now = datetime.now(timezone.utc)
        self.service.update_activity(
            self.owner,
            self.activity.id,
            {
                "name": "新活动名",
                "details": "new details",
                "location": "new-place",
                "signup_start": now.isoformat(),
                "signup_end": (now + timedelta(days=2)).isoformat(),
            },
        )

        updated = self.activity_repo.get(self.activity.id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["name"], "新活动名")
        self.assertEqual(updated["details"], "new details")
        self.assertEqual(updated["location"], "new-place")

    def test_update_activity_validates_signup_window(self) -> None:
        now = datetime.now(timezone.utc)
        with self.assertRaises(ValidationError):
            self.service.update_activity(
                self.owner,
                self.activity.id,
                {
                    "signup_start": now.isoformat(),
                    "signup_end": now.isoformat(),
                },
            )

    def test_update_location_checkin_activity_requires_coordinates(self) -> None:
        now = datetime.now(timezone.utc)
        activity = Activity.create(
            "位置签到活动",
            self.owner.id,
            now,
            now + timedelta(days=1),
            "location test",
            location="30.1234,120.5678",
            checkin_mode=CheckInMode.LOCATION,
        )
        self.activity_repo.create(activity)

        with self.assertRaises(ValidationError):
            self.service.update_activity(self.owner, activity.id, {"location": "教学楼大厅"})

        self.service.update_activity(self.owner, activity.id, {"location": "31.0000,121.0000"})
        updated = self.activity_repo.get(activity.id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["location"], "31.0000,121.0000")

    def test_create_location_checkin_activity_rejects_out_of_range_coordinates(self) -> None:
        now = datetime.now(timezone.utc)
        with self.assertRaises(ValidationError):
            self.service.create_activity(
                user=self.owner,
                name="越界位置签到",
                signup_start=now,
                signup_end=now + timedelta(days=1),
                details="bad coordinates",
                location="999,999",
                checkin_mode=CheckInMode.LOCATION.value,
            )

        created = self.service.create_activity(
            user=self.owner,
            name="合法位置签到",
            signup_start=now,
            signup_end=now + timedelta(days=1),
            details="ok coordinates",
            location="30.1234,120.5678",
            checkin_mode=CheckInMode.LOCATION.value,
        )
        self.assertEqual(created.location, "30.1234,120.5678")


class RemoteRepoMethodTests(unittest.TestCase):
    """确保远程仓储/服务保留批次 2 新增方法（防重构丢失）。"""

    def test_remote_user_repo_has_avatar_methods(self) -> None:
        from app.infrastructure.api_client import ApiClient
        from app.infrastructure.remote_repositories import RemoteUserRepository

        repo = RemoteUserRepository(ApiClient("http://localhost:9999"))
        self.assertTrue(hasattr(repo, "update_avatar"))
        self.assertTrue(hasattr(repo, "update_notification_mode"))

    def test_api_client_login_preserves_profile_fields(self) -> None:
        from app.infrastructure.api_client import ApiClient

        client = ApiClient("http://localhost:9999")

        def fake_request(method: str, path: str, **kwargs) -> dict:
            self.assertEqual(method, "POST")
            self.assertEqual(path, "/auth/login")
            return {
                "token": "token1",
                "user": {
                    "id": "user1",
                    "username": "alice",
                    "role": Role.USER.value,
                    "status": "approved",
                    "avatar_path": "avatars/user1.png",
                    "notification_mode": NotificationMode.EMAIL.value,
                },
            }

        client._request = fake_request  # type: ignore[method-assign]

        user = client.login("alice", "pw")

        self.assertEqual(user.avatar_path, "avatars/user1.png")
        self.assertEqual(user.notification_mode, NotificationMode.EMAIL)

    def test_api_client_bypasses_proxy_for_loopback_server(self) -> None:
        from app.infrastructure.api_client import ApiClient, is_loopback_api_url

        self.assertTrue(is_loopback_api_url("http://localhost:8000"))
        self.assertTrue(is_loopback_api_url("http://127.0.0.1:8000"))
        self.assertTrue(is_loopback_api_url("http://[::1]:8000"))
        self.assertFalse(is_loopback_api_url("https://example.com"))

        local_client = ApiClient("http://127.0.0.1:8000")
        remote_client = ApiClient("https://example.com")

        self.assertFalse(local_client._session.trust_env)
        self.assertTrue(remote_client._session.trust_env)

    def test_pending_users_route_is_not_captured_as_user_id(self) -> None:
        from starlette.routing import Match

        from app.api_server import app

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/users/pending",
            "root_path": "",
            "headers": [],
        }
        for route in app.router.routes:
            match, _ = route.matches(scope)
            if match == Match.FULL:
                self.assertEqual(route.endpoint.__name__, "list_pending_users")
                break
        else:
            self.fail("/users/pending route was not matched")

    def test_user_list_api_strips_password_hashes(self) -> None:
        from app.api_server import list_users

        admin = User.create("admin", Role.SUPER_ADMIN)
        with patch("app.api_server.user_repo") as fake_repo:
            fake_repo.list_all.return_value = [
                {"id": "user1", "username": "alice", "password_hash": "secret-hash"},
            ]

            users = list_users(current_user=admin)

        self.assertEqual(users, [{"id": "user1", "username": "alice"}])

    def test_activity_list_hides_unpublished_activities_from_regular_users(self) -> None:
        from app.api_server import list_activities

        activities = [
            {"id": "draft1", "name": "草稿", "status": ActivityStatus.DRAFT.value},
            {"id": "review1", "name": "待审核", "status": ActivityStatus.PENDING_REVIEW.value},
            {"id": "open1", "name": "开放", "status": ActivityStatus.OPEN.value},
            {"id": "closed1", "name": "已关闭", "status": ActivityStatus.CLOSED.value},
            {"id": "archived1", "name": "已归档", "status": ActivityStatus.ARCHIVED.value},
        ]
        regular_user = User.create("student", Role.USER)
        admin = User.create("admin", Role.SUPER_ADMIN)

        with patch("app.api_server.activity_service") as fake_service:
            fake_service.list_activities.return_value = activities
            visible_to_user = list_activities(current_user=regular_user)
            visible_to_admin = list_activities(current_user=admin)

        self.assertEqual(
            [activity["id"] for activity in visible_to_user],
            ["open1", "closed1", "archived1"],
        )
        self.assertEqual([activity["id"] for activity in visible_to_admin], [activity["id"] for activity in activities])

    def test_remote_user_repo_uploads_avatar_file(self) -> None:
        from app.infrastructure.remote_repositories import RemoteUserRepository

        class FakeApi:
            upload: tuple[str, str, str] | None = None

            def post_file(self, path: str, field_name: str, file_path: str) -> dict:
                self.upload = (path, field_name, file_path)
                return {"ok": True}

        api = FakeApi()
        repo = RemoteUserRepository(api)  # type: ignore[arg-type]
        repo.update_avatar("user1", "avatars/user1.png")
        self.assertIsNotNone(api.upload)
        self.assertEqual(api.upload[0], "/users/me/avatar")
        self.assertEqual(api.upload[1], "file")
        self.assertTrue(api.upload[2].endswith("resources/uploads/avatars/user1.png"))

    def test_remote_user_repo_get_by_id_falls_back_to_me(self) -> None:
        from app.domain.exceptions import PermissionDenied
        from app.infrastructure.remote_repositories import RemoteUserRepository

        class FakeApi:
            def get(self, path: str, params: dict | None = None) -> dict:
                if path == "/users/user1":
                    raise PermissionDenied("权限不足")
                if path == "/users/me":
                    return {"id": "user1", "username": "alice"}
                raise AssertionError(path)

        repo = RemoteUserRepository(FakeApi())  # type: ignore[arg-type]
        self.assertEqual(repo.get_by_id("user1")["username"], "alice")

    def test_remote_activity_repo_has_checkin_closed(self) -> None:
        from app.infrastructure.api_client import ApiClient
        from app.infrastructure.remote_repositories import MetricsCache, RemoteActivityRepository

        api = ApiClient("http://localhost:9999")
        repo = RemoteActivityRepository(api, MetricsCache(api))
        self.assertTrue(hasattr(repo, "update_checkin_closed"))

    def test_remote_activity_service_updates_activity(self) -> None:
        from app.application.remote_services import RemoteActivityService

        class FakeApi:
            call: tuple[str, dict] | None = None

            def put(self, path: str, json: dict) -> dict:
                self.call = (path, json)
                return {"ok": True}

        api = FakeApi()
        service = RemoteActivityService(api)  # type: ignore[arg-type]
        service.update_activity(
            User.create("owner", Role.ORGANIZER),
            "act1",
            {"name": "新的活动名", "location": "A101"},
        )

        self.assertEqual(api.call, ("/activities/act1", {"name": "新的活动名", "location": "A101"}))

    def test_remote_slot_repo_positions_uses_parent_alias(self) -> None:
        from app.infrastructure.remote_repositories import MetricsCache, RemoteTimeSlotRepository

        class FakeApi:
            path = ""

            def get(self, path: str, params: dict | None = None) -> list:
                self.path = path
                return []

        api = FakeApi()
        repo = RemoteTimeSlotRepository(api, MetricsCache(api))  # type: ignore[arg-type]
        self.assertEqual(repo.list_positions("parent1"), [])
        self.assertEqual(api.path, "/slots/parent1/positions")

    def test_remote_checkin_service_has_close_reopen(self) -> None:
        from app.infrastructure.api_client import ApiClient
        from app.application.remote_services import RemoteCheckInService

        svc = RemoteCheckInService(ApiClient("http://localhost:9999"))
        self.assertTrue(hasattr(svc, "close_checkin"))
        self.assertTrue(hasattr(svc, "reopen_checkin"))

    def test_remote_registration_service_sends_points(self) -> None:
        from app.application.remote_services import RemoteRegistrationService

        class FakeApi:
            payload: dict | None = None

            def post(self, path: str, json: dict) -> dict:
                self.payload = json
                return {
                    "id": "reg1",
                    "user_id": "user1",
                    "activity_id": json["activity_id"],
                    "slot_id": json["slot_id"],
                    "priority": json["priority"],
                    "points": json["points"],
                    "status": RegistrationStatus.PENDING.value,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

        api = FakeApi()
        svc = RemoteRegistrationService(api)  # type: ignore[arg-type]
        reg = svc.register("user1", "act1", "slot1", priority=1, points=42)
        self.assertEqual(api.payload["points"], 42)
        self.assertEqual(reg.points, 42)

    def test_api_registration_service_has_group_repo(self) -> None:
        from app.api_server import registration_service

        self.assertIsNotNone(registration_service._group_repo)


class FormatActivityStatusTests(unittest.TestCase):
    """format_activity_status 对 checkin_closed 的处理。"""

    def test_format_status_checkin_closed(self) -> None:
        activity = {"status": "closed", "checkin_closed": True}
        self.assertEqual(format_activity_status(activity), "签到已结束")

    def test_format_status_checkin_open(self) -> None:
        now = datetime.now(timezone.utc)
        activity = {
            "status": "closed",
            "checkin_closed": False,
            "checkin_end": (now + timedelta(hours=1)).isoformat(),
        }
        self.assertEqual(format_activity_status(activity), "签到中")


class CopyActivityDateShortcutTests(unittest.TestCase):
    """复制活动快捷日期应始终跳到下一周。"""

    def test_next_monday_after_monday_is_following_week(self) -> None:
        monday = QDate(2026, 7, 6)

        self.assertEqual(_next_monday_after(monday), QDate(2026, 7, 13))

    def test_next_monday_after_sunday_is_next_day(self) -> None:
        sunday = QDate(2026, 7, 5)

        self.assertEqual(_next_monday_after(sunday), QDate(2026, 7, 6))


if __name__ == "__main__":
    unittest.main()
