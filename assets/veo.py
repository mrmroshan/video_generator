"""
assets/veo.py — Veo 2 video generation via Google Gemini API

Generates an 8-second 9:16 clip from a broll_prompt.
Each scene in the job gets its own clip.

MOCK_APIS=true → creates a silent black MP4 stub (no API call).
"""
import os
import time
import subprocess
from pathlib import Path

_ROOT = Path(__file__).parent.parent
MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
JOBS_DIR = os.getenv("JOBS_DIR", str(_ROOT / "data" / "jobs"))

# Model constant (upgrade path when Veo 3 is stable)
VEO_MODEL = "veo-2.0-generate-001"
DEFAULT_DURATION = 8
MAX_WAIT_SECONDS = 180
POLL_INTERVAL_SECONDS = 10


def generate_clip(prompt: str, dest_path: str, duration: int = DEFAULT_DURATION) -> str:
    """
    Generate a single Veo 2 clip from prompt.
    Saves to dest_path. Returns dest_path.
    Raises RuntimeError on failure.
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    if MOCK_APIS:
        _write_mock_clip(dest_path, duration)
        print(f"[MOCK/VEO2] Clip → {dest_path}")
        return dest_path

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set — cannot generate Veo 2 clip")

    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)

    print(f"  [VEO2] Generating clip: {prompt[:80]}...")

    operation = client.models.generate_videos(
        model=VEO_MODEL,
        prompt=prompt,
        config=genai.types.GenerateVideosConfig(
            aspect_ratio="9:16",
            duration_seconds=duration,
            number_of_videos=1,
        ),
    )

    # Poll until done (Veo 2 typically takes 30-90s)
    waited = 0
    while not operation.done:
        if waited >= MAX_WAIT_SECONDS:
            raise RuntimeError(f"Veo 2 generation timed out after {MAX_WAIT_SECONDS}s")
        time.sleep(POLL_INTERVAL_SECONDS)
        waited += POLL_INTERVAL_SECONDS
        operation = client.operations.get(operation)
        print(f"  [VEO2] Waiting... ({waited}s)")

    videos = operation.result.generated_videos
    if not videos:
        raise RuntimeError("Veo 2 returned no videos")

    video_bytes = videos[0].video.video_bytes
    if not video_bytes:
        raise RuntimeError("Veo 2 video bytes are empty")

    with open(dest_path, "wb") as f:
        f.write(video_bytes)

    print(f"  [VEO2] ✓ {dest_path} ({len(video_bytes) // 1024}KB)")
    return dest_path


def _write_mock_clip(dest_path: str, duration: int = DEFAULT_DURATION):
    """Write a silent black MP4 stub using FFmpeg (for MOCK_APIS=true)."""
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:s=720x1280:r=30:d={duration}",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            "-c:v", "libx264", "-profile:v", "baseline",
            "-c:a", "aac", "-shortest",
            dest_path,
        ], capture_output=True, check=True)
    except Exception:
        # Ultimate fallback — stub file (render will skip it gracefully)
        Path(dest_path).write_bytes(b"MOCK_VEO2_CLIP")


def fetch_broll_veo2(job: dict) -> dict:
    """
    Generate Veo 2 clips for all scenes in a job.
    Adds 'broll_path' to each scene. Returns updated job.
    Scenes are processed sequentially (API rate limits).
    """
    job_dir = os.path.abspath(os.path.join(JOBS_DIR, job["job_id"]))
    os.makedirs(job_dir, exist_ok=True)

    for scene in job.get("scenes", []):
        scene_id   = scene["scene_id"]
        broll_path = os.path.join(job_dir, f"{scene_id}_broll.mp4")
        prompt     = scene.get("broll_prompt", "cinematic short video clip, 9:16 vertical")

        # Enrich prompt for Veo 2 — add niche style context
        enriched = _enrich_prompt(prompt, job.get("niche", ""))

        try:
            generate_clip(enriched, broll_path)
            scene["broll_path"]   = broll_path
            scene["broll_source"] = "veo2"
            scene["broll_meta"]   = {"source": "veo2", "model": VEO_MODEL}
        except Exception as e:
            print(f"  [WARN] Veo 2 failed for {scene_id}: {e}")
            scene["broll_path"]   = None
            scene["broll_source"] = "veo2_failed"
            scene["broll_meta"]   = {"source": "veo2_failed", "reason": str(e)}

    return job


def _enrich_prompt(prompt: str, niche: str) -> str:
    """
    Append consistent cinematic style guidance to the broll_prompt.
    Keeps prompts concise — Veo 2 works better with focused prompts.
    """
    style_suffixes = {
        "finance":         "cinematic, warm colour grade, shallow depth of field, 4K",
        "entrepreneurship": "documentary style, natural light, handheld energy",
        "health":          "clean bright aesthetic, soft natural light, calm",
        "tech":            "sleek modern, blue-tinted light, sharp focus",
        "mindset":         "moody cinematic, golden hour, contemplative",
        "productivity":    "clean minimal, natural light, focused energy",
        "ai":              "futuristic, blue-purple tones, sharp crisp",
        "marketing":       "bold vibrant, high contrast, energetic",
        "fitness":         "high energy, warm golden tones, dynamic motion",
        "relationships":   "warm intimate, soft bokeh, authentic moments",
    }
    suffix = style_suffixes.get(niche, "cinematic, 4K, professional")
    # Avoid duplicating style words already in prompt
    if "cinematic" in prompt.lower():
        return prompt
    return f"{prompt}, {suffix}"
