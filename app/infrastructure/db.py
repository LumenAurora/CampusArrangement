from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import DATA_DIR

DB_PATH = str(DATA_DIR / "app.db")


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_db_path() -> str:
    """懒读取 DB_PATH：每次调用都从环境变量获取，便于测试通过 monkeypatch.setenv 切换数据库。

    保留与 app.config 一致的默认值（DATA_DIR/app.db），生产行为不变。
    """
    return os.environ.get("CAMPUS_DB_PATH", DB_PATH)


def get_connection() -> sqlite3.Connection:
    ensure_data_dir()
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction() -> sqlite3.Connection:
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    ensure_data_dir()
    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activities (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                signup_start TEXT NOT NULL,
                signup_end TEXT NOT NULL,
                details TEXT NOT NULL,
                signup_mode TEXT NOT NULL DEFAULT 'realtime',
                allocation_mode TEXT NOT NULL DEFAULT 'greedy',
                location TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS slots (
                id TEXT PRIMARY KEY,
                activity_id TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                capacity INTEGER NOT NULL,
                used_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS registrations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                activity_id TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                priority INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE,
                FOREIGN KEY (slot_id) REFERENCES slots(id) ON DELETE CASCADE
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_reg_user_slot_active
                ON registrations(user_id, slot_id) WHERE status NOT IN ('cancelled', 'not_assigned');

            CREATE TABLE IF NOT EXISTS schedule_results (
                id TEXT PRIMARY KEY,
                activity_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (slot_id) REFERENCES slots(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS checkins (
                id TEXT PRIMARY KEY,
                activity_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                status TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                FOREIGN KEY (activity_id) REFERENCES activities(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (slot_id) REFERENCES slots(id) ON DELETE CASCADE,
                UNIQUE (user_id, slot_id)
            );

            CREATE TABLE IF NOT EXISTS groups (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                owner_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS group_members (
                group_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                status TEXT NOT NULL DEFAULT 'pending',
                joined_at TEXT NOT NULL,
                PRIMARY KEY (group_id, user_id),
                FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        _ensure_column(conn, "activities", "signup_mode", "signup_mode TEXT NOT NULL DEFAULT 'realtime'")
        _ensure_column(conn, "activities", "allocation_mode", "allocation_mode TEXT NOT NULL DEFAULT 'greedy'")
        _ensure_column(conn, "activities", "location", "location TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "activities", "checkin_code", "checkin_code TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "activities", "checkin_mode", "checkin_mode TEXT NOT NULL DEFAULT 'manual'")
        _ensure_column(conn, "activities", "checkin_start", "checkin_start TEXT")
        _ensure_column(conn, "activities", "checkin_end", "checkin_end TEXT")
        # 新增：支持多种活动类型
        _ensure_column(conn, "activities", "activity_type", "activity_type TEXT NOT NULL DEFAULT 'time_slot'")
        _ensure_column(conn, "slots", "slot_type", "slot_type TEXT NOT NULL DEFAULT 'time_slot'")
        _ensure_column(conn, "slots", "name", "name TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "slots", "metadata", "metadata TEXT NOT NULL DEFAULT ''")
        # 使slots表中start_time和end_time允许为空
        # （注意：SQLite不支持直接修改列约束，所以我们不改变这些列的定义）
        _ensure_column(conn, "checkins", "latitude", "latitude REAL")
        _ensure_column(conn, "checkins", "longitude", "longitude REAL")
        _ensure_column(conn, "checkins", "photo_path", "photo_path TEXT NOT NULL DEFAULT ''")
        # 新增：用户审批状态
        _ensure_column(conn, "users", "status", "status TEXT NOT NULL DEFAULT 'approved'")
        # 新增：岗位层级（子岗位的 parent_slot_id）
        _ensure_column(conn, "slots", "parent_slot_id", "parent_slot_id TEXT")
        # 新增：活动小组限制
        _ensure_column(conn, "activities", "group_id", "group_id TEXT")
        # 新增：小组申请理由，方便管理端审批时参考
        _ensure_column(conn, "group_members", "reason", "reason TEXT NOT NULL DEFAULT ''")
        # 新增：意愿点模式（用户对每个志愿分配的点数）
        _ensure_column(conn, "registrations", "points", "points INTEGER NOT NULL DEFAULT 0")
        # 新增：人工提前结束签到（与 checkin_end 时间独立，可逆）
        _ensure_column(conn, "activities", "checkin_closed", "checkin_closed INTEGER NOT NULL DEFAULT 0")
        # 新增：用户头像与通知偏好
        _ensure_column(conn, "users", "avatar_path", "avatar_path TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "users", "notification_mode", "notification_mode TEXT NOT NULL DEFAULT 'in_app'")
        # 新增：允许兼报多个时段/岗位（0=不允许，1=允许）
        _ensure_column(conn, "activities", "allow_multiple_slots", "allow_multiple_slots INTEGER NOT NULL DEFAULT 0")
        # 改造报名唯一索引：从 (user_id, activity_id) 改为 (user_id, slot_id)
        # 允许兼报时同一用户可报同一活动的不同 slot，但同一 slot 不可重复报
        _migrate_registration_unique_index(conn)
        # 迁移旧 activity_type 到新模式：scheduling/topic_selection/course_selection/seat_reservation/custom → time_slot/non_time_slot
        _migrate_activity_type(conn)
        conn.commit()
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    # 使用白名单验证表名，防止SQL注入
    allowed_tables = {"users", "activities", "slots", "registrations", "schedule_results", "checkins", "groups", "group_members"}
    if table not in allowed_tables:
        raise ValueError(f"不允许的表名: {table}")
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _migrate_activity_type(conn: sqlite3.Connection) -> None:
    """将旧的 activity_type 值迁移为新的两种模式：time_slot / non_time_slot"""
    old_to_new = {
        "scheduling": "time_slot",
        "seat_reservation": "time_slot",
        "topic_selection": "non_time_slot",
        "course_selection": "non_time_slot",
        "custom": "non_time_slot",
    }
    for old_val, new_val in old_to_new.items():
        conn.execute(
            "UPDATE activities SET activity_type = ? WHERE activity_type = ?",
            (new_val, old_val),
        )


def _migrate_registration_unique_index(conn: sqlite3.Connection) -> None:
    """将报名唯一索引从 (user_id, activity_id) 改为 (user_id, slot_id)。

    旧索引阻止同一用户在同一活动下报多个 slot（即阻止兼报）；
    新索引只阻止同一用户重复报同一 slot，允许兼报不同 slot。
    对于不允许兼报的活动，由应用层 RegistrationService.register 做检查。
    """
    # 检查旧索引是否存在，存在则删除
    indexes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='registrations'"
    ).fetchall()
    index_names = {row["name"] for row in indexes}
    if "idx_reg_user_activity_active" in index_names:
        conn.execute("DROP INDEX IF EXISTS idx_reg_user_activity_active")
    if "idx_reg_user_slot_active" not in index_names:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_reg_user_slot_active "
            "ON registrations(user_id, slot_id) WHERE status NOT IN ('cancelled', 'not_assigned')"
        )
