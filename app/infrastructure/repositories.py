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
    UserStatus,
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
            rows = conn.execute("SELECT id, username, role, status, created_at FROM users ORDER BY created_at DESC").fetchall()
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
            status = user.status.value if hasattr(user.status, 'value') else (user.status or 'approved')
            conn.execute(
                "INSERT INTO users (id, username, role, password_hash, created_at, status) VALUES (?, ?, ?, ?, ?, ?)",
                (user.id, user.username, user.role.value, password_hash, datetime.now(timezone.utc).isoformat(), status),
            )
            conn.commit()
        finally:
            conn.close()

    def update_status(self, user_id: str, status: UserStatus) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE users SET status = ? WHERE id = ?",
                (status.value, user_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_by_status(self, status: UserStatus) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT id, username, role, status, created_at FROM users WHERE status = ? ORDER BY created_at DESC",
                (status.value,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def update_password(self, user_id: str, password_hash: str) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id),
            )
            conn.commit()
        finally:
            conn.close()


class ActivityRepository:
    def create(self, activity: Activity) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO activities (id, name, status, owner_id, signup_start, signup_end, details, signup_mode, allocation_mode, location, activity_type, checkin_code, checkin_mode, checkin_start, checkin_end, group_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    activity.activity_type.value,
                    activity.checkin_code,
                    activity.checkin_mode.value,
                    activity.checkin_start.isoformat() if activity.checkin_start else None,
                    activity.checkin_end.isoformat() if activity.checkin_end else None,
                    activity.group_id,
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
            start_time_str = slot.start_time.isoformat() if slot.start_time else None
            end_time_str = slot.end_time.isoformat() if slot.end_time else None
            conn.execute(
                "INSERT INTO slots (id, activity_id, slot_type, name, start_time, end_time, capacity, used_count, metadata, parent_slot_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    slot.id,
                    slot.activity_id,
                    slot.slot_type.value,
                    slot.name,
                    start_time_str,
                    end_time_str,
                    slot.capacity,
                    slot.used_count,
                    slot.metadata,
                    slot.parent_slot_id,
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
            # 排序：先时段按时间，其他按名称；子岗位紧跟父时段
            rows = conn.execute("""
                SELECT * FROM slots 
                WHERE activity_id = ? 
                ORDER BY 
                    CASE WHEN parent_slot_id IS NULL THEN 0 ELSE 1 END,
                    CASE WHEN slot_type = 'time_slot' AND parent_slot_id IS NULL THEN start_time ELSE name END,
                    parent_slot_id,
                    name
                """, (activity_id,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            if own:
                conn.close()

    def list_positions(self, parent_slot_id: str) -> list[dict]:
        """获取某时段下的所有子岗位"""
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM slots WHERE parent_slot_id = ? ORDER BY name",
                (parent_slot_id,),
            ).fetchall()
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
        from app.domain.models import SlotType
        slots: list[TimeSlot] = []
        for row in rows:
            # 兼容旧数据
            slot_type = SlotType(row.get("slot_type", "time_slot"))
            name = row.get("name", "")
            metadata = row.get("metadata", "")
            parent_slot_id = row.get("parent_slot_id")

            start_time = None
            end_time = None
            if row.get("start_time"):
                try:
                    start_time = datetime.fromisoformat(row["start_time"])
                except (ValueError, TypeError):
                    pass
            if row.get("end_time"):
                try:
                    end_time = datetime.fromisoformat(row["end_time"])
                except (ValueError, TypeError):
                    pass

            slots.append(
                TimeSlot(
                    id=row["id"],
                    activity_id=row["activity_id"],
                    slot_type=slot_type,
                    name=name,
                    start_time=start_time,
                    end_time=end_time,
                    capacity=row["capacity"],
                    used_count=row["used_count"],
                    parent_slot_id=parent_slot_id,
                    metadata=metadata,
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

    def reset_for_rescheduling(self, activity_id: str, conn: sqlite3.Connection | None = None) -> None:
        """将 ASSIGNED / NOT_ASSIGNED 状态的报名重置为 PENDING，以便重新排班。
        不触碰 CONFIRMED 等已确认状态。"""
        reset_statuses = (RegistrationStatus.NOT_ASSIGNED.value, RegistrationStatus.ASSIGNED.value)
        if conn is not None:
            conn.execute(
                "UPDATE registrations SET status = ? WHERE activity_id = ? AND status IN (?, ?)",
                (RegistrationStatus.PENDING.value, activity_id, *reset_statuses),
            )
        else:
            with transaction() as c:
                c.execute(
                    "UPDATE registrations SET status = ? WHERE activity_id = ? AND status IN (?, ?)",
                    (RegistrationStatus.PENDING.value, activity_id, *reset_statuses),
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


class GroupRepository:
    """小组数据访问"""

    def create(self, group) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO groups (id, name, description, owner_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (group.id, group.name, group.description, group.owner_id, group.created_at.isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, group_id: str) -> dict | None:
        conn = get_connection()
        try:
            row = conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_all(self) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute("SELECT * FROM groups ORDER BY created_at DESC").fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_by_owner(self, owner_id: str) -> list[dict]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM groups WHERE owner_id = ? ORDER BY created_at DESC", (owner_id,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def list_by_user(self, user_id: str) -> list[dict]:
        """获取用户所属的小组（已审批通过的）"""
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT g.* FROM groups g
                   INNER JOIN group_members gm ON g.id = gm.group_id
                   WHERE gm.user_id = ? AND gm.status = 'approved'""",
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def delete(self, group_id: str) -> bool:
        conn = get_connection()
        try:
            cursor = conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── 成员管理 ────────────────────────────────────────────

    def add_member(self, group_id: str, user_id: str, role: str = "member", status: str = "pending", reason: str = "") -> None:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO group_members (group_id, user_id, role, status, joined_at, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (group_id, user_id, role, status, datetime.now(timezone.utc).isoformat(), reason),
            )
            conn.commit()
        finally:
            conn.close()

    def update_member_status(self, group_id: str, user_id: str, status: str) -> None:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE group_members SET status = ? WHERE group_id = ? AND user_id = ?",
                (status, group_id, user_id),
            )
            conn.commit()
        finally:
            conn.close()

    def remove_member(self, group_id: str, user_id: str) -> bool:
        conn = get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_members(self, group_id: str) -> list[dict]:
        """获取小组成员（含用户信息）"""
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT gm.*, u.username FROM group_members gm
                   INNER JOIN users u ON gm.user_id = u.id
                   WHERE gm.group_id = ?
                   ORDER BY gm.status, gm.joined_at""",
                (group_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_member(self, group_id: str, user_id: str) -> dict | None:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_pending_applications(self, owner_id: str) -> list[dict]:
        """管理员查看自己小组中待审批的申请"""
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT gm.*, g.name as group_name, u.username
                   FROM group_members gm
                   INNER JOIN groups g ON gm.group_id = g.id
                   INNER JOIN users u ON gm.user_id = u.id
                   WHERE g.owner_id = ? AND gm.status = 'pending'
                   ORDER BY gm.joined_at""",
                (owner_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def is_member(self, group_id: str, user_id: str) -> bool:
        """检查用户是否为已审批的小组成员"""
        row = self.get_member(group_id, user_id)
        return row is not None and row.get("status") == "approved"
