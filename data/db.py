import os
import json
import sqlite3
from pathlib import Path

_ROOT   = Path(__file__).parent.parent
DB_PATH = os.getenv("DB_PATH", str(_ROOT / "data" / "video_maker.db"))


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id     TEXT PRIMARY KEY,
                status     TEXT NOT NULL,
                platform   TEXT NOT NULL DEFAULT 'youtube',
                created_at TEXT NOT NULL,
                blueprint  TEXT NOT NULL
            )
        """)
    print(f"DB initialized at {DB_PATH}")


def save_job(job: dict):
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO jobs (job_id, status, platform, created_at, blueprint)
               VALUES (?, ?, ?, ?, ?)""",
            (
                job["job_id"],
                job["status"],
                job.get("platform", "youtube"),
                job.get("created_at", ""),
                json.dumps(job),
            ),
        )


def load_job(job_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT blueprint FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    if not row:
        return None
    return json.loads(row["blueprint"])


def update_status(job_id: str, status: str, extra: dict = None):
    """Update job status. Uses direct SQL UPDATE for status-only changes (atomic)."""
    allowed = {"pending", "generating_assets", "in_review", "approved", "rendering", "distributing", "done", "failed"}
    if status not in allowed:
        raise ValueError(f"Invalid status: {status}")

    if extra:
        job = load_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        job["status"] = status
        job.update(extra)
        save_job(job)
        return

    with get_connection() as conn:
        result = conn.execute(
            "UPDATE jobs SET status = ? WHERE job_id = ?",
            (status, job_id)
        )
        if result.rowcount == 0:
            raise ValueError(f"Job not found: {job_id}")
        row = conn.execute("SELECT blueprint FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row:
            blueprint = json.loads(row["blueprint"])
            blueprint["status"] = status
            conn.execute(
                "UPDATE jobs SET blueprint = ? WHERE job_id = ?",
                (json.dumps(blueprint), job_id)
            )


def update_progress(job_id: str, phase: str, detail: str = ""):
    """Record pipeline progress so the UI can show live phase status."""
    allowed_phases = {
        "queued", "generating_script", "generating_audio",
        "extracting_timestamps", "downloading_broll",
        "ready_for_review", "failed"
    }
    if phase not in allowed_phases:
        phase = "queued"
    job = load_job(job_id)
    if not job:
        return
    job["progress_phase"]      = phase
    job["progress_detail"]     = detail
    from datetime import datetime, timezone
    job["progress_updated_at"] = datetime.now(timezone.utc).isoformat()
    save_job(job)


def list_jobs(status: str = None) -> list:
    with get_connection() as conn:
        if status:
            rows = conn.execute("SELECT blueprint FROM jobs WHERE status = ?", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT blueprint FROM jobs ORDER BY created_at DESC").fetchall()
    return [json.loads(r["blueprint"]) for r in rows]
