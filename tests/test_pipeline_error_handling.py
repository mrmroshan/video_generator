import pytest
from unittest.mock import patch


def test_pipeline_sets_failed_on_tts_error(tmp_db, mock_job, monkeypatch):
    """If TTS fails, job must be marked 'failed', not stuck in 'generating_assets'."""
    monkeypatch.setenv("MOCK_APIS", "false")
    import importlib
    import pipeline
    importlib.reload(pipeline)

    with patch("pipeline.generate_script", return_value=mock_job), \
         patch("pipeline.generate_audio_for_job", side_effect=RuntimeError("ElevenLabs 429")):
        with pytest.raises(RuntimeError):
            pipeline.run_pipeline("test topic", "youtube")

    loaded = tmp_db.load_job(mock_job["job_id"])
    assert loaded["status"] == "failed", f"Expected 'failed', got '{loaded['status']}'"


def test_render_requires_approved_status(mock_job):
    """render_job must raise for non-approved jobs."""
    from renderer.render import render_job
    for status in ["pending", "in_review", "generating_assets"]:
        mock_job["status"] = status
        with pytest.raises((PermissionError, ValueError)):
            render_job(mock_job)
