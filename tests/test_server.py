import pytest


def test_approve_blocks_done_job(client, tmp_db):
    """Approving a done job must return 409."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("t", "youtube")
    job["status"] = "done"
    tmp_db.save_job(job)
    res = client.post(f"/jobs/{job['job_id']}/approve")
    assert res.status_code == 409


def test_approve_blocks_rendering_job(client, tmp_db):
    """Approving a rendering job must return 409."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("t", "youtube")
    job["status"] = "rendering"
    tmp_db.save_job(job)
    res = client.post(f"/jobs/{job['job_id']}/approve")
    assert res.status_code == 409


def test_search_broll_empty_query_rejected(client, tmp_db):
    """Empty search query must return 422."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("t", "youtube")
    job["status"] = "in_review"
    tmp_db.save_job(job)
    res = client.get(f"/jobs/{job['job_id']}/scenes/scene_01/search-broll?q=")
    assert res.status_code == 422


def test_pick_broll_ssrf_guard(client, tmp_db):
    """SSRF: non-Pexels URLs must be rejected with 422."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("t", "youtube")
    job["status"] = "in_review"
    tmp_db.save_job(job)
    res = client.post(
        f"/jobs/{job['job_id']}/scenes/scene_01/pick-broll",
        json={"video_id": 1, "download_url": "http://169.254.169.254/metadata",
              "pexels_url": "http://169.254.169.254/metadata"}
    )
    assert res.status_code == 422


def test_caption_styles_endpoint(client):
    """GET /caption-styles returns at least 7 styles."""
    res = client.get("/caption-styles")
    assert res.status_code == 200
    assert len(res.json()["styles"]) >= 7


def test_platforms_endpoint(client):
    """GET /platforms returns exactly 4 platforms."""
    res = client.get("/platforms")
    assert res.status_code == 200
    assert set(res.json()["platforms"]) == {"youtube", "tiktok", "instagram", "facebook"}


def test_render_status_endpoint(client, tmp_db):
    """GET /render-status returns status for known job."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("t", "youtube")
    job["status"] = "approved"
    tmp_db.save_job(job)
    res = client.get(f"/jobs/{job['job_id']}/render-status")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert data["done"] is False
    assert data["failed"] is False


def test_patch_scene_updates_voiceover(client, tmp_db):
    """PATCH /scenes updates voiceover_text."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("test", "youtube")
    job["status"] = "in_review"
    tmp_db.save_job(job)
    sid = job["scenes"][0]["scene_id"]
    res = client.patch(
        f"/jobs/{job['job_id']}/scenes/{sid}",
        json={"voiceover_text": "Updated text here"}
    )
    assert res.status_code == 200
    updated = next(s for s in res.json()["scenes"] if s["scene_id"] == sid)
    assert updated["voiceover_text"] == "Updated text here"


def test_set_caption_style_unknown_rejected(client, tmp_db):
    """PATCH caption-style with unknown style returns 422."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("test", "youtube")
    tmp_db.save_job(job)
    res = client.patch(
        f"/jobs/{job['job_id']}/caption-style",
        json={"caption_style": "neon_disco"}
    )
    assert res.status_code == 422


def test_caption_text_endpoint_returns_voiceover_fallback(client, tmp_db):
    """GET /caption-text without timestamps returns voiceover_text as fallback."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("test", "youtube")
    tmp_db.save_job(job)
    sid = job["scenes"][0]["scene_id"]
    res = client.get(f"/jobs/{job['job_id']}/scenes/{sid}/caption-text")
    assert res.status_code == 200
    data = res.json()
    assert "text" in data
    assert data["has_timestamps"] == False
    assert len(data["text"]) > 0


def test_caption_text_endpoint_is_edited_false_initially(client, tmp_db):
    """GET /caption-text returns is_edited=False before any edits."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("test", "youtube")
    tmp_db.save_job(job)
    sid = job["scenes"][0]["scene_id"]
    res = client.get(f"/jobs/{job['job_id']}/scenes/{sid}/caption-text")
    assert res.json()["is_edited"] == False
