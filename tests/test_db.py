import pytest


def test_db_save_load_roundtrip(tmp_db, mock_job):
    """Full job dict survives save → load without data loss."""
    tmp_db.save_job(mock_job)
    loaded = tmp_db.load_job(mock_job["job_id"])
    assert loaded["job_id"] == mock_job["job_id"]
    assert loaded["status"] == mock_job["status"]
    assert len(loaded["scenes"]) == len(mock_job["scenes"])


def test_db_update_status_atomic(tmp_db, mock_job):
    """update_status changes status and persists it."""
    tmp_db.save_job(mock_job)
    tmp_db.update_status(mock_job["job_id"], "in_review")
    loaded = tmp_db.load_job(mock_job["job_id"])
    assert loaded["status"] == "in_review"


def test_db_update_status_invalid_raises(tmp_db, mock_job):
    """Invalid status raises ValueError."""
    tmp_db.save_job(mock_job)
    with pytest.raises(ValueError, match="Invalid status"):
        tmp_db.update_status(mock_job["job_id"], "launched_to_moon")


def test_db_update_status_missing_job_raises(tmp_db):
    """Updating non-existent job raises ValueError."""
    with pytest.raises(ValueError):
        tmp_db.update_status("nonexistent-id", "in_review")


def test_db_wal_mode_enabled(tmp_db):
    """WAL journal mode must be active after init."""
    conn = tmp_db.get_connection()
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal", f"Expected WAL, got {mode}"
