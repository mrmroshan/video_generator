"""
Tests for Project and Topic Bank API endpoints.
"""
import pytest
from fastapi.testclient import TestClient


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def project(client):
    """Create a test project and return it."""
    res = client.post("/projects", json={
        "name": "Test AI Project",
        "niche": "ai",
        "description": "Test project for unit tests",
        "platforms": ["tiktok", "youtube"],
    })
    assert res.status_code == 200
    return res.json()


# ── Project CRUD ─────────────────────────────────────────────────────────────

def test_create_project_success(client):
    res = client.post("/projects", json={"name": "Finance 2026", "niche": "finance"})
    assert res.status_code == 200
    d = res.json()
    assert d["name"] == "Finance 2026"
    assert d["niche"] == "finance"
    assert "project_id" in d
    assert "stats" in d
    assert d["stats"]["total"] == 0


def test_create_project_unknown_niche_rejected(client):
    res = client.post("/projects", json={"name": "X", "niche": "astrology"})
    assert res.status_code == 422


def test_create_project_empty_name_rejected(client):
    res = client.post("/projects", json={"name": "  ", "niche": "finance"})
    assert res.status_code == 422


def test_create_project_bad_platform_rejected(client):
    res = client.post("/projects", json={"name": "X", "niche": "ai", "platforms": ["snapchat"]})
    assert res.status_code == 422


def test_list_projects(client, project):
    res = client.get("/projects")
    assert res.status_code == 200
    ids = [p["project_id"] for p in res.json()]
    assert project["project_id"] in ids


def test_get_project(client, project):
    res = client.get(f"/projects/{project['project_id']}")
    assert res.status_code == 200
    assert res.json()["name"] == project["name"]


def test_get_project_not_found(client):
    res = client.get("/projects/nonexistent-id")
    assert res.status_code == 404


def test_delete_project(client, project):
    pid = project["project_id"]
    res = client.delete(f"/projects/{pid}")
    assert res.status_code == 200
    assert res.json()["deleted"] == pid
    # Confirm gone
    assert client.get(f"/projects/{pid}").status_code == 404


# ── Topic generation ─────────────────────────────────────────────────────────

def test_generate_topics_returns_immediately(client, project):
    """Endpoint is async — returns 'generating' status immediately."""
    res = client.post(f"/projects/{project['project_id']}/topics/generate",
                      json={"count": 5})
    assert res.status_code == 200
    d = res.json()
    assert d["status"] == "generating"
    assert d["requested"] == 5


def test_generate_topics_count_capped_at_40(client, project):
    res = client.post(f"/projects/{project['project_id']}/topics/generate",
                      json={"count": 999})
    assert res.status_code == 200
    assert res.json()["requested"] == 40


def test_generate_topics_unknown_project(client):
    res = client.post("/projects/bad-id/topics/generate", json={"count": 5})
    assert res.status_code == 404


# ── Topic list & status ───────────────────────────────────────────────────────

def test_list_topics_empty_initially(client, project):
    res = client.get(f"/projects/{project['project_id']}/topics")
    assert res.status_code == 200
    d = res.json()
    assert d["topics"] == []
    assert d["stats"]["total"] == 0


def test_add_and_list_topics(client, project):
    """Add topics directly via db, then list via API."""
    from data.db import add_topics
    add_topics(project["project_id"], [
        {"title": "Topic A", "hook": "Hook A", "why_trending": "Reason A"},
        {"title": "Topic B", "hook": "Hook B", "why_trending": "Reason B"},
    ])
    res = client.get(f"/projects/{project['project_id']}/topics")
    assert res.status_code == 200
    topics = res.json()["topics"]
    assert len(topics) == 2
    assert topics[0]["title"] == "Topic A"
    assert topics[0]["status"] == "queued"


def test_filter_topics_by_status(client, project):
    from data.db import add_topics, update_topic_status
    added = add_topics(project["project_id"], [
        {"title": "A", "hook": "", "why_trending": ""},
        {"title": "B", "hook": "", "why_trending": ""},
    ])
    update_topic_status(added[0]["topic_id"], "published")

    queued = client.get(f"/projects/{project['project_id']}/topics?status=queued")
    published = client.get(f"/projects/{project['project_id']}/topics?status=published")
    assert len(queued.json()["topics"]) == 1
    assert len(published.json()["topics"]) == 1


def test_update_topic_status(client, project):
    from data.db import add_topics
    added = add_topics(project["project_id"], [{"title": "X", "hook": "", "why_trending": ""}])
    tid = added[0]["topic_id"]

    res = client.patch(
        f"/projects/{project['project_id']}/topics/{tid}",
        json={"status": "published"}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "published"


def test_update_topic_invalid_status(client, project):
    from data.db import add_topics
    added = add_topics(project["project_id"], [{"title": "Y", "hook": "", "why_trending": ""}])
    tid = added[0]["topic_id"]
    res = client.patch(
        f"/projects/{project['project_id']}/topics/{tid}",
        json={"status": "banana"}
    )
    assert res.status_code == 422


def test_delete_topic(client, project):
    from data.db import add_topics, list_topics
    added = add_topics(project["project_id"], [{"title": "ToDelete", "hook": "", "why_trending": ""}])
    tid = added[0]["topic_id"]
    res = client.delete(f"/projects/{project['project_id']}/topics/{tid}")
    assert res.status_code == 200
    remaining = list_topics(project["project_id"])
    assert not any(t["topic_id"] == tid for t in remaining)


# ── Project stats ─────────────────────────────────────────────────────────────

def test_project_stats_counts(client, project):
    from data.db import add_topics, update_topic_status
    added = add_topics(project["project_id"], [
        {"title": "A", "hook": "", "why_trending": ""},
        {"title": "B", "hook": "", "why_trending": ""},
        {"title": "C", "hook": "", "why_trending": ""},
    ])
    update_topic_status(added[1]["topic_id"], "in_progress")
    update_topic_status(added[2]["topic_id"], "published")

    res = client.get(f"/projects/{project['project_id']}")
    stats = res.json()["stats"]
    assert stats["total"] == 3
    assert stats["queued"] == 1
    assert stats["in_progress"] == 1
    assert stats["published"] == 1


# ── Start video from topic ────────────────────────────────────────────────────

def test_start_video_from_topic(client, project):
    from data.db import add_topics
    added = add_topics(project["project_id"], [{"title": "Video topic", "hook": "Hook", "why_trending": ""}])
    tid = added[0]["topic_id"]

    res = client.post(f"/projects/{project['project_id']}/topics/{tid}/start-video")
    assert res.status_code == 200
    d = res.json()
    assert "job_id" in d
    assert d["topic_id"] == tid
    assert d["status"] == "pending"


def test_start_video_already_in_progress(client, project):
    from data.db import add_topics, update_topic_status
    added = add_topics(project["project_id"], [{"title": "In progress topic", "hook": "", "why_trending": ""}])
    tid = added[0]["topic_id"]
    update_topic_status(tid, "in_progress", job_id="fake-job-id")

    res = client.post(f"/projects/{project['project_id']}/topics/{tid}/start-video")
    assert res.status_code == 409


def test_start_video_published_rejected(client, project):
    from data.db import add_topics, update_topic_status
    added = add_topics(project["project_id"], [{"title": "Published topic", "hook": "", "why_trending": ""}])
    tid = added[0]["topic_id"]
    update_topic_status(tid, "published")

    res = client.post(f"/projects/{project['project_id']}/topics/{tid}/start-video")
    assert res.status_code == 409
