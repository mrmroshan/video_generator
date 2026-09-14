"""
Phase 3: Review Dashboard — FastAPI backend
Serves job data, handles caption edits, B-roll swaps, approvals, and media streaming.

Run: uvicorn dashboard.server:app --reload --port 8000
"""
import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

# Allow imports from project root
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load .env
env_path = ROOT / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager

from data.db import init_db, list_jobs, load_job, save_job, update_status
from assets.stock import _search_pexels, _download_video


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Video Maker Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Jobs ──────────────────────────────────────────────────────────────

@app.get("/jobs")
def get_jobs():
    return list_jobs()


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    return job


# ── Scene edits ───────────────────────────────────────────────────────

class CaptionPatch(BaseModel):
    voiceover_text: str | None = None
    broll_prompt: str | None = None
    target_duration_seconds: float | None = None


@app.patch("/jobs/{job_id}/scenes/{scene_id}")
def patch_scene(job_id: str, scene_id: str, patch: CaptionPatch):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    if job["status"] == "approved":
        raise HTTPException(409, "Job is approved and locked — cannot edit")

    scene = next((s for s in job["scenes"] if s["scene_id"] == scene_id), None)
    if not scene:
        raise HTTPException(404, f"Scene not found: {scene_id}")

    if patch.voiceover_text is not None:
        scene["voiceover_text"] = patch.voiceover_text.strip()
    if patch.broll_prompt is not None:
        scene["broll_prompt"] = patch.broll_prompt.strip()
    if patch.target_duration_seconds is not None:
        if not (1 <= patch.target_duration_seconds <= 60):
            raise HTTPException(422, "Duration must be between 1 and 60 seconds")
        scene["target_duration_seconds"] = patch.target_duration_seconds

    if job["status"] != "in_review":
        job["status"] = "in_review"

    save_job(job)
    return job


class ReorderPayload(BaseModel):
    scene_ids: list[str]


@app.post("/jobs/{job_id}/reorder")
def reorder_scenes(job_id: str, payload: ReorderPayload):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    if job["status"] == "approved":
        raise HTTPException(409, "Job is approved and locked — cannot reorder")

    scene_map = {s["scene_id"]: s for s in job["scenes"]}
    missing = [sid for sid in payload.scene_ids if sid not in scene_map]
    if missing:
        raise HTTPException(422, f"Unknown scene IDs: {missing}")

    job["scenes"] = [scene_map[sid] for sid in payload.scene_ids]
    if job["status"] != "in_review":
        job["status"] = "in_review"

    save_job(job)
    return job


# ── B-roll search (returns candidates without downloading) ─────────────

@app.get("/jobs/{job_id}/scenes/{scene_id}/search-broll")
def search_broll(job_id: str, scene_id: str, q: str, limit: int = 6):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "PEXELS_API_KEY not configured")

    import urllib.request, urllib.parse, json as _json

    encoded = urllib.parse.quote(q)
    url = f"https://api.pexels.com/videos/search?query={encoded}&per_page={limit}&orientation=landscape"
    req = urllib.request.Request(url, headers={
        "Authorization": api_key,
        "User-Agent": "VideoMaker/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())
    except Exception as e:
        raise HTTPException(502, f"Pexels error: {e}")

    results = []
    for v in data.get("videos", []):
        files = v.get("video_files", [])
        # Prefer HD
        hd = next((f for f in files if f.get("quality") == "hd"), files[0] if files else None)
        sd = next((f for f in files if f.get("quality") == "sd"), hd)
        if not hd:
            continue
        results.append({
            "video_id":     v["id"],
            "photographer": v.get("user", {}).get("name", "Unknown"),
            "pexels_url":   v.get("url", ""),
            "duration":     v.get("duration", 0),
            "width":        hd.get("width", 0),
            "height":       hd.get("height", 0),
            "preview_url":  sd["link"] if sd else hd["link"],  # lower-res for preview
            "download_url": hd["link"],
            "image":        v.get("image", ""),
        })
    return {"results": results, "total": data.get("total_results", 0)}


# ── Pick a specific B-roll result ─────────────────────────────────────

class PickBrollPayload(BaseModel):
    download_url: str
    video_id:     int
    photographer: str
    pexels_url:   str
    width:        int
    height:       int
    duration:     int


@app.post("/jobs/{job_id}/scenes/{scene_id}/pick-broll")
def pick_broll(job_id: str, scene_id: str, payload: PickBrollPayload):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] == "approved":
        raise HTTPException(409, "Job is approved and locked")

    scene = next((s for s in job["scenes"] if s["scene_id"] == scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")

    import urllib.request as _req
    jobs_dir = os.environ.get("JOBS_DIR", str(ROOT / "data" / "jobs"))
    job_dir  = os.path.join(jobs_dir, job_id)
    os.makedirs(job_dir, exist_ok=True)
    dest = os.path.join(job_dir, f"{scene_id}_broll.mp4")

    req = _req.Request(payload.download_url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.pexels.com/",
    })
    with _req.urlopen(req, timeout=60) as r:
        with open(dest, "wb") as f:
            f.write(r.read())

    scene["broll_path"] = dest
    scene["broll_meta"] = {
        "source":       "pexels",
        "video_id":     payload.video_id,
        "photographer": payload.photographer,
        "pexels_url":   payload.pexels_url,
        "width":        payload.width,
        "height":       payload.height,
        "duration":     payload.duration,
    }
    if job["status"] != "in_review":
        job["status"] = "in_review"

    save_job(job)
    return job


# ── B-roll swap (quick re-fetch same prompt) ──────────────────────────

@app.post("/jobs/{job_id}/scenes/{scene_id}/swap-broll")
def swap_broll(job_id: str, scene_id: str):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    if job["status"] == "approved":
        raise HTTPException(409, "Job is approved and locked — cannot swap B-roll")

    scene = next((s for s in job["scenes"] if s["scene_id"] == scene_id), None)
    if not scene:
        raise HTTPException(404, f"Scene not found: {scene_id}")

    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "PEXELS_API_KEY not configured")

    mock = os.environ.get("MOCK_APIS", "true").lower() == "true"
    jobs_dir = os.environ.get("JOBS_DIR", str(ROOT / "data" / "jobs"))
    job_dir = os.path.join(jobs_dir, job_id)
    os.makedirs(job_dir, exist_ok=True)
    broll_path = os.path.join(job_dir, f"{scene_id}_broll.mp4")

    if mock:
        with open(broll_path, "wb") as f:
            f.write(b"MOCK_BROLL_SWAPPED")
        scene["broll_path"] = broll_path
        scene["broll_meta"] = {"source": "mock"}
    else:
        result = _search_pexels(scene["broll_prompt"], api_key)
        if not result:
            raise HTTPException(404, f"No Pexels results for: {scene['broll_prompt']}")
        _download_video(result["url"], broll_path)
        scene["broll_path"] = broll_path
        scene["broll_meta"] = {
            "source": "pexels",
            "video_id": result["video_id"],
            "photographer": result["photographer"],
            "pexels_url": result["pexels_url"],
            "width": result["width"],
            "height": result["height"],
            "duration": result["duration"],
        }

    save_job(job)
    return job


# ── Approve ───────────────────────────────────────────────────────────

@app.post("/jobs/{job_id}/approve")
def approve_job(job_id: str):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    if job["status"] == "approved":
        return job  # idempotent
    update_status(job_id, "approved", {"approved_at": datetime.now(timezone.utc).isoformat()})
    return load_job(job_id)


# ── Media streaming ───────────────────────────────────────────────────

@app.get("/jobs/{job_id}/scenes/{scene_id}/audio")
def stream_audio(job_id: str, scene_id: str):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    scene = next((s for s in job["scenes"] if s["scene_id"] == scene_id), None)
    if not scene or not scene.get("audio_path"):
        raise HTTPException(404, "Audio not found")
    path = scene["audio_path"]
    if not os.path.exists(path):
        raise HTTPException(404, f"Audio file missing: {path}")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/jobs/{job_id}/scenes/{scene_id}/broll")
def stream_broll(job_id: str, scene_id: str):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    scene = next((s for s in job["scenes"] if s["scene_id"] == scene_id), None)
    if not scene or not scene.get("broll_path"):
        raise HTTPException(404, "B-roll not found")
    path = scene["broll_path"]
    if not os.path.exists(path):
        raise HTTPException(404, f"B-roll file missing: {path}")
    return FileResponse(path, media_type="video/mp4")
