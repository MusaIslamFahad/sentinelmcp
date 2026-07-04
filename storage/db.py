"""
SQLite storage for SentinelMCP.

Deliberately simple (stdlib sqlite3, no ORM) so the project has zero extra
infra to run — one file, `sentinel.db`, created on first use. Swap in
Postgres later by replacing this module if you need concurrent writers.
"""
import sqlite3
import json
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    target_name TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS results (
    result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    test_case_id TEXT NOT NULL,
    category TEXT NOT NULL,
    prompt TEXT NOT NULL,
    target_response TEXT NOT NULL,
    attack_succeeded INTEGER NOT NULL,
    severity INTEGER NOT NULL,
    judge_reasoning TEXT NOT NULL,
    tool_called TEXT,
    error TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_results_run_id ON results(run_id);
"""


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # lets the dashboard read while a run is writing
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def create_run(target_name: str, notes: str = "") -> str:
    run_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO runs (run_id, started_at, target_name, notes) VALUES (?, ?, ?, ?)",
            (run_id, datetime.now(timezone.utc).isoformat(), target_name, notes),
        )
    return run_id


def finish_run(run_id: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = ? WHERE run_id = ?",
            (datetime.now(timezone.utc).isoformat(), run_id),
        )


def log_result(
    run_id: str,
    test_case_id: str,
    category: str,
    prompt: str,
    target_response: str,
    attack_succeeded: bool,
    severity: int,
    judge_reasoning: str,
    tool_called: str | None = None,
    error: str | None = None,
) -> str:
    """error should be set (non-None) when this row represents a test case that
    failed to execute (e.g. API call exhausted retries) rather than a genuine
    judged verdict. Callers/reporting should treat error rows as "not tested",
    not as evidence the target behaved safely."""
    result_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO results
               (result_id, run_id, test_case_id, category, prompt, target_response,
                attack_succeeded, severity, judge_reasoning, tool_called, error, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result_id, run_id, test_case_id, category, prompt, target_response,
                int(attack_succeeded), severity, judge_reasoning, tool_called, error,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return result_id


def get_run_results(run_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM results WHERE run_id = ?", (run_id,)).fetchall()
        return [dict(r) for r in rows]


def get_all_runs() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_run(run_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None
