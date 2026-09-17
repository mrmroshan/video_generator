"""
Sprint 3 wizard integration tests.
Tests _run_wizard_pipeline, update_progress, and wizard endpoint edge cases.
"""
import pytest
from unittest.mock import patch


# ── progress endpoint edge cases ─────────────────────────────────────────────

def test_wizard_job_progress_not_found_returns_404(client):
    """GET /jobs/{nonexistent}/progress must return 404."""
    res = client.get("/jobs/nonexistent-uuid/progress")
    assert res.status_code == 404


def test_wizard_job_progress_shows_ready_when_in_review(client, tmp_db):
    """status=in_review → ready=True, failed=False."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("test", "youtube")
    job["status"] = "in_review"
    job["progress_phase"] = "ready_for_review"
    tmp_db.save_job(job)
    res = client.get(f"/jobs/{job['job_id']}/progress")
    assert res.status_code == 200
    data = res.json()
    assert data["ready"] is True
    assert data["failed"] is False


def test_wizard_job_progress_shows_failed_when_status_failed(client, tmp_db):
    """status=failed → failed=True, ready=False."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("test", "youtube")
    job["status"] = "failed"
    job["progress_phase"] = "failed"
    tmp_db.save_job(job)
    res = client.get(f"/jobs/{job['job_id']}/progress")
    assert res.status_code == 200
    data = res.json()
    assert data["failed"] is True
    assert data["ready"] is False


# ── update_progress edge cases ────────────────────────────────────────────────

def test_update_progress_silent_on_missing_job(tmp_db):
    """update_progress with non-existent job_id must not raise."""
    from data.db import update_progress
    try:
        update_progress("does-not-exist", "generating_script", "detail")
    except Exception as e:
        pytest.fail(f"update_progress raised unexpectedly: {e}")


def test_update_progress_unknown_phase_normalizes_to_queued(tmp_db, mock_job):
    """Unknown phase string silently resets to 'queued'."""
    from data.db import update_progress
    tmp_db.save_job(mock_job)
    update_progress(mock_job["job_id"], "not_a_real_phase", "whatever")
    loaded = tmp_db.load_job(mock_job["job_id"])
    assert loaded["progress_phase"] == "queued"


def test_update_progress_known_phase_persists(tmp_db, mock_job):
    """Valid phase and detail are persisted correctly."""
    from data.db import update_progress
    tmp_db.save_job(mock_job)
    update_progress(mock_job["job_id"], "generating_audio", "Generating 5 scenes...")
    loaded = tmp_db.load_job(mock_job["job_id"])
    assert loaded["progress_phase"]  == "generating_audio"
    assert loaded["progress_detail"] == "Generating 5 scenes..."


# ── wizard pipeline integration ────────────────────────────────────────────────

def test_wizard_pipeline_script_failure_marks_job_failed(tmp_db, mock_job):
    """If generate_script raises, job must be marked 'failed' (not stuck in 'pending')."""
    from dashboard.server import _run_wizard_pipeline

    mock_job["status"] = "pending"
    mock_job["progress_phase"] = "queued"
    tmp_db.save_job(mock_job)

    class FakePayload:
        topic_title   = "test"
        platform      = "youtube"
        platforms     = ["youtube"]
        niche         = "finance"
        caption_style = "karaoke"
        topic_hook    = ""

    with patch("orchestration.crew.generate_script",
               side_effect=RuntimeError("Claude offline")):
        _run_wizard_pipeline(mock_job["job_id"], FakePayload())

    loaded = tmp_db.load_job(mock_job["job_id"])
    assert loaded["status"] == "failed", f"Expected 'failed', got '{loaded['status']}'"
    assert loaded.get("progress_phase") == "failed"


def test_wizard_pipeline_partial_timestamps_reaches_review(tmp_db, mock_job):
    """Timestamp failures per-scene are non-fatal — pipeline still reaches in_review."""
    from dashboard.server import _run_wizard_pipeline

    for scene in mock_job["scenes"]:
        scene["audio_path"] = None  # triggers FileNotFoundError in extract_timestamps
    mock_job["status"] = "pending"
    mock_job["progress_phase"] = "queued"
    tmp_db.save_job(mock_job)

    class FakePayload:
        topic_title   = "test"
        platform      = "youtube"
        platforms     = ["youtube"]
        niche         = "finance"
        caption_style = "karaoke"
        topic_hook    = ""

    with patch("orchestration.crew.generate_script",  return_value=mock_job), \
         patch("audio.tts.generate_audio_for_job",    return_value=mock_job), \
         patch("assets.broll.fetch_broll_for_job",    return_value=mock_job):
        _run_wizard_pipeline(mock_job["job_id"], FakePayload())

    loaded = tmp_db.load_job(mock_job["job_id"])
    assert loaded["status"] == "in_review", f"Got: {loaded['status']}"
    assert loaded["progress_phase"] == "ready_for_review"


# ── approval guard ─────────────────────────────────────────────────────────────

def test_approve_blocked_when_no_scenes(client, tmp_db):
    """Approving a job with no scenes (pipeline still running) returns 409."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("test", "youtube")
    job["status"] = "in_review"
    job["scenes"] = []  # simulate mid-pipeline state
    tmp_db.save_job(job)
    res = client.post(f"/jobs/{job['job_id']}/approve")
    assert res.status_code == 409
    assert "scenes" in res.text.lower() or "pipeline" in res.text.lower()
