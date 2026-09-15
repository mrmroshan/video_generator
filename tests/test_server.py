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


# ── Wizard endpoint tests ────────────────────────────────────────────────────

def test_niches_endpoint_returns_10_niches(client):
    res = client.get("/niches")
    assert res.status_code == 200
    niches = res.json()["niches"]
    assert len(niches) == 10
    # Each niche has required fields
    for key, niche in niches.items():
        assert "label" in niche and "icon" in niche and "color" in niche


def test_topics_unknown_niche_rejected(client):
    res = client.post("/topics", json={"niche": "astrology", "platform": "youtube"})
    assert res.status_code == 422


def test_topics_returns_8_topics(client):
    res = client.post("/topics", json={"niche": "finance", "platform": "youtube"})
    assert res.status_code == 200
    data = res.json()
    assert "topics" in data
    assert len(data["topics"]) == 8
    for t in data["topics"]:
        assert "title" in t and "hook" in t


def test_create_job_unknown_niche_rejected(client):
    res = client.post("/jobs/create", json={
        "niche": "astrology", "topic_title": "Stars and money",
        "platform": "youtube"
    })
    assert res.status_code == 422


def test_create_job_empty_topic_rejected(client):
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "  ",
        "platform": "youtube"
    })
    assert res.status_code == 422


def test_create_job_returns_job_id(client):
    res = client.post("/jobs/create", json={
        "niche": "finance",
        "topic_title": "Test topic for wizard",
        "platform": "youtube"
    })
    assert res.status_code == 200
    data = res.json()
    assert "job_id" in data
    assert len(data["job_id"]) == 36  # UUID


def test_job_progress_endpoint(client, tmp_db):
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("test", "youtube")
    job["progress_phase"] = "generating_script"
    job["progress_detail"] = "Writing..."
    tmp_db.save_job(job)
    res = client.get(f"/jobs/{job['job_id']}/progress")
    assert res.status_code == 200
    data = res.json()
    assert data["progress_phase"] == "generating_script"
    assert data["ready"] == False
    assert data["failed"] == False


# ── Platform validation tests ─────────────────────────────────────────────────

def test_topics_unknown_platform_rejected(client):
    """POST /topics with unknown platform returns 422."""
    res = client.post("/topics", json={"niche": "finance", "platform": "snapchat"})
    assert res.status_code == 422


def test_topics_all_four_platforms_accepted(client):
    """All 4 platforms (youtube, tiktok, instagram, facebook) are accepted by /topics."""
    for platform in ["youtube", "tiktok", "instagram", "facebook"]:
        res = client.post("/topics", json={"niche": "finance", "platform": platform})
        assert res.status_code == 200, f"Platform '{platform}' was rejected: {res.text}"
        assert len(res.json()["topics"]) == 8


def test_create_job_unknown_platform_rejected(client):
    """POST /jobs/create with unknown platform returns 422."""
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "test", "platform": "snapchat"
    })
    assert res.status_code == 422


def test_create_job_instagram_platform_accepted(client):
    """POST /jobs/create with platform=instagram returns a job_id."""
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "Instagram test topic",
        "platform": "instagram"
    })
    assert res.status_code == 200
    assert "job_id" in res.json()


def test_create_job_facebook_platform_accepted(client):
    """POST /jobs/create with platform=facebook returns a job_id."""
    res = client.post("/jobs/create", json={
        "niche": "marketing", "topic_title": "Facebook test topic",
        "platform": "facebook"
    })
    assert res.status_code == 200
    assert "job_id" in res.json()
