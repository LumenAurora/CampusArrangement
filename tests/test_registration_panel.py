from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import PySide6
from PySide6.QtWidgets import QApplication

from app.application.activity_service import ActivityService
from app.application.registration_service import RegistrationService
from app.domain.models import (
    Activity,
    ActivityStatus,
    AllocationMode,
    Role,
    SignupMode,
    TimeSlot,
    User,
)
from app.infrastructure.db import init_db
from app.infrastructure.repositories import (
    ActivityRepository,
    RegistrationRepository,
    TimeSlotRepository,
)
from app.ui.registration_widgets import RegistrationPanel
from app.ui.ui_utils import set_banner


class RegistrationPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault(
            "QT_PLUGIN_PATH",
            str(Path(PySide6.__file__).resolve().parent / "Qt" / "plugins"),
        )
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_file.close()
        self._db_path = db_file.name
        self._orig_db_path = os.environ.get("CAMPUS_DB_PATH")
        os.environ["CAMPUS_DB_PATH"] = self._db_path
        self.addCleanup(self._cleanup_db)

        init_db()
        self.activity_repo = ActivityRepository()
        self.slot_repo = TimeSlotRepository()
        self.reg_repo = RegistrationRepository()
        self.activity_service = ActivityService(self.activity_repo, self.slot_repo)
        self.registration_service = RegistrationService(
            self.slot_repo,
            self.reg_repo,
            self.activity_repo,
        )
        self.user = User.create("student", Role.USER)

    def _cleanup_db(self) -> None:
        if self._orig_db_path is None:
            os.environ.pop("CAMPUS_DB_PATH", None)
        else:
            os.environ["CAMPUS_DB_PATH"] = self._orig_db_path
        try:
            os.remove(self._db_path)
        except OSError:
            pass

    def test_future_activity_replaces_stale_duplicate_error_with_not_started_reason(self) -> None:
        now = datetime.now(timezone.utc)
        signup_start = now + timedelta(hours=1)
        signup_end = now + timedelta(hours=2)
        activity = Activity.create(
            name="未来志愿活动",
            owner_id="admin",
            signup_start=signup_start,
            signup_end=signup_end,
            details="",
            signup_mode=SignupMode.REALTIME,
            allocation_mode=AllocationMode.GREEDY,
            location="",
        )
        self.activity_repo.create(activity)
        self.activity_repo.update_status(activity.id, ActivityStatus.OPEN)
        slot = TimeSlot.create_time_slot(
            activity.id,
            signup_start + timedelta(days=1),
            signup_start + timedelta(days=1, hours=1),
            capacity=30,
            name="测试时段",
        )
        self.slot_repo.create(slot)

        panel = RegistrationPanel(
            self.activity_service,
            self.registration_service,
            self.user,
            self.reg_repo,
        )
        set_banner(panel._message, "error", "您已报名该活动，请勿重复报名")
        panel._load_slots()

        self.assertIn("报名尚未开始", panel._message.text())
        self.assertFalse(panel._submit_btn.isEnabled())
