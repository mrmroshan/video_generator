"""
Phase 3: Review Dashboard — FastAPI backend
Serves job data, handles caption edits, B-roll swaps, approvals, and media streaming.

Run: uvicorn dashboard.server:app --host 127.0.0.1 --port 8001
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
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from contextlib import asynccontextmanager

from data.db import (
    init_db, list_jobs, load_job, save_job, update_status, update_progress,
    create_project, load_project, list_projects, delete_project,
    add_topics, list_topics, update_topic_status, delete_topic, get_project_stats,
)
from assets.stock import _search_pexels, _download_video
from renderer.render import VALID_PLATFORMS, PLATFORMS, PLATFORM_GROUPS  # single source of truth


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

# ── Wizard: Niches, Topics, Create ────────────────────────────────────

@app.get("/niches")
def get_niches():
    """Return all available niches with metadata."""
    from orchestration.crew import NICHES
    return {"niches": NICHES}



class TopicsPayload(BaseModel):
    niche:    str
    platform: str = "youtube"


@app.post("/topics")
def get_topics(payload: TopicsPayload):
    """Generate 8 trending topic ideas for a niche."""
    from orchestration.crew import NICHES
    if payload.niche not in NICHES:
        raise HTTPException(422, f"Unknown niche '{payload.niche}'. Choose from: {sorted(NICHES)}")
    platform = payload.platform.lower().strip()
    if platform not in VALID_PLATFORMS:
        raise HTTPException(422, f"Unknown platform '{payload.platform}'. Choose from: {sorted(VALID_PLATFORMS)}")

    from orchestration.crew import generate_topic_ideas
    # Call synchronously — topic gen is fast (Claude or mock)
    try:
        result = generate_topic_ideas(payload.niche, payload.platform)
        return result
    except Exception as e:
        raise HTTPException(500, f"Topic generation failed: {e}")


class CreateJobPayload(BaseModel):
    niche:          str
    topic_title:    str
    topic_hook:     str = ""
    platforms:      List[str] = ["tiktok", "instagram", "youtube", "facebook"]
    formats:        List[str] = []   # specific format keys e.g. ["youtube_shorts","instagram_reels","instagram_square"]
    caption_style:  str = "none"
    broll_source:   str = "pexels"   # "pexels" | "veo2"

    @property
    def platform(self) -> str:
        """Primary platform brand — first in platforms list, used for script style."""
        return self.platforms[0] if self.platforms else "tiktok"

    def resolved_formats(self) -> List[str]:
        """
        Return the final list of format keys to export.
        If formats were explicitly set, validate and use them.
        Otherwise, default to the first (default) format for each selected platform brand.
        """
        if self.formats:
            return [f for f in self.formats if f in VALID_PLATFORMS]
        # Default: pick the default format for each selected platform brand
        result = []
        for brand in self.platforms:
            group = PLATFORM_GROUPS.get(brand)
            if group:
                for fmt in group["formats"]:
                    if fmt["default"] and fmt["available"]:
                        result.append(fmt["key"])
                        break
            elif brand in VALID_PLATFORMS:
                result.append(brand)  # backward-compat alias
        return result or ["tiktok"]


@app.post("/jobs/create")
def create_job(payload: CreateJobPayload, background_tasks: BackgroundTasks):
    """
    Wizard entry point: niche + topic → full async pipeline.
    Returns job_id immediately. Client polls GET /jobs/{id}/progress.
    """
    from orchestration.crew import NICHES
    if payload.niche not in NICHES:
        raise HTTPException(422, f"Unknown niche '{payload.niche}'")
    if not payload.topic_title.strip():
        raise HTTPException(422, "topic_title cannot be empty")
    # Validate all selected platforms
    bad = [p for p in payload.platforms if p.lower() not in VALID_PLATFORMS]
    if bad:
        raise HTTPException(422, f"Unknown platform(s): {bad}. Choose from: {sorted(VALID_PLATFORMS)}")
    if not payload.platforms:
        raise HTTPException(422, "At least one platform must be selected")
    broll_source = (payload.broll_source or "pexels").lower()
    if broll_source not in {"pexels", "veo2"}:
        raise HTTPException(422, f"Unknown broll_source '{payload.broll_source}'. Choose from: pexels, veo2")

    # Pre-create the job record so the UI can poll immediately
    import uuid
    from datetime import datetime, timezone
    job_id = str(uuid.uuid4())
    platforms = [p.lower() for p in payload.platforms]
    formats   = payload.resolved_formats()
    job = {
        "job_id":         job_id,
        "status":         "pending",
        "platform":       platforms[0],    # primary brand (for script style)
        "platforms":      platforms,        # selected platform brands
        "formats":        formats,          # resolved format keys for export
        "niche":          payload.niche,
        "topic":          payload.topic_title,
        "topic_hook":     payload.topic_hook,
        "caption_style":  payload.caption_style,
        "broll_source":   broll_source,
        "created_at":     datetime.now(timezone.utc).isoformat(),
        "scenes":         [],
        "progress_phase": "queued",
        "progress_detail": "Queued — starting now...",
    }
    save_job(job)

    background_tasks.add_task(_run_wizard_pipeline, job_id, payload)
    return {"job_id": job_id, "status": "pending",
            "message": "Pipeline started. Poll GET /jobs/{job_id}/progress"}


@app.get("/jobs/{job_id}/progress")
def job_progress(job_id: str):
    """
    Lightweight poll endpoint for the wizard generating screen.
    Returns phase + detail + status so the UI can show live progress.
    """
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id":          job_id,
        "status":          job["status"],
        "progress_phase":  job.get("progress_phase",  "queued"),
        "progress_detail": job.get("progress_detail", ""),
        "progress_updated_at": job.get("progress_updated_at", ""),
        "ready":  job["status"] in ("in_review", "draft"),
        "failed": job["status"] == "failed",
        "title":  job.get("title", job.get("topic", "")),
        "niche":  job.get("niche", ""),
        "platform": job.get("platform", "youtube"),
        "scene_count": len(job.get("scenes", [])),
    }


def _run_wizard_pipeline(job_id: str, payload: "CreateJobPayload"):
    """
    Background task: runs the full pipeline for the wizard flow.
    Updates progress_phase at each step so the UI can show live status.
    Note: server.py already loads .env at startup — no re-load needed here.
    """
    from data.db import update_progress, update_status, load_job, save_job
    from orchestration.crew import generate_script
    from audio.tts import generate_audio_for_job
    from audio.timestamps import extract_timestamps
    from assets.broll import fetch_broll_for_job

    platforms = [p.lower() for p in (payload.platforms or ["tiktok"])]
    primary   = platforms[0]
    broll_source = (getattr(payload, "broll_source", "pexels") or "pexels").lower()
    # Resolve export formats: use explicit formats if set, else default per brand
    raw_formats = getattr(payload, "formats", []) or []
    if raw_formats:
        formats = [f for f in raw_formats if f in VALID_PLATFORMS]
    else:
        formats = []
        for brand in platforms:
            grp = PLATFORM_GROUPS.get(brand)
            if grp:
                for fmt in grp["formats"]:
                    if fmt["default"] and fmt["available"]:
                        formats.append(fmt["key"])
                        break
            elif brand in VALID_PLATFORMS:
                formats.append(brand)
        formats = formats or ["tiktok"]

    try:
        # Phase 1 — Script (always Shorts/9:16, primary platform drives rules)
        update_progress(job_id, "generating_script", "Claude is writing your script...")
        topic = payload.topic_title
        job   = generate_script(topic, primary, niche=payload.niche)
        # Preserve wizard metadata + carry forward progress fields
        job["job_id"]           = job_id
        job["niche"]            = payload.niche
        job["topic"]            = topic
        job["topic_hook"]       = payload.topic_hook
        job["caption_style"]    = payload.caption_style
        job["platform"]         = primary
        job["platforms"]        = platforms   # selected brands
        job["formats"]          = formats     # resolved format keys
        job["broll_source"]     = broll_source
        job["status"]           = "pending"
        job["progress_phase"]   = "generating_script"
        job["progress_detail"]  = "Script complete — generating audio..."
        # Preserve project/topic linkage if started from topic bank
        if hasattr(payload, "project_id") and payload.project_id:
            job["project_id"] = payload.project_id
        if hasattr(payload, "topic_id") and payload.topic_id:
            job["topic_id"] = payload.topic_id
        save_job(job)

        # Phase 2 — Audio
        update_progress(job_id, "generating_audio", f"Generating voiceover for {len(job['scenes'])} scenes...")
        job["progress_phase"]  = "generating_audio"
        job["progress_detail"] = f"Generating voiceover for {len(job['scenes'])} scenes..."
        job = generate_audio_for_job(job)
        save_job(job)

        # Phase 3 — Timestamps
        update_progress(job_id, "extracting_timestamps", "Extracting word-level timestamps with Whisper...")
        job["progress_phase"]  = "extracting_timestamps"
        job["progress_detail"] = "Extracting word-level timestamps with Whisper..."
        for scene in job["scenes"]:
            try:
                extract_timestamps(scene)
            except Exception as e:
                print(f"  [WARN] Timestamps failed for {scene['scene_id']}: {e}")
        save_job(job)

        # Phase 4 — B-roll (source: Pexels or Veo 2)
        if broll_source == "veo2":
            broll_msg = "Generating custom B-roll with Veo 2 AI... (this takes a few minutes)"
        else:
            broll_msg = "Downloading B-roll clips from Pexels..."
        update_progress(job_id, "downloading_broll", broll_msg)
        job["progress_phase"]  = "downloading_broll"
        job["progress_detail"] = broll_msg
        job = fetch_broll_for_job(job)
        save_job(job)

        # Done — hand off to review
        job["status"]          = "in_review"
        job["progress_phase"]  = "ready_for_review"
        job["progress_detail"] = "Ready! Opening review dashboard..."
        save_job(job)
        print(f"[WIZARD] Job {job_id} ready for review")

    except Exception as e:
        print(f"[WIZARD ERROR] {job_id}: {e}")
        try:
            update_progress(job_id, "failed", str(e)[:200])
            update_status(job_id, "failed")
        except Exception:
            pass
        # Reset linked topic back to queued so user can retry from Topic Bank
        try:
            failed_job = load_job(job_id)
            tid = (failed_job or {}).get("topic_id") or getattr(payload, "topic_id", None)
            if tid:
                from data.db import update_topic_status
                update_topic_status(tid, "queued")
                print(f"  [TOPIC] Reset topic {tid} → queued (pipeline failed)")
        except Exception:
            pass


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

    if job["status"] not in ("in_review", "draft"):
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
    if job["status"] not in ("in_review", "draft"):
        job["status"] = "in_review"

    save_job(job)
    return job


# ── B-roll search (returns candidates without downloading) ─────────────

@app.get("/jobs/{job_id}/scenes/{scene_id}/search-broll")
def search_broll(job_id: str, scene_id: str, q: str, limit: int = Query(default=6, ge=1, le=80)):
    if not q or not q.strip():
        raise HTTPException(422, "Search query 'q' cannot be empty")
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
    import urllib.parse as _urlparse
    # SSRF guard: only allow Pexels CDN URLs
    parsed = _urlparse.urlparse(payload.download_url)
    allowed_hosts = {"videos.pexels.com", "www.pexels.com", "images.pexels.com"}
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise HTTPException(422, f"download_url must be a Pexels CDN URL (got: {parsed.hostname!r})")
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
        import shutil as _shutil
        with open(dest, "wb") as f:
            _shutil.copyfileobj(r, f, length=256 * 1024)

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
    if job["status"] not in ("in_review", "draft"):
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


# ── Caption text editor ───────────────────────────────────────────────

@app.get("/jobs/{job_id}/scenes/{scene_id}/caption-text")
def get_caption_text(job_id: str, scene_id: str):
    """
    Return the caption text for a scene in an editable format.
    Each LINE = one phrase group (will appear on screen together).
    Words within a line = karaoke-highlighted one by one.
    Returns the current edited text if saved, or auto-generates from timestamps.
    """
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    scene = next((s for s in job.get("scenes", []) if s["scene_id"] == scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")

    # If already edited, return saved text
    if scene.get("caption_text_edited"):
        return {
            "scene_id":    scene_id,
            "text":        scene["caption_text_edited"],
            "is_edited":   True,
            "word_count":  len(scene["caption_text_edited"].split()),
        }

    # Auto-generate from timestamps: group into lines by phrase
    ts = scene.get("timestamps", [])
    if ts:
        from renderer.captions import KARAOKE_STYLES
        # Use same line_max_chars logic as make_karaoke_ass to show accurate preview
        line_max = 32
        lines, current, char_count = [], [], 0
        for w in ts:
            word = w.get("word", "").strip()
            if not word:
                continue
            # Honour existing phrase_break flags
            if w.get("phrase_break") and current:
                lines.append(" ".join(current))
                current = [word]
                char_count = len(word)
            elif char_count + len(word) + 1 > line_max and current:
                lines.append(" ".join(current))
                current = [word]
                char_count = len(word)
            else:
                current.append(word)
                char_count += len(word) + 1
        if current:
            lines.append(" ".join(current))
        text = "\n".join(lines)
    else:
        # Fallback: use voiceover text as single line (no timestamps — timing will be approximate)
        text = scene.get("voiceover_text", "") or ""

    return {
        "scene_id":    scene_id,
        "text":        text,
        "is_edited":   False,
        "has_timestamps": bool(ts),
        "word_count":  len(text.split()),
    }


class CaptionTextPayload(BaseModel):
    text: str  # multiline — newlines = phrase breaks


@app.post("/jobs/{job_id}/scenes/{scene_id}/recaption")
def recaption_scene(job_id: str, scene_id: str, payload: CaptionTextPayload):
    """
    Save edited caption text and re-burn captions for this scene only.
    - Parses edited text → merges with Whisper timestamps (preserving timing)
    - Re-burns the captioned video for this scene
    - Does NOT require a full re-render
    Returns updated job.
    """
    import subprocess as _sp
    from renderer.captions import parse_caption_edit, burn_karaoke, burn_captions
    from renderer.render import _get_audio_duration
    from pathlib import Path as _Path
    _root = _Path(__file__).parent.parent
    _jobs_dir = os.environ.get("JOBS_DIR", str(_root / "data" / "jobs"))

    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    scene = next((s for s in job.get("scenes", []) if s["scene_id"] == scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")

    composed = scene.get("composed_path", "")
    if not composed or not os.path.exists(composed):
        raise HTTPException(409, f"Scene {scene_id} has no composed video yet — render first")

    text = payload.text.strip()
    if not text:
        raise HTTPException(422, "Caption text cannot be empty")

    # Save the edited text on the scene
    scene["caption_text_edited"] = text

    # Merge edited text into timestamps
    original_ts = scene.get("timestamps", [])
    new_ts = parse_caption_edit(text, original_ts)
    scene["timestamps"] = new_ts

    # Re-burn captions for this scene only
    caption_style = job.get("caption_style", "karaoke")
    use_karaoke   = caption_style.startswith("karaoke") and bool(new_ts)
    audio_dur     = _get_audio_duration(scene.get("audio_path") or composed)

    # Probe video dimensions
    r = _sp.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-select_streams", "v:0", composed],
        capture_output=True, text=True
    )
    vst = next((s for s in json.loads(r.stdout).get("streams", [])
                if s.get("codec_type") == "video"), {})
    width  = vst.get("width",  1280)
    height = vst.get("height", 720)

    captioned = composed.replace("_composed.mp4", "_captioned.mp4")
    try:
        if use_karaoke:
            burn_karaoke(composed, new_ts, audio_dur,
                         style=caption_style, out_path=captioned,
                         audio_path=None, width=width, height=height)
        else:
            # No timestamps or non-karaoke — burn static captions
            from renderer.captions import STYLES as _STYLES
            static_style = caption_style if caption_style in _STYLES else "clean"
            burn_captions(composed, text, audio_dur,
                          style=static_style, out_path=captioned,
                          width=width, height=height)
        scene["captioned_path"] = captioned
    except Exception as e:
        raise HTTPException(500, f"Re-caption failed: {e}")

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
    """Return platform groups with format options for the two-level picker UI."""
    return {
        # Flat map of all known format keys → specs (backward compat)
        "platforms": {k: {"width": v[0], "height": v[1], "label": v[2], "description": v[3]}
                      for k, v in PLATFORMS.items()},
        # Grouped structure for the new two-level UI picker
        "groups": PLATFORM_GROUPS,
        "aliases": {
            "instagram": ["ig", "ig_square", "fb_post"],
            "tiktok":    ["reels", "shorts", "fb_reels"],
            "facebook":  ["fb", "fb_video"],
        }
    }


@app.post("/jobs/{job_id}/export/{platform}")
def export_single_platform(job_id: str, platform: str):
    """Export the master to a specific platform size. Render must exist."""
    from renderer.render import export_platform, _canonical_platform, PLATFORMS, PLATFORM_ALIASES
    # Reject anything that isn't a known key or alias
    raw = platform.lower().strip()
    if raw not in PLATFORMS and raw not in PLATFORM_ALIASES:
        raise HTTPException(422, f"Unknown platform '{platform}'. Choose from: {sorted(PLATFORMS)}")
    canon = _canonical_platform(raw)
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
def render_job_endpoint(job_id: str, background_tasks: BackgroundTasks):
    """Kick off FFmpeg render as a background task. Returns 200 immediately."""
    from renderer.render import render_job

    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "approved":
        raise HTTPException(409, f"Job must be approved before rendering (status={job['status']})")

    # Snapshot the approved job BEFORE setting status=rendering.
    # render_job() checks status=="approved" internally — passing the snapshot
    # avoids the race where the background task loads "rendering" and rejects itself.
    approved_snapshot        = dict(job)
    approved_snapshot["status"] = "approved"  # ensure snapshot stays approved for render_job check

    update_status(job_id, "rendering")

    def _do_render(job_id: str, job_snapshot: dict):
        try:
            output_path = render_job(job_snapshot)
            # Auto-export to each selected format after render
            # formats = resolved format keys (e.g. ["youtube_shorts","instagram_square"])
            formats = job_snapshot.get("formats") or job_snapshot.get("platforms") or ["tiktok"]
            exports = {}
            try:
                from renderer.render import export_platform
                fresh_job = load_job(job_id) or job_snapshot
                fresh_job["output_path"] = output_path
                for fmt in formats:
                    try:
                        exp_path = export_platform(fresh_job, fmt)
                        exports[fmt] = exp_path
                        print(f"  [EXPORT] {fmt} → {exp_path}")
                    except Exception as ex:
                        print(f"  [WARN] Export failed for {fmt}: {ex}")
            except Exception as ex:
                print(f"  [WARN] Auto-export failed: {ex}")
            update_status(job_id, "done", {"output_path": output_path, "exports": exports})
            # Auto-mark linked topic as published when render completes
            try:
                done_job = load_job(job_id) or job_snapshot
                tid = done_job.get("topic_id")
                if tid:
                    from data.db import update_topic_status
                    update_topic_status(tid, "published", job_id=job_id)
                    print(f"  [TOPIC] Marked topic {tid} → published")
            except Exception as ex:
                print(f"  [WARN] Could not mark topic published: {ex}")
        except Exception as e:
            print(f"[ERROR] Render failed for {job_id}: {e}")
            try:
                update_status(job_id, "failed")
            except Exception:
                pass
            # Reset linked topic back to queued so user can retry
            try:
                failed_job = load_job(job_id) or job_snapshot
                tid = failed_job.get("topic_id")
                if tid:
                    from data.db import update_topic_status
                    update_topic_status(tid, "queued")
                    print(f"  [TOPIC] Reset topic {tid} → queued (render failed)")
            except Exception:
                pass

    background_tasks.add_task(_do_render, job_id, approved_snapshot)
    return {
        "status": "rendering",
        "job_id": job_id,
        "message": "Render started in background. Poll GET /jobs/{job_id}/render-status for completion."
    }


@app.get("/jobs/{job_id}/render-status")
def render_status(job_id: str):
    """Lightweight polling endpoint for render progress."""
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id":      job_id,
        "status":      job["status"],
        "output_path": job.get("output_path"),
        "exports":     job.get("exports", {}),
        "done":        job["status"] == "done",
        "failed":      job["status"] == "failed",
    }



@app.post("/jobs/{job_id}/save-draft")
def save_draft(job_id: str):
    """
    Explicitly mark a job as 'draft' — edits saved, not yet approved.
    Can be called multiple times; always returns the updated job.
    Allowed from: in_review, draft (idempotent re-save).
    """
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    if job["status"] in ("approved", "rendering", "done"):
        raise HTTPException(409, f"Cannot save draft — job is already '{job['status']}'")
    update_status(job_id, "draft", {"draft_saved_at": datetime.now(timezone.utc).isoformat()})
    return load_job(job_id)


@app.post("/jobs/{job_id}/approve")
def approve_job(job_id: str):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    if job["status"] in ("approved", "done", "rendering"):
        raise HTTPException(409, f"Cannot approve a job with status '{job['status']}'")
    # Block approval if the wizard pipeline hasn't finished yet
    progress_phase = job.get("progress_phase", "")
    if progress_phase not in ("ready_for_review", "") and job["status"] not in ("in_review", "draft"):
        raise HTTPException(409, f"Job is still generating (phase: {progress_phase!r}) — wait until it reaches review")
    if not job.get("scenes"):
        raise HTTPException(409, "Job has no scenes yet — pipeline may still be running")
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


# ── Projects ──────────────────────────────────────────────────────────


class CreateProjectPayload(BaseModel):
    name:        str
    niche:       str
    description: str = ""
    platforms:   List[str] = ["tiktok", "instagram", "youtube", "facebook"]


class GenerateTopicsPayload(BaseModel):
    count:    int = 20    # topics to generate this batch (max 40 per call)
    platform: str = "tiktok"


class TopicStatusPayload(BaseModel):
    status: str           # queued | in_progress | published | archived
    job_id: Optional[str] = None


@app.get("/projects")
def get_projects():
    """List all content projects with topic stats."""
    projects = list_projects()
    result = []
    for p in projects:
        stats = get_project_stats(p["project_id"])
        result.append({**p, "stats": stats})
    return result


@app.post("/projects")
def create_project_endpoint(payload: CreateProjectPayload):
    """Create a new content project."""
    from orchestration.crew import NICHES
    if payload.niche not in NICHES:
        raise HTTPException(422, f"Unknown niche '{payload.niche}'. Choose from: {sorted(NICHES)}")
    if not payload.name.strip():
        raise HTTPException(422, "Project name cannot be empty")
    bad = [p for p in payload.platforms if p.lower() not in VALID_PLATFORMS]
    if bad:
        raise HTTPException(422, f"Unknown platform(s): {bad}. Choose from: {sorted(VALID_PLATFORMS)}")
    project = create_project(
        name=payload.name,
        niche=payload.niche,
        description=payload.description,
        platforms=payload.platforms,
    )
    return {**project, "stats": get_project_stats(project["project_id"])}


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    """Get a single project with stats."""
    project = load_project(project_id)
    if not project:
        raise HTTPException(404, f"Project not found: {project_id}")
    stats = get_project_stats(project_id)
    return {**project, "stats": stats}


@app.delete("/projects/{project_id}")
def delete_project_endpoint(project_id: str):
    """Delete a project and all its topics."""
    project = load_project(project_id)
    if not project:
        raise HTTPException(404, f"Project not found: {project_id}")
    delete_project(project_id)
    return {"deleted": project_id}


@app.get("/projects/{project_id}/topics")
def get_topics(project_id: str, status: str = None):
    """List topics for a project. Optional ?status= filter."""
    project = load_project(project_id)
    if not project:
        raise HTTPException(404, f"Project not found: {project_id}")
    from data.db import TOPIC_STATUSES
    if status and status not in TOPIC_STATUSES:
        raise HTTPException(422, f"Unknown status '{status}'. Choose from: {sorted(TOPIC_STATUSES)}")
    topics = list_topics(project_id, status=status)
    stats  = get_project_stats(project_id)
    return {"project": project, "topics": topics, "stats": stats}


@app.post("/projects/{project_id}/topics/generate")
def generate_topics_endpoint(project_id: str, payload: GenerateTopicsPayload,
                              background_tasks: BackgroundTasks):
    """
    Trigger async batch topic generation via Claude.
    Returns immediately — poll GET /projects/{id}/topics to see new topics appear.
    Max 40 per call; call multiple times to build a large bank.
    """
    project = load_project(project_id)
    if not project:
        raise HTTPException(404, f"Project not found: {project_id}")
    count = max(1, min(40, payload.count))  # cap at 40 per call

    def _generate(project_id: str, niche: str, count: int, platform: str):
        from orchestration.crew import generate_topics_batch
        try:
            # Pass existing titles so Claude avoids duplicates
            existing = [t["title"] for t in list_topics(project_id)]
            new_topics = generate_topics_batch(
                niche=niche, count=count,
                existing_titles=existing, platform=platform,
            )
            if new_topics:
                add_topics(project_id, new_topics)
                print(f"[TOPICS] Added {len(new_topics)} topics to project {project_id}")
        except Exception as e:
            print(f"[TOPICS ERROR] {project_id}: {e}")

    background_tasks.add_task(
        _generate, project_id, project["niche"], count, payload.platform
    )
    return {
        "status":     "generating",
        "project_id": project_id,
        "requested":  count,
        "message":    f"Generating {count} topics in background. Poll GET /projects/{project_id}/topics.",
    }


@app.patch("/projects/{project_id}/topics/{topic_id}")
def update_topic(project_id: str, topic_id: str, payload: TopicStatusPayload):
    """Update topic status: queued → in_progress → published | archived."""
    from data.db import TOPIC_STATUSES
    if payload.status not in TOPIC_STATUSES:
        raise HTTPException(422, f"Invalid status '{payload.status}'. Choose from: {sorted(TOPIC_STATUSES)}")
    updated = update_topic_status(topic_id, payload.status, payload.job_id)
    if not updated:
        raise HTTPException(404, f"Topic not found: {topic_id}")
    return updated


@app.delete("/projects/{project_id}/topics/{topic_id}")
def delete_topic_endpoint(project_id: str, topic_id: str):
    """Permanently delete a topic."""
    delete_topic(topic_id)
    return {"deleted": topic_id}


@app.post("/projects/{project_id}/topics/{topic_id}/start-video")
def start_video_from_topic(project_id: str, topic_id: str,
                            background_tasks: BackgroundTasks):
    """
    Kick off the full video pipeline from a queued topic.
    Marks topic as in_progress, creates a job, returns job_id.
    """
    project = load_project(project_id)
    if not project:
        raise HTTPException(404, f"Project not found: {project_id}")

    topics = list_topics(project_id)
    topic  = next((t for t in topics if t["topic_id"] == topic_id), None)
    if not topic:
        raise HTTPException(404, f"Topic not found: {topic_id}")
    if topic["status"] == "published":
        raise HTTPException(409, "Topic is already published")
    if topic["status"] == "in_progress":
        raise HTTPException(409, f"Topic already has a video in progress (job: {topic.get('job_id')})")

    # Build a CreateJobPayload and call the same pipeline
    _project_id = project_id   # capture for inner class
    _topic_id   = topic_id

    class _TopicPayload:
        topic_title   = topic["title"]
        topic_hook    = topic.get("hook", "")
        niche         = project["niche"]
        platforms     = project.get("platforms", ["tiktok", "instagram", "youtube", "facebook"])
        caption_style = "karaoke"
        broll_source  = project.get("broll_source", "pexels")  # honour project preference
        project_id    = _project_id
        topic_id      = _topic_id

    import uuid
    from datetime import datetime, timezone
    job_id = str(uuid.uuid4())
    platforms = _TopicPayload.platforms
    job = {
        "job_id":          job_id,
        "status":          "pending",
        "platform":        platforms[0],
        "platforms":       platforms,
        "niche":           project["niche"],
        "topic":           topic["title"],
        "topic_hook":      topic.get("hook", ""),
        "caption_style":   "karaoke",
        "broll_source":    project.get("broll_source", "pexels"),  # honour project preference
        "project_id":      project_id,
        "topic_id":        topic_id,
        "created_at":      datetime.now(timezone.utc).isoformat(),
        "scenes":          [],
        "progress_phase":  "queued",
        "progress_detail": "Queued — starting now...",
    }
    save_job(job)

    # Mark topic in_progress
    update_topic_status(topic_id, "in_progress", job_id=job_id)

    background_tasks.add_task(_run_wizard_pipeline, job_id, _TopicPayload())
    return {
        "job_id":     job_id,
        "topic_id":   topic_id,
        "project_id": project_id,
        "status":     "pending",
        "message":    "Pipeline started. Poll GET /jobs/{job_id}/progress",
    }

