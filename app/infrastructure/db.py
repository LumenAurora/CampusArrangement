from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import DATA_DIR, DB_PATH


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_data_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
                allocation_mode TEXT NOT NULL DEFAULT 'greedy'
            );

            CREATE TABLE IF NOT EXISTS slots (
                id TEXT PRIMARY KEY,
                activity_id TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                capacity INTEGER NOT NULL,
                used_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS registrations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                activity_id TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                priority INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS schedule_results (
                id TEXT PRIMARY KEY,
                activity_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                slot_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        _ensure_column(conn, "activities", "signup_mode", "signup_mode TEXT NOT NULL DEFAULT 'realtime'")
        _ensure_column(conn, "activities", "allocation_mode", "allocation_mode TEXT NOT NULL DEFAULT 'greedy'")
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    # 使用白名单验证表名，防止SQL注入
    allowed_tables = {"users", "activities", "slots", "registrations", "schedule_results"}
    if table not in allowed_tables:
        raise ValueError(f"不允许的表名: {table}")
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
