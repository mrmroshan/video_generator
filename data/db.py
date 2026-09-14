"""
DATABASE — SQLite job store
Tracks all jobs and their status transitions.
"""
import os
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).parent
DB_PATH = os.getenv("DB_PATH", str(_HERE / "video_maker.db"))


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist"""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id      TEXT PRIMARY KEY,
                status      TEXT NOT NULL DEFAULT 'pending',
                platform    TEXT NOT NULL,
                title       TEXT,
                blueprint   TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                approved_at TEXT,
                output_path TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)
        """)
    print(f"DB initialized at {DB_PATH}")


def save_job(job: dict):
    """Insert or replace a job record"""
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO jobs
              (job_id, status, platform, title, blueprint, created_at, approved_at, output_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job["job_id"],
            job["status"],
            job["platform"],
            job.get("title"),
            json.dumps(job),
            job["created_at"],
            job.get("approved_at"),
            job.get("output_path"),
        ))


def load_job(job_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT blueprint FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    return json.loads(row["blueprint"]) if row else None


def update_status(job_id: str, status: str, extra: dict = None):
    """Update job status. Uses direct SQL UPDATE for status-only changes (atomic)."""
    allowed = {"pending", "generating_assets", "in_review", "approved", "rendering", "distributing", "done", "failed"}
    if status not in allowed:
        raise ValueError(f"Invalid status: {status}")

    if extra:
        # Extra fields require loading the full blueprint
        job = load_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        job["status"] = status
        job.update(extra)
        save_job(job)
        return

    # Status-only: single atomic SQL UPDATE + blueprint sync
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE jobs SET status = ? WHERE job_id = ?",
            (status, job_id)
        )
        if result.rowcount == 0:
            raise ValueError(f"Job not found: {job_id}")
        # Keep blueprint JSON consistent with status column
        row = conn.execute("SELECT blueprint FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row:
            blueprint = json.loads(row["blueprint"])
            blueprint["status"] = status
            conn.execute(
                "UPDATE jobs SET blueprint = ? WHERE job_id = ?",
                (json.dumps(blueprint), job_id)
            )


def list_jobs(status: str = None) -> list:
    with get_connection() as conn:
        if status:
            rows = conn.execute("SELECT blueprint FROM jobs WHERE status = ?", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT blueprint FROM jobs ORDER BY created_at DESC").fetchall()
    return [json.loads(r["blueprint"]) for r in rows]
