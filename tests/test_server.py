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
    """GET /platforms returns the known platform brands + groups structure."""
    res = client.get("/platforms")
    assert res.status_code == 200
    data = res.json()
    platforms = set(data["platforms"])
    # Must include the new format keys (subset check — safe for future additions)
    assert {"youtube_shorts", "tiktok", "instagram_reels", "facebook_reels"}.issubset(platforms)
    # Must also include backward-compat alias keys
    assert {"youtube", "instagram", "facebook"}.issubset(platforms)
    # Must include the grouped structure for the UI picker
    assert "groups" in data
    groups = data["groups"]
    assert set(groups.keys()) == {"tiktok", "youtube", "instagram", "facebook"}
    # Each group has label, icon, and formats list
    for brand, grp in groups.items():
        assert "label" in grp and "icon" in grp and "formats" in grp
        for fmt in grp["formats"]:
            assert "key" in fmt and "label" in fmt and "available" in fmt and "default" in fmt


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
        "platforms": ["youtube"]
    })
    assert res.status_code == 422


def test_create_job_empty_topic_rejected(client):
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "  ",
        "platforms": ["youtube"]
    })
    assert res.status_code == 422


def test_create_job_returns_job_id(client):
    res = client.post("/jobs/create", json={
        "niche": "finance",
        "topic_title": "Test topic for wizard",
        "platforms": ["youtube"]
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
        "niche": "finance", "topic_title": "test", "platforms": ["snapchat"]
    })
    assert res.status_code == 422


def test_create_job_instagram_platform_accepted(client):
    """POST /jobs/create with platforms=[instagram] returns a job_id."""
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "Instagram test topic",
        "platforms": ["instagram"]
    })
    assert res.status_code == 200
    assert "job_id" in res.json()


def test_create_job_facebook_platform_accepted(client):
    """POST /jobs/create with platforms=[facebook] returns a job_id."""
    res = client.post("/jobs/create", json={
        "niche": "marketing", "topic_title": "Facebook test topic",
        "platforms": ["facebook"]
    })
    assert res.status_code == 200
    assert "job_id" in res.json()


def test_create_job_multi_platform_accepted(client):
    """POST /jobs/create with all 4 platforms returns a job_id."""
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "Multi-platform test",
        "platforms": ["tiktok", "instagram", "youtube", "facebook"]
    })
    assert res.status_code == 200
    data = res.json()
    assert "job_id" in data


def test_create_job_empty_platforms_rejected(client):
    """POST /jobs/create with empty platforms list returns 422."""
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "test", "platforms": []
    })
    assert res.status_code == 422


# ── Draft save tests ─────────────────────────────────────────────────────────

def test_save_draft_from_in_review(client, tmp_path):
    """POST /save-draft on in_review job sets status=draft."""
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "Draft test", "platforms": ["youtube"]
    })
    job_id = res.json()["job_id"]
    # Manually push to in_review
    from data.db import load_job, save_job
    j = load_job(job_id); j["status"] = "in_review"; j["scenes"] = [{"scene_id": "s1"}]; save_job(j)

    res = client.post(f"/jobs/{job_id}/save-draft")
    assert res.status_code == 200
    assert res.json()["status"] == "draft"
    assert "draft_saved_at" in res.json()


def test_save_draft_idempotent(client):
    """Calling save-draft twice on a draft job is idempotent."""
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "Idempotent draft", "platforms": ["tiktok"]
    })
    job_id = res.json()["job_id"]
    from data.db import load_job, save_job
    j = load_job(job_id); j["status"] = "draft"; j["scenes"] = [{"scene_id": "s1"}]; save_job(j)

    r1 = client.post(f"/jobs/{job_id}/save-draft")
    r2 = client.post(f"/jobs/{job_id}/save-draft")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["status"] == "draft"


def test_save_draft_blocked_on_approved(client):
    """POST /save-draft on approved job returns 409."""
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "Approved draft test", "platforms": ["youtube"]
    })
    job_id = res.json()["job_id"]
    from data.db import load_job, save_job
    j = load_job(job_id); j["status"] = "approved"; j["scenes"] = [{"scene_id": "s1"}]; save_job(j)

    res = client.post(f"/jobs/{job_id}/save-draft")
    assert res.status_code == 409


def test_approve_from_draft(client):
    """POST /approve on draft job succeeds."""
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "Approve from draft", "platforms": ["youtube"]
    })
    job_id = res.json()["job_id"]
    from data.db import load_job, save_job
    j = load_job(job_id)
    j["status"] = "draft"; j["scenes"] = [{"scene_id": "s1"}]
    j["progress_phase"] = "ready_for_review"
    save_job(j)

    res = client.post(f"/jobs/{job_id}/approve")
    assert res.status_code == 200
    assert res.json()["status"] == "approved"


def test_patch_scene_preserves_draft_status(client):
    """Editing a scene on a draft job keeps status=draft (not reset to in_review)."""
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "Draft scene edit", "platforms": ["youtube"]
    })
    job_id = res.json()["job_id"]
    from data.db import load_job, save_job
    j = load_job(job_id)
    j["status"] = "draft"
    j["scenes"] = [{"scene_id": "scene_01", "voiceover_text": "original"}]
    save_job(j)

    res = client.patch(f"/jobs/{job_id}/scenes/scene_01",
                       json={"voiceover_text": "updated text"})
    assert res.status_code == 200
    assert res.json()["status"] == "draft", "Status must remain draft after scene edit"


# ── Platform export tests ─────────────────────────────────────────────────────

def test_export_single_platform_mock(client, tmp_db, tmp_path, monkeypatch):
    """POST /export/{platform} on a rendered job returns 200 with path and size_kb."""
    from orchestration.crew import _mock_blueprint
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    job = _mock_blueprint("export test", "youtube")
    job["status"] = "done"
    job["output_path"] = str(tmp_path / "jobs" / job["job_id"] / "output.mp4")
    tmp_db.save_job(job)
    res = client.post(f"/jobs/{job['job_id']}/export/youtube")
    assert res.status_code == 200
    data = res.json()
    assert data["platform"] == "youtube"
    assert "path" in data
    assert "size_kb" in data


def test_export_unknown_platform_rejected(client, tmp_db):
    """POST /export/{platform} with unknown platform name returns 422."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("export reject test", "youtube")
    job["status"] = "done"
    tmp_db.save_job(job)
    res = client.post(f"/jobs/{job['job_id']}/export/snapchat")
    assert res.status_code == 422


def test_export_all_platforms_mock(client, tmp_db, tmp_path, monkeypatch):
    """POST /export-all returns exports dict with all known platform keys."""
    from orchestration.crew import _mock_blueprint
    from renderer.render import PLATFORMS
    monkeypatch.setenv("JOBS_DIR", str(tmp_path / "jobs"))
    job = _mock_blueprint("export all test", "youtube")
    job["status"] = "done"
    job["output_path"] = str(tmp_path / "jobs" / job["job_id"] / "output.mp4")
    tmp_db.save_job(job)
    res = client.post(f"/jobs/{job['job_id']}/export-all")
    assert res.status_code == 200
    exports = res.json()["exports"]
    # Must include at minimum the 4 original short-form keys
    assert {"youtube", "tiktok", "instagram", "facebook"}.issubset(set(exports.keys()))
    for p, info in exports.items():
        assert info["path"] is not None, f"{p} export path should not be None"


def test_download_export_missing_returns_404(client, tmp_db):
    """GET /export/{platform} before exporting returns 404."""
    from orchestration.crew import _mock_blueprint
    job = _mock_blueprint("download missing", "youtube")
    job["status"] = "done"
    job["exports"] = {}   # no exports yet
    tmp_db.save_job(job)
    res = client.get(f"/jobs/{job['job_id']}/export/youtube")
    assert res.status_code == 404


# ── Bug A: _platform_vf zero-dimension guard ─────────────────────────────────

def test_platform_vf_zero_dimensions_no_crash():
    """Bug A fix: _platform_vf must not raise ZeroDivisionError on 0-dimension src."""
    from renderer.render import _platform_vf
    result = _platform_vf(0, 0, 720, 1280)
    assert "scale=720:1280" in result

    result2 = _platform_vf(720, 0, 720, 1280)
    assert "scale=720:1280" in result2


# ── Bug C: topic reset on pipeline failure ────────────────────────────────────

def test_wizard_pipeline_failure_resets_topic_to_queued(tmp_db, mock_job):
    """Bug C fix: if wizard pipeline fails, linked topic is reset from in_progress → queued."""
    from unittest.mock import patch
    from dashboard.server import _run_wizard_pipeline

    # Set up a topic in the DB marked in_progress
    from data.db import create_project, add_topics, update_topic_status, list_topics
    proj = create_project("test proj", "finance")
    topics = add_topics(proj["project_id"], [{"title": "test", "hook": "", "why_trending": ""}])
    tid = topics[0]["topic_id"]
    update_topic_status(tid, "in_progress")

    mock_job["status"] = "pending"
    mock_job["topic_id"] = tid
    tmp_db.save_job(mock_job)

    class FakePayload:
        topic_title   = "test"
        platforms     = ["youtube"]
        niche         = "finance"
        caption_style = "karaoke"
        topic_hook    = ""
        topic_id      = tid

    with patch("orchestration.crew.generate_script", side_effect=RuntimeError("Claude down")):
        _run_wizard_pipeline(mock_job["job_id"], FakePayload())

    # Topic must be back to queued
    rows = list_topics(proj["project_id"])
    assert rows[0]["status"] == "queued", f"Expected queued, got {rows[0]['status']}"


# ── Format-selection feature tests ───────────────────────────────────────────

def test_platform_vf_portrait_center_crop():
    """9:16→4:5 export must center-crop height, not pad."""
    from renderer.render import _platform_vf
    vf = _platform_vf(720, 1280, 720, 900)
    assert "crop" in vf, "4:5 export must use crop, not pad"
    assert "pad" not in vf, "4:5 export must not letterbox"


def test_platform_vf_square_center_crop():
    """9:16→1:1 export must center-crop height, not pad."""
    from renderer.render import _platform_vf
    vf = _platform_vf(720, 1280, 720, 720)
    assert "crop" in vf
    assert "pad" not in vf


def test_resolved_formats_with_explicit_formats():
    """Explicit formats= list is used verbatim (filtered to valid keys)."""
    from dashboard.server import CreateJobPayload
    p = CreateJobPayload(
        niche="finance", topic_title="test",
        platforms=["youtube"],
        formats=["youtube_shorts", "instagram_square", "made_up_key"]
    )
    result = p.resolved_formats()
    assert "youtube_shorts" in result
    assert "instagram_square" in result
    assert "made_up_key" not in result   # invalid key filtered out


def test_resolved_formats_defaults_to_brand_default():
    """No explicit formats → each brand's default format is picked."""
    from dashboard.server import CreateJobPayload
    p = CreateJobPayload(
        niche="finance", topic_title="test",
        platforms=["youtube", "instagram"],
        formats=[]
    )
    result = p.resolved_formats()
    assert "youtube_shorts" in result       # youtube default
    assert "instagram_reels" in result      # instagram default
    assert "instagram_square" not in result  # not a default


def test_create_job_stores_formats(client, tmp_db):
    """POST /jobs/create with explicit formats stores them on the job."""
    res = client.post("/jobs/create", json={
        "niche": "finance",
        "topic_title": "Format test",
        "platforms": ["youtube", "instagram"],
        "formats": ["youtube_shorts", "instagram_reels", "instagram_square"],
    })
    assert res.status_code == 200
    job_id = res.json()["job_id"]
    from data.db import load_job
    job = load_job(job_id)
    assert "formats" in job
    assert "youtube_shorts" in job["formats"]
    assert "instagram_square" in job["formats"]


def test_create_job_no_formats_defaults(client, tmp_db):
    """POST /jobs/create without formats= defaults to one format per brand."""
    res = client.post("/jobs/create", json={
        "niche": "finance",
        "topic_title": "Default format test",
        "platforms": ["tiktok", "facebook"],
    })
    assert res.status_code == 200
    job_id = res.json()["job_id"]
    from data.db import load_job
    job = load_job(job_id)
    assert "formats" in job
    assert len(job["formats"]) >= 2     # at least one per brand
    assert "tiktok" in job["formats"]   # tiktok brand → tiktok format
    assert "facebook_reels" in job["formats"]  # facebook default


def test_render_vf_platform_keys():
    """All PLATFORMS keys produce a valid non-empty _platform_vf string."""
    from renderer.render import PLATFORMS, _platform_vf
    for key, (w, h, *_) in PLATFORMS.items():
        vf = _platform_vf(720, 1280, w, h)
        assert vf and "scale" in vf, f"No valid vf for {key}: {vf}"
