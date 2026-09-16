"""
assets/veo.py — Veo 3.1 video generation via Google Gemini API

Generates an 8-second 9:16 clip from a broll_prompt.
Each scene in the job gets its own clip.

API note: Veo 3.1 returns a download URI (not raw bytes).
We authenticate the download with x-goog-api-key header.

MOCK_APIS=true → creates a silent black MP4 stub (no API call).
"""
import os
import ssl
import time
import urllib.request
import subprocess
from pathlib import Path

_ROOT = Path(__file__).parent.parent
MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
JOBS_DIR = os.getenv("JOBS_DIR", str(_ROOT / "data" / "jobs"))

# Model — use fast for speed, swap to generate-preview for max quality
VEO_MODEL   = "veo-3.1-fast-generate-preview"
VEO_MODEL_HQ = "veo-3.1-generate-preview"
DEFAULT_DURATION = 8
MAX_WAIT_SECONDS = 300   # 5 min — Veo 3.1 can take up to 90s+ per clip
POLL_INTERVAL_SECONDS = 10


def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def generate_clip(prompt: str, dest_path: str, duration: int = DEFAULT_DURATION,
                  quality: str = "fast") -> str:
    """
    Generate a single Veo 3.1 clip from prompt.
    quality: "fast" (veo-3.1-fast) or "hq" (veo-3.1-generate)
    Saves to dest_path. Returns dest_path.
    Raises RuntimeError on failure.
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    if MOCK_APIS:
        _write_mock_clip(dest_path, duration)
        print(f"[MOCK/VEO3.1] Clip → {dest_path}")
        return dest_path

    api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set — cannot generate Veo clip")

    from google import genai
    client = genai.Client(api_key=api_key)
    model = VEO_MODEL_HQ if quality == "hq" else VEO_MODEL

    print(f"  [VEO3.1] Generating ({model}): {prompt[:80]}...")

    operation = client.models.generate_videos(
        model=model,
        prompt=prompt,
        config=genai.types.GenerateVideosConfig(
            aspect_ratio="9:16",
            duration_seconds=duration,
            number_of_videos=1,
        ),
    )

    # Poll until done
    waited = 0
    while not operation.done:
        if waited >= MAX_WAIT_SECONDS:
            raise RuntimeError(f"Veo 3.1 generation timed out after {MAX_WAIT_SECONDS}s")
        time.sleep(POLL_INTERVAL_SECONDS)
        waited += POLL_INTERVAL_SECONDS
        operation = client.operations.get(operation)
        print(f"  [VEO3.1] Waiting... ({waited}s)")

    videos = operation.result.generated_videos
    if not videos:
        raise RuntimeError("Veo 3.1 returned no videos")

    video = videos[0].video
    if not video:
        raise RuntimeError("Veo 3.1: no video object in result")

    # Veo 3.1 returns a URI — download it with API key auth
    if video.uri:
        _download_uri(video.uri, dest_path, api_key)
    elif video.video_bytes:
        with open(dest_path, "wb") as f:
            f.write(video.video_bytes)
    else:
        raise RuntimeError("Veo 3.1: neither uri nor video_bytes in result")

    size_kb = os.path.getsize(dest_path) // 1024
    print(f"  [VEO3.1] ✓ {dest_path} ({size_kb}KB)")
    return dest_path


def _download_uri(uri: str, dest_path: str, api_key: str):
    """Download a Veo-generated clip from the Gemini Files API URI."""
    req = urllib.request.Request(
        uri,
        headers={"x-goog-api-key": api_key}
    )
    with urllib.request.urlopen(req, timeout=120, context=_ssl_ctx()) as resp:
        data = resp.read()
    with open(dest_path, "wb") as f:
        f.write(data)


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
        Path(dest_path).write_bytes(b"MOCK_VEO31_CLIP")


def fetch_broll_veo2(job: dict) -> dict:
    """
    Generate Veo 3.1 clips for all scenes in a job.
    Adds 'broll_path' to each scene. Returns updated job.
    Scenes processed sequentially (API rate limits).
    """
    job_dir = os.path.abspath(os.path.join(JOBS_DIR, job["job_id"]))
    os.makedirs(job_dir, exist_ok=True)

    for scene in job.get("scenes", []):
        scene_id   = scene["scene_id"]
        broll_path = os.path.join(job_dir, f"{scene_id}_broll.mp4")
        prompt     = scene.get("broll_prompt", "cinematic short video clip, 9:16 vertical")

        enriched = _enrich_prompt(prompt, job.get("niche", ""))

        try:
            generate_clip(enriched, broll_path)
            scene["broll_path"]   = broll_path
            scene["broll_source"] = "veo3.1"
            scene["broll_meta"]   = {"source": "veo3.1", "model": VEO_MODEL}
        except Exception as e:
            print(f"  [WARN] Veo 3.1 failed for {scene_id}: {e}")
            scene["broll_path"]   = None
            scene["broll_source"] = "veo_failed"
            scene["broll_meta"]   = {"source": "veo_failed", "reason": str(e)}

    return job


def _enrich_prompt(prompt: str, niche: str) -> str:
    """Append niche-specific cinematic style to the broll_prompt."""
    style_suffixes = {
        "finance":          "cinematic, warm colour grade, shallow depth of field, 4K",
        "entrepreneurship": "documentary style, natural light, handheld energy",
        "health":           "clean bright aesthetic, soft natural light, calm",
        "tech":             "sleek modern, blue-tinted light, sharp focus",
        "mindset":          "moody cinematic, golden hour, contemplative",
        "productivity":     "clean minimal, natural light, focused energy",
        "ai":               "futuristic, blue-purple tones, sharp crisp",
        "marketing":        "bold vibrant, high contrast, energetic",
        "fitness":          "high energy, warm golden tones, dynamic motion",
        "relationships":    "warm intimate, soft bokeh, authentic moments",
    }
    suffix = style_suffixes.get(niche, "cinematic, 4K, professional")
    if "cinematic" in prompt.lower():
        return prompt
    return f"{prompt}, {suffix}"



