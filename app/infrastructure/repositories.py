from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable

from app.domain.exceptions import ConflictError
from app.domain.models import (
    Activity,
    ActivityStatus,
    CheckIn,
    CheckInStatus,
    Registration,
    RegistrationStatus,
    ScheduleResult,
    TimeSlot,
)
from app.infrastructure.db import get_connection, transaction


class UserRepository:
    def get_by_id(self, user_id: str) -> dict | None:
        conn = get_connection()
        try:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_by_username(self, username: str) -> dict | None:
        conn = get_connection()
        try:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_all(self) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at DESC").fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def delete(self, user_id: str) -> bool:
        conn = get_connection()
        try:
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def create(self, user, password_hash: str) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO users (id, username, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (user.id, user.username, user.role.value, password_hash, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()


class ActivityRepository:
    def create(self, activity: Activity) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO activities (id, name, status, owner_id, signup_start, signup_end, details, signup_mode, allocation_mode, location, checkin_code, checkin_mode, checkin_start, checkin_end) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    activity.id,
                    activity.name,
                    activity.status.value,
                    activity.owner_id,
                    activity.signup_start.isoformat(),
                    activity.signup_end.isoformat(),
                    activity.details,
                    activity.signup_mode.value,
                    activity.allocation_mode.value,
                    activity.location,
                    activity.checkin_code,
                    activity.checkin_mode.value,
                    activity.checkin_start.isoformat() if activity.checkin_start else None,
                    activity.checkin_end.isoformat() if activity.checkin_end else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, activity_id: str) -> dict | None:
        conn = get_connection()
        try:
            row = conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_all(self) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM activities ORDER BY signup_start DESC"
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_by_status(self, status: ActivityStatus) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM activities WHERE status = ? ORDER BY signup_start DESC",
                (status.value,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def count_all(self) -> int:
        conn = get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) AS total FROM activities").fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()

    def count_by_status(self, status: ActivityStatus) -> int:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM activities WHERE status = ?",
                (status.value,),
            ).fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()

    def delete(self, activity_id: str) -> bool:
        conn = get_connection()
        try:
            cursor = conn.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_status(self, activity_id: str, status: ActivityStatus) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE activities SET status = ? WHERE id = ?",
                (status.value, activity_id),
            )
            conn.commit()
        finally:
            conn.close()

    def update_checkin_code(self, activity_id: str, checkin_code: str) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE activities SET checkin_code = ? WHERE id = ?",
                (checkin_code, activity_id),
            )
            conn.commit()
        finally:
            conn.close()


class TimeSlotRepository:
    def get(self, slot_id: str) -> dict | None:
        conn = get_connection()
        try:
            row = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create(self, slot: TimeSlot) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO slots (id, activity_id, start_time, end_time, capacity, used_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    slot.id,
                    slot.activity_id,
                    slot.start_time.isoformat(),
                    slot.end_time.isoformat(),
                    slot.capacity,
                    slot.used_count,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_by_activity(self, activity_id: str, conn: sqlite3.Connection | None = None) -> list[dict]:
        own = conn is None
        if own:
            conn = get_connection()
        try:
            rows = conn.execute("SELECT * FROM slots WHERE activity_id = ? ORDER BY start_time ASC", (activity_id,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            if own:
                conn.close()

    def count_all(self) -> int:
        conn = get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) AS total FROM slots").fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()

    def lock_slot(self, slot_id: str, conn: sqlite3.Connection | None = None) -> bool:
        own = conn is None
        if own:
            conn = get_connection()
            conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute("SELECT capacity, used_count FROM slots WHERE id = ?", (slot_id,)).fetchone()
            if not row:
                return False
            if row["used_count"] >= row["capacity"]:
                return False
            conn.execute("UPDATE slots SET used_count = used_count + 1 WHERE id = ?", (slot_id,))
            if own:
                conn.commit()
            return True
        except Exception:
            if own:
                conn.rollback()
            raise
        finally:
            if own:
                conn.close()

    def release_slot(self, slot_id: str, conn: sqlite3.Connection | None = None) -> None:
        if conn is not None:
            conn.execute(
                "UPDATE slots SET used_count = MAX(used_count - 1, 0) WHERE id = ?",
                (slot_id,),
            )
        else:
            with transaction() as c:
                c.execute(
                    "UPDATE slots SET used_count = MAX(used_count - 1, 0) WHERE id = ?",
                    (slot_id,),
                )

    def reset_used_counts_for_activity(self, activity_id: str, conn: sqlite3.Connection | None = None) -> None:
        if conn is not None:
            conn.execute(
                "UPDATE slots SET used_count = 0 WHERE activity_id = ?",
                (activity_id,),
            )
        else:
            with transaction() as c:
                c.execute(
                    "UPDATE slots SET used_count = 0 WHERE activity_id = ?",
                    (activity_id,),
                )

    def increment_used_count(self, slot_id: str, count: int = 1, conn: sqlite3.Connection | None = None) -> None:
        if conn is not None:
            conn.execute(
                "UPDATE slots SET used_count = used_count + ? WHERE id = ?",
                (count, slot_id),
            )
        else:
            with transaction() as c:
                c.execute(
                    "UPDATE slots SET used_count = used_count + ? WHERE id = ?",
                    (count, slot_id),
                )

    def count_by_activity_status(self, status_value: str) -> int:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM slots "
                "WHERE activity_id IN (SELECT id FROM activities WHERE status = ?)",
                (status_value,),
            ).fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()

    @staticmethod
    def to_models(rows: Iterable[dict]) -> list[TimeSlot]:
        slots: list[TimeSlot] = []
        for row in rows:
            slots.append(
                TimeSlot(
                    id=row["id"],
                    activity_id=row["activity_id"],
                    start_time=datetime.fromisoformat(row["start_time"]),
                    end_time=datetime.fromisoformat(row["end_time"]),
                    capacity=row["capacity"],
                    used_count=row["used_count"],
                )
            )
        return slots


class RegistrationRepository:
    def create(self, registration: Registration, conn: sqlite3.Connection | None = None) -> None:
        own = conn is None
        if own:
            conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO registrations (id, user_id, activity_id, slot_id, priority, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    registration.id,
                    registration.user_id,
                    registration.activity_id,
                    registration.slot_id,
                    registration.priority,
                    registration.status.value,
                    registration.created_at.isoformat(),
                ),
            )
            if own:
                conn.commit()
        except sqlite3.IntegrityError:
            if own:
                conn.rollback()
            raise ConflictError("您已报名该活动，请勿重复报名")
        finally:
            if own:
                conn.close()

    def get(self, registration_id: str) -> dict | None:
        conn = get_connection()
        try:
            row = conn.execute("SELECT * FROM registrations WHERE id = ?", (registration_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_pending(self, activity_id: str, conn: sqlite3.Connection | None = None) -> list[dict]:
        own = conn is None
        if own:
            conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM registrations WHERE activity_id = ? AND status = ? ORDER BY created_at ASC",
                (activity_id, RegistrationStatus.PENDING.value),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            if own:
                conn.close()

    def reset_not_assigned_to_pending(self, activity_id: str, conn: sqlite3.Connection | None = None) -> None:
        if conn is not None:
            conn.execute(
                "UPDATE registrations SET status = ? WHERE activity_id = ? AND status IN (?, ?)",
                (RegistrationStatus.PENDING.value, activity_id, RegistrationStatus.NOT_ASSIGNED.value, RegistrationStatus.ASSIGNED.value),
            )
        else:
            with transaction() as c:
                c.execute(
                    "UPDATE registrations SET status = ? WHERE activity_id = ? AND status IN (?, ?)",
                    (RegistrationStatus.PENDING.value, activity_id, RegistrationStatus.NOT_ASSIGNED.value, RegistrationStatus.ASSIGNED.value),
                )

    def list_by_activity(self, activity_id: str) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM registrations WHERE activity_id = ? ORDER BY created_at ASC",
                (activity_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_by_user_activity(self, user_id: str, activity_id: str) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM registrations WHERE user_id = ? AND activity_id = ? AND status != ?",
                (user_id, activity_id, RegistrationStatus.CANCELLED.value),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_by_user(self, user_id: str) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM registrations WHERE user_id = ? AND status != ? ORDER BY created_at DESC",
                (user_id, RegistrationStatus.CANCELLED.value),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def update_status(self, registration_id: str, status: RegistrationStatus, conn: sqlite3.Connection | None = None) -> None:
        own = conn is None
        if own:
            conn = get_connection()
        try:
            conn.execute(
                "UPDATE registrations SET status = ? WHERE id = ?",
                (status.value, registration_id),
            )
            if own:
                conn.commit()
        finally:
            if own:
                conn.close()

    def count_all(self) -> int:
        conn = get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) AS total FROM registrations WHERE status != ?", (RegistrationStatus.CANCELLED.value,)).fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()

    def count_by_user(self, user_id: str) -> int:
        conn = get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) AS total FROM registrations WHERE user_id = ? AND status != ?", (user_id, RegistrationStatus.CANCELLED.value)).fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()

    @staticmethod
    def to_models(rows: Iterable[dict]) -> list[Registration]:
        regs: list[Registration] = []
        for row in rows:
            regs.append(
                Registration(
                    id=row["id"],
                    user_id=row["user_id"],
                    activity_id=row["activity_id"],
                    slot_id=row["slot_id"],
                    priority=row["priority"],
                    status=RegistrationStatus(row["status"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
            )
        return regs


class ScheduleRepository:
    def create(self, result: ScheduleResult, conn: sqlite3.Connection | None = None) -> None:
        own = conn is None
        if own:
            conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO schedule_results (id, activity_id, user_id, slot_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (result.id, result.activity_id, result.user_id, result.slot_id, result.created_at.isoformat()),
            )
            if own:
                conn.commit()
        finally:
            if own:
                conn.close()

    def clear_for_activity(self, activity_id: str, conn: sqlite3.Connection | None = None) -> None:
        own = conn is None
        if own:
            conn = get_connection()
        try:
            conn.execute("DELETE FROM schedule_results WHERE activity_id = ?", (activity_id,))
            if own:
                conn.commit()
        finally:
            if own:
                conn.close()

    def list_by_activity(self, activity_id: str) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute("SELECT * FROM schedule_results WHERE activity_id = ?", (activity_id,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_by_user(self, user_id: str) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute("SELECT * FROM schedule_results WHERE user_id = ?", (user_id,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def count_all(self) -> int:
        conn = get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) AS total FROM schedule_results").fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()

    def count_by_user(self, user_id: str) -> int:
        conn = get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) AS total FROM schedule_results WHERE user_id = ?", (user_id,)).fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()


class CheckInRepository:
    def get(self, checkin_id: str) -> dict | None:
        conn = get_connection()
        try:
            row = conn.execute("SELECT * FROM checkins WHERE id = ?", (checkin_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create(self, checkin: CheckIn) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO checkins (id, activity_id, user_id, slot_id, status, checked_at, latitude, longitude, photo_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    checkin.id,
                    checkin.activity_id,
                    checkin.user_id,
                    checkin.slot_id,
                    checkin.status.value,
                    checkin.checked_at.isoformat(),
                    checkin.latitude,
                    checkin.longitude,
                    checkin.photo_path,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_by_user_slot(self, user_id: str, slot_id: str) -> dict | None:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM checkins WHERE user_id = ? AND slot_id = ?",
                (user_id, slot_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_by_activity(self, activity_id: str) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM checkins WHERE activity_id = ? ORDER BY checked_at DESC",
                (activity_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_by_user(self, user_id: str) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM checkins WHERE user_id = ? ORDER BY checked_at DESC",
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def count_by_activity(self, activity_id: str) -> int:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM checkins WHERE activity_id = ? AND status = ?",
                (activity_id, CheckInStatus.CHECKED_IN.value),
            ).fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()

    def update_status(self, checkin_id: str, status: CheckInStatus, keep_checked_at: bool = False) -> None:
        conn = get_connection()
        try:
            if keep_checked_at:
                conn.execute(
                    "UPDATE checkins SET status = ? WHERE id = ?",
                    (status.value, checkin_id),
                )
            else:
                conn.execute(
                    "UPDATE checkins SET status = ?, checked_at = ? WHERE id = ?",
                    (status.value, datetime.now(timezone.utc).isoformat(), checkin_id),
                )
            conn.commit()
        finally:
            conn.close()
