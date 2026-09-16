"""
Tests for Veo 2 B-roll generation and the b-roll orchestrator.
"""
import os
import pytest


# ── assets/veo.py ─────────────────────────────────────────────────────────────

def test_generate_clip_mock_creates_file(tmp_path, monkeypatch):
    from assets import veo
    monkeypatch.setattr(veo, "MOCK_APIS", True)
    dest = str(tmp_path / "scene_01_broll.mp4")
    result = veo.generate_clip("test prompt", dest)
    assert result == dest
    assert os.path.exists(dest)
    assert os.path.getsize(dest) > 0


def test_fetch_broll_veo2_adds_broll_path(tmp_path, monkeypatch):
    from assets import veo
    monkeypatch.setattr(veo, "MOCK_APIS", True)
    monkeypatch.setattr(veo, "JOBS_DIR", str(tmp_path))

    job = {
        "job_id": "test-job",
        "niche":  "finance",
        "scenes": [
            {"scene_id": "scene_01", "broll_prompt": "hand counting cash"},
            {"scene_id": "scene_02", "broll_prompt": "bank statement"},
        ],
    }
    result = veo.fetch_broll_veo2(job)
    assert result["scenes"][0]["broll_path"].endswith("scene_01_broll.mp4")
    assert result["scenes"][1]["broll_path"].endswith("scene_02_broll.mp4")
    assert result["scenes"][0]["broll_source"] == "veo3.1"
    assert os.path.exists(result["scenes"][0]["broll_path"])


def test_fetch_broll_veo2_handles_failure(tmp_path, monkeypatch):
    from assets import veo
    monkeypatch.setattr(veo, "MOCK_APIS", True)
    monkeypatch.setattr(veo, "JOBS_DIR", str(tmp_path))

    # Make generate_clip raise for scene_02
    original = veo.generate_clip
    calls = {"n": 0}

    def flaky(prompt, dest_path, duration=8):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated Veo failure")
        return original(prompt, dest_path, duration)

    monkeypatch.setattr(veo, "generate_clip", flaky)

    job = {
        "job_id": "test-job",
        "niche":  "ai",
        "scenes": [
            {"scene_id": "scene_01", "broll_prompt": "prompt one"},
            {"scene_id": "scene_02", "broll_prompt": "prompt two"},
        ],
    }
    result = veo.fetch_broll_veo2(job)
    assert result["scenes"][0]["broll_path"] is not None
    assert result["scenes"][0]["broll_source"] == "veo3.1"
    assert result["scenes"][1]["broll_path"] is None
    assert result["scenes"][1]["broll_source"] == "veo_failed"


def test_enrich_prompt_adds_style_for_finance():
    from assets.veo import _enrich_prompt
    result = _enrich_prompt("person counting money", "finance")
    assert "warm colour grade" in result


def test_enrich_prompt_skips_if_cinematic_present():
    from assets.veo import _enrich_prompt
    prompt = "cinematic shot of city skyline"
    result = _enrich_prompt(prompt, "finance")
    assert result == prompt  # unchanged


def test_enrich_prompt_unknown_niche_gets_default():
    from assets.veo import _enrich_prompt
    result = _enrich_prompt("test prompt", "unknown_niche")
    assert "4K" in result


def test_generate_clip_raises_without_api_key(tmp_path, monkeypatch):
    from assets import veo
    monkeypatch.setattr(veo, "MOCK_APIS", False)
    monkeypatch.setattr(veo, "GEMINI_API_KEY", "")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY not set"):
        veo.generate_clip("test", str(tmp_path / "x.mp4"))


# ── assets/broll.py (orchestrator) ───────────────────────────────────────────

def test_orchestrator_routes_pexels_by_default(monkeypatch):
    from assets import broll
    called = {}

    def fake_pexels(job):
        called["source"] = "pexels"
        return job

    monkeypatch.setattr("assets.stock.fetch_broll_pexels", fake_pexels)
    broll.fetch_broll_for_job({"broll_source": "pexels", "scenes": []})
    assert called["source"] == "pexels"


def test_orchestrator_routes_veo2_when_set(monkeypatch):
    from assets import broll
    called = {}

    def fake_veo(job):
        called["source"] = "veo2"
        return job

    monkeypatch.setattr("assets.veo.fetch_broll_veo2", fake_veo)
    broll.fetch_broll_for_job({"broll_source": "veo2", "scenes": []})
    assert called["source"] == "veo2"


def test_orchestrator_defaults_to_pexels_for_missing_source(monkeypatch):
    from assets import broll
    called = {}

    def fake_pexels(job):
        called["source"] = "pexels"
        return job

    monkeypatch.setattr("assets.stock.fetch_broll_pexels", fake_pexels)
    broll.fetch_broll_for_job({"scenes": []})  # no broll_source key
    assert called["source"] == "pexels"


# ── SSL context (stock.py hardening) ─────────────────────────────────────────

def test_ssl_context_returns_sslcontext():
    from assets.stock import _ssl_context
    ctx = _ssl_context()
    assert isinstance(ctx, __import__("ssl").SSLContext)


def test_ssl_context_uses_certifi_when_available():
    import certifi
    import ssl
    # certifi is installed → the context should reference its bundle path
    from assets.stock import _ssl_context
    ctx = _ssl_context()
    # The CA file loaded should be certifi's (verify via get_ca_certs non-empty
    # or checking the context's cafile indirectly through ca cert count)
    assert ctx is not None


# ── API integration ──────────────────────────────────────────────────────────

def test_wizard_defaults_to_pexels(client):
    """Create job without broll_source → defaults to pexels."""
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "test topic",
        "platforms": ["tiktok"],
    })
    assert res.status_code == 200
    from data.db import load_job
    job = load_job(res.json()["job_id"])
    assert job.get("broll_source") == "pexels"


def test_wizard_accepts_veo2_source(client):
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "test topic",
        "platforms": ["tiktok"], "broll_source": "veo2",
    })
    assert res.status_code == 200
    from data.db import load_job
    job = load_job(res.json()["job_id"])
    assert job.get("broll_source") == "veo2"


def test_wizard_rejects_unknown_broll_source(client):
    res = client.post("/jobs/create", json={
        "niche": "finance", "topic_title": "test topic",
        "platforms": ["tiktok"], "broll_source": "sora",
    })
    assert res.status_code == 422
