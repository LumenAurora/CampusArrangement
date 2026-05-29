from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from app.domain.models import Activity, ActivityStatus, Registration, RegistrationStatus, ScheduleResult, TimeSlot
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
                "INSERT INTO activities (id, name, status, owner_id, signup_start, signup_end, details, signup_mode, allocation_mode) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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

    def count_all(self) -> int:
        conn = get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) AS total FROM activities").fetchone()
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


class TimeSlotRepository:
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

    def list_by_activity(self, activity_id: str) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute("SELECT * FROM slots WHERE activity_id = ?", (activity_id,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def count_all(self) -> int:
        conn = get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) AS total FROM slots").fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()

    def lock_slot(self, slot_id: str) -> bool:
        with transaction() as conn:
            row = conn.execute("SELECT capacity, used_count FROM slots WHERE id = ?", (slot_id,)).fetchone()
            if not row:
                return False
            if row["used_count"] >= row["capacity"]:
                return False
            conn.execute("UPDATE slots SET used_count = used_count + 1 WHERE id = ?", (slot_id,))
            return True

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
    def create(self, registration: Registration) -> None:
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
            conn.commit()
        finally:
            conn.close()

    def list_pending(self, activity_id: str) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM registrations WHERE activity_id = ? AND status = ? ORDER BY created_at ASC",
                (activity_id, RegistrationStatus.PENDING.value),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def count_all(self) -> int:
        conn = get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) AS total FROM registrations").fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()

    def count_by_user(self, user_id: str) -> int:
        conn = get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) AS total FROM registrations WHERE user_id = ?", (user_id,)).fetchone()
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
    def create(self, result: ScheduleResult) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO schedule_results (id, activity_id, user_id, slot_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (result.id, result.activity_id, result.user_id, result.slot_id, result.created_at.isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def clear_for_activity(self, activity_id: str) -> None:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM schedule_results WHERE activity_id = ?", (activity_id,))
            conn.commit()
        finally:
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
