import os
import json
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone

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
        # Migration: add formats column if it doesn't exist yet (safe on existing DBs)
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN formats TEXT NOT NULL DEFAULT '[]'")
        except Exception:
            pass  # column already exists — ignore
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id  TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                niche       TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                platforms   TEXT NOT NULL DEFAULT '["tiktok","instagram","youtube","facebook"]',
                formats     TEXT NOT NULL DEFAULT '[]',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        # Migration: add formats column to projects if it doesn't exist yet
        try:
            conn.execute("ALTER TABLE projects ADD COLUMN formats TEXT NOT NULL DEFAULT '[]'")
        except Exception:
            pass  # column already exists — ignore
        conn.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                topic_id      TEXT PRIMARY KEY,
                project_id    TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                title         TEXT NOT NULL,
                hook          TEXT NOT NULL DEFAULT '',
                why_trending  TEXT NOT NULL DEFAULT '',
                status        TEXT NOT NULL DEFAULT 'queued',
                job_id        TEXT,
                position      INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            )
        """)
        # Index for fast per-project topic listing
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_topics_project
            ON topics(project_id, position)
        """)
    print(f"DB initialized at {DB_PATH}")


# ── Jobs ──────────────────────────────────────────────────────────────

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
    allowed = {"pending", "generating_assets", "in_review", "draft", "approved", "rendering", "distributing", "done", "failed"}
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
        print(f"  [WARN] update_progress: job {job_id} not found — skipping")
        return
    job["progress_phase"]      = phase
    job["progress_detail"]     = detail
    job["progress_updated_at"] = datetime.now(timezone.utc).isoformat()
    save_job(job)


def list_jobs(status: str = None) -> list:
    with get_connection() as conn:
        if status:
            rows = conn.execute("SELECT blueprint FROM jobs WHERE status = ?", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT blueprint FROM jobs ORDER BY created_at DESC").fetchall()
    return [json.loads(r["blueprint"]) for r in rows]


# ── Projects ──────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_project(name: str, niche: str, description: str = "",
                   platforms: list = None) -> dict:
    project = {
        "project_id":  str(uuid.uuid4()),
        "name":        name.strip(),
        "niche":       niche,
        "description": description.strip(),
        "platforms":   platforms or ["tiktok", "instagram", "youtube", "facebook"],
        "created_at":  _now(),
        "updated_at":  _now(),
    }
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO projects
               (project_id, name, niche, description, platforms, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                project["project_id"], project["name"], project["niche"],
                project["description"], json.dumps(project["platforms"]),
                project["created_at"], project["updated_at"],
            ),
        )
    return project


def load_project(project_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
    if not row:
        return None
    return _project_row(row)


def list_projects() -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC"
        ).fetchall()
    return [_project_row(r) for r in rows]


def _project_row(row) -> dict:
    d = dict(row)
    d["platforms"] = json.loads(d.get("platforms", "[]"))
    return d


def delete_project(project_id: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))


# ── Topics ────────────────────────────────────────────────────────────

TOPIC_STATUSES = {"queued", "in_progress", "published", "archived"}


def add_topics(project_id: str, topics: list[dict]) -> list[dict]:
    """Bulk-insert topics for a project. topics = [{title, hook, why_trending}, ...]"""
    with get_connection() as conn:
        # Get current max position
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) as max_pos FROM topics WHERE project_id = ?",
            (project_id,)
        ).fetchone()
        pos = (row["max_pos"] or -1) + 1

        inserted = []
        now = _now()
        for t in topics:
            topic_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO topics
                   (topic_id, project_id, title, hook, why_trending,
                    status, job_id, position, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'queued', NULL, ?, ?, ?)""",
                (
                    topic_id, project_id,
                    t.get("title", "").strip(),
                    t.get("hook", "").strip(),
                    t.get("why_trending", "").strip(),
                    pos, now, now,
                ),
            )
            inserted.append({
                "topic_id":     topic_id,
                "project_id":   project_id,
                "title":        t.get("title", "").strip(),
                "hook":         t.get("hook", "").strip(),
                "why_trending": t.get("why_trending", "").strip(),
                "status":       "queued",
                "job_id":       None,
                "position":     pos,
                "created_at":   now,
                "updated_at":   now,
            })
            pos += 1
    return inserted


def list_topics(project_id: str, status: str = None) -> list:
    with get_connection() as conn:
        if status:
            rows = conn.execute(
                """SELECT * FROM topics WHERE project_id = ? AND status = ?
                   ORDER BY position ASC""",
                (project_id, status)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM topics WHERE project_id = ? ORDER BY position ASC",
                (project_id,)
            ).fetchall()
    return [dict(r) for r in rows]


def update_topic_status(topic_id: str, status: str, job_id: str = None) -> dict | None:
    if status not in TOPIC_STATUSES:
        raise ValueError(f"Invalid topic status: {status}. Choose from {TOPIC_STATUSES}")
    now = _now()
    with get_connection() as conn:
        if job_id is not None:
            conn.execute(
                "UPDATE topics SET status = ?, job_id = ?, updated_at = ? WHERE topic_id = ?",
                (status, job_id, now, topic_id)
            )
        else:
            conn.execute(
                "UPDATE topics SET status = ?, updated_at = ? WHERE topic_id = ?",
                (status, now, topic_id)
            )
        row = conn.execute("SELECT * FROM topics WHERE topic_id = ?", (topic_id,)).fetchone()
    return dict(row) if row else None


def delete_topic(topic_id: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM topics WHERE topic_id = ?", (topic_id,))


def get_project_stats(project_id: str) -> dict:
    """Return topic counts per status for a project."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT status, COUNT(*) as count
               FROM topics WHERE project_id = ?
               GROUP BY status""",
            (project_id,)
        ).fetchall()
    counts = {r["status"]: r["count"] for r in rows}
    total = sum(counts.values())
    return {
        "total":       total,
        "queued":      counts.get("queued", 0),
        "in_progress": counts.get("in_progress", 0),
        "published":   counts.get("published", 0),
        "archived":    counts.get("archived", 0),
    }
