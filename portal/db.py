"""SQLite persistence for transcript VC requests."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "demo_requests.db"


def db_path() -> str:
    return os.environ.get("AIT_DEMO_DB", str(_DEFAULT_DB))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    if own:
        conn = connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            degree_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
            created_at TEXT NOT NULL,
            decided_at TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_requests_student_degree ON requests (student_id, degree_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_revocations (
            credential_id TEXT PRIMARY KEY,
            requested_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    if own:
        conn.close()


def reset_db() -> None:
    """Drop and recreate the requests/pending_revocations tables (tests)."""
    conn = connect()
    conn.execute("DROP TABLE IF EXISTS requests")
    conn.execute("DROP TABLE IF EXISTS pending_revocations")
    init_db(conn)
    conn.close()
