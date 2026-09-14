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


# ── Caption style ─────────────────────────────────────────────────────

@app.get("/caption-styles")
def get_caption_styles():
    from renderer.captions import STYLES, KARAOKE_STYLES
    return {
        "styles": list(STYLES.keys()) + list(KARAOKE_STYLES.keys()),
        "default": "clean",
        "descriptions": {
            "clean":          "White bold, black outline, bottom center — YouTube standard",
            "cinematic":      "Yellow on dark bar, bottom center — film/documentary feel",
            "tiktok":         "Giant Impact, thick outline, screen center — viral style",
            "minimal":        "Small light gray, subtle, bottom right — understated",
            "karaoke":        "✨ Word-by-word highlight (yellow), bottom center",
            "karaoke_tiktok": "✨ Word-by-word highlight, Impact font, screen center",
            "karaoke_fire":   "✨ Word-by-word highlight (orange), dramatic",
        }
    }


class CaptionStylePayload(BaseModel):
    caption_style: str


@app.patch("/jobs/{job_id}/caption-style")
def set_caption_style(job_id: str, payload: CaptionStylePayload):
    from renderer.captions import STYLES, KARAOKE_STYLES
    all_styles = set(STYLES.keys()) | set(KARAOKE_STYLES.keys())
    if payload.caption_style not in all_styles:
        raise HTTPException(422, f"Unknown style '{payload.caption_style}'. Choose from: {sorted(all_styles)}")
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] == "approved":
        raise HTTPException(409, "Job is approved and locked")
    job["caption_style"] = payload.caption_style
    save_job(job)
    return job


@app.get("/platforms")
def get_platforms():
    from renderer.render import PLATFORMS
    return {
        "platforms": {k: {"width": v[0], "height": v[1], "label": v[2], "description": v[3]}
                      for k, v in PLATFORMS.items()},
        "aliases": {
            "instagram": ["ig","ig_square","fb_post"],
            "tiktok":    ["reels","shorts","fb_reels"],
            "facebook":  ["fb","fb_video"],
        }
    }


@app.post("/jobs/{job_id}/export/{platform}")
def export_single_platform(job_id: str, platform: str):
    """Export the master to a specific platform size. Render must exist."""
    from renderer.render import export_platform, _canonical_platform, PLATFORMS
    canon = _canonical_platform(platform)
    if canon not in PLATFORMS:
        raise HTTPException(422, f"Unknown platform '{platform}'")
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    try:
        path = export_platform(job, canon)
        exports = job.get("exports", {})
        exports[canon] = path
        job["exports"] = exports
        save_job(job)
        return {"platform": canon, "path": path,
                "size_kb": os.path.getsize(path) // 1024}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Export failed: {e}")


@app.post("/jobs/{job_id}/export-all")
def export_all(job_id: str):
    """Export master to all 4 platform sizes in one call."""
    from renderer.render import export_all_platforms
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    try:
        results = export_all_platforms(job)
        exports = job.get("exports", {})
        for platform, path in results.items():
            if path:
                exports[platform] = path
        job["exports"] = exports
        save_job(job)
        return {
            "exports": {
                p: {"path": path, "size_kb": os.path.getsize(path) // 1024 if path else None}
                for p, path in results.items()
            }
        }
    except Exception as e:
        raise HTTPException(500, f"Export failed: {e}")


@app.get("/jobs/{job_id}/export/{platform}")
def download_export(job_id: str, platform: str):
    """Download a platform-specific export."""
    from renderer.render import _canonical_platform, PLATFORMS
    canon = _canonical_platform(platform)
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    path = job.get("exports", {}).get(canon)
    if not path or not os.path.exists(path):
        raise HTTPException(404, f"No export for '{canon}' — run /export/{canon} first")
    label = PLATFORMS.get(canon, ("","","",""))[2].replace(" ", "_")
    filename = f"{job.get('title','video')[:30].replace(' ','_')}_{label}.mp4"
    return FileResponse(path, media_type="video/mp4",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── Approve ────────────────────────────────────────────────────────────

@app.post("/jobs/{job_id}/render")
def render_job_endpoint(job_id: str):
    """Trigger FFmpeg render with captions for an approved job."""
    import time
    from renderer.render import render_job

    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "approved":
        raise HTTPException(409, f"Job must be approved before rendering (status={job['status']})")

    try:
        update_status(job_id, "rendering")
        output_path = render_job(job)
        update_status(job_id, "done", {"output_path": output_path})
        return load_job(job_id)
    except Exception as e:
        update_status(job_id, "failed")
        raise HTTPException(500, f"Render failed: {e}")



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

@app.get("/jobs/{job_id}/output")
def download_output(job_id: str):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    path = job.get("output_path")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Output MP4 not found — render first")
    filename = f"{job.get('title','video')[:40].replace(' ','_')}.mp4"
    return FileResponse(path, media_type="video/mp4",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


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
