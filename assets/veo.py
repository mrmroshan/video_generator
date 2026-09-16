"""
assets/veo.py — Veo 3.1 video generation via Google Gemini API

Generates 8-second 9:16 clips from broll_prompts.

THREE QUALITY IMPROVEMENTS over v1:
  1. _veo_safe_prompt() — rewrites action-based prompts to scene-based.
     AI video models fail at multi-step actions (counting money → scratch nose
     → money disappears). Scene descriptions are stable; actions are not.
  2. HQ model default — veo-3.1-generate-preview (was fast-generate-preview).
     Better temporal consistency and object permanence.
  3. best_of=2 — generates 2 candidates, keeps the larger file.
     Larger = more visual content = less likely to be a glitchy short clip.

API note: Veo 3.1 returns a download URI (not raw bytes).
We authenticate the download with x-goog-api-key header.

MOCK_APIS=true → silent black MP4 stub (no API call).
"""
import os
import re
import ssl
import time
import urllib.request
import subprocess
from pathlib import Path

_ROOT = Path(__file__).parent.parent
MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
JOBS_DIR = os.getenv("JOBS_DIR", str(_ROOT / "data" / "jobs"))

# Use HQ model by default — better object permanence and temporal consistency
VEO_MODEL    = "veo-3.1-generate-preview"          # HQ (default)
VEO_MODEL_FAST = "veo-3.1-fast-generate-preview"   # Fast fallback
DEFAULT_DURATION    = 8
MAX_WAIT_SECONDS    = 300   # 5 min per clip
POLL_INTERVAL_SECS  = 10

# ── Prompt safety: action verbs that cause morphing / object loss ─────────────
#
# Pattern → Replacement rules (applied in order, case-insensitive).
# Goal: describe WHAT THE FRAME LOOKS LIKE, not WHAT IS HAPPENING.
#
_ACTION_RULES = [
    # Person + object interactions (most common source of artifacts)
    (r'\bperson counting (\w[\w\s]*)',         r'stack of \1 spread neatly on desk'),
    (r'\b\w+ counting (\w[\w\s]*)',            r'stack of \1 arranged on wooden surface'),
    (r'\bperson holding (\w[\w\s]*)',          r'close-up of \1, hands out of frame'),
    (r'\bhand holding (\w[\w\s]*)',            r'close-up of \1, shallow depth of field'),
    (r'\bhands holding (\w[\w\s]*)',           r'close-up of \1, shallow depth of field'),
    (r'\bperson looking at (\w[\w\s]*)',       r'close-up of \1, bokeh background'),
    (r'\bperson pointing at (\w[\w\s]*)',      r'\1 highlighted on screen, close-up'),
    (r'\bperson pointing to (\w[\w\s]*)',      r'\1 displayed prominently, close-up'),
    (r'\bperson using (\w[\w\s]*)',            r'close-up of \1 in use, no hands'),
    (r'\bperson typing on (\w[\w\s]*)',        r'\1 keyboard close-up, no hands'),
    (r'\bperson typing',                       r'keyboard close-up, keys in focus'),
    (r'\bperson reading (\w[\w\s]*)',          r'\1 text close-up, shallow depth'),
    (r'\bperson scanning (\w[\w\s]*)',         r'\1 document close-up, crisp detail'),
    (r'\bperson signing (\w[\w\s]*)',          r'pen resting on \1, close-up'),
    (r'\bperson writing',                      r'pen on paper, close-up, ink flowing'),
    (r'\bperson checking (\w[\w\s]*)',         r'\1 displayed on screen, close-up'),
    (r'\bperson scrolling',                    r'phone screen scrolling, close-up'),
    (r'\bperson opening (\w[\w\s]*)',          r'\1 open on desk, close-up'),
    (r'\bperson examining (\w[\w\s]*)',        r'\1 close-up, macro lens'),
    (r'\bperson reviewing (\w[\w\s]*)',        r'\1 spread on desk, overhead shot'),
    # Generic action cleanup
    (r'\bcounting\b',                          r'arranged neatly'),
    (r'\bholding\b',                           r'placed on surface'),
    (r'\bgrabbing\b',                          r'positioned'),
    (r'\bscratching\b',                        r''),
    (r'\btouching\b',                          r'near'),
    (r'\bpicking up\b',                        r'on surface'),
]

# Stability keywords appended to every Veo prompt
_STABILITY = (
    "static camera, no camera movement, "
    "photorealistic, hyperrealistic, "
    "no morphing, no distortion, "
    "physically accurate, consistent lighting"
)


# ── SSL ───────────────────────────────────────────────────────────────────────

def _ssl_ctx() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# ── Prompt transformation ─────────────────────────────────────────────────────

def _veo_safe_prompt(prompt: str) -> str:
    """
    Rewrite action-based prompts to scene-based descriptions.

    AI video models break when asked to show multi-step actions
    (e.g. 'person counting money then scratching nose' → money disappears).
    Scene descriptions (objects, environments, close-ups) are stable.

    Rules:
      - Strip action verbs: counting, holding, touching, scratching, ...
      - Replace person+action with object/environment close-up
      - Append stability keywords (static camera, no morphing, ...)
    """
    p = prompt.strip()
    for pattern, replacement in _ACTION_RULES:
        p = re.sub(pattern, replacement, p, flags=re.IGNORECASE)

    # Clean up double spaces/commas left by empty replacements
    p = re.sub(r',\s*,', ',', p)
    p = re.sub(r'\s{2,}', ' ', p).strip().strip(',').strip()

    # Append stability keywords if not already present
    if "static camera" not in p.lower():
        p = f"{p}, {_STABILITY}"

    return p


def _enrich_prompt(prompt: str, niche: str) -> str:
    """Append niche-specific cinematic style to the broll_prompt."""
    style_suffixes = {
        "finance":          "warm colour grade, shallow depth of field, 4K, golden hour",
        "entrepreneurship": "natural light, clean office aesthetic, 4K",
        "health":           "bright clean aesthetic, soft natural light, 4K",
        "tech":             "sleek modern, blue-tinted ambient light, sharp focus, 4K",
        "mindset":          "moody atmosphere, golden hour, contemplative, 4K",
        "productivity":     "clean minimal workspace, natural light, 4K",
        "ai":               "futuristic glow, blue-purple ambient light, sharp crisp, 4K",
        "marketing":        "bold vibrant colours, high contrast, professional, 4K",
        "fitness":          "warm golden tones, gym aesthetic, dramatic lighting, 4K",
        "relationships":    "warm intimate, soft bokeh background, authentic, 4K",
    }
    suffix = style_suffixes.get(niche, "cinematic, 4K, professional, dramatic lighting")
    # Don't double-add if already enriched
    if "4K" in prompt or "cinematic" in prompt.lower():
        return prompt
    return f"{prompt}, {suffix}"


# ── Core generation ───────────────────────────────────────────────────────────

def generate_clip(prompt: str, dest_path: str, duration: int = DEFAULT_DURATION,
                  best_of: int = 2) -> str:
    """
    Generate a Veo 3.1 clip from prompt. Saves to dest_path.

    best_of: generate N candidates, keep the largest file.
             Larger file = more visual detail = less likely to be glitchy.
             Default: 2. Set to 1 to halve API cost.

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

    n = max(1, min(best_of, 2))   # clamp 1-2
    print(f"  [VEO3.1/{VEO_MODEL}] Generating {n} candidate(s): {prompt[:80]}...")

    # API only supports number_of_videos=1 — run sequentially for best_of=2
    candidate_paths = []
    for attempt in range(n):
        tmp = dest_path + f".candidate_{attempt}.mp4"

        operation = client.models.generate_videos(
            model=VEO_MODEL,
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
                raise RuntimeError(f"Veo 3.1 timed out after {MAX_WAIT_SECONDS}s")
            time.sleep(POLL_INTERVAL_SECS)
            waited += POLL_INTERVAL_SECS
            operation = client.operations.get(operation)
            print(f"  [VEO3.1] Candidate {attempt+1} waiting... ({waited}s)")

        videos = operation.result.generated_videos
        if not videos:
            print(f"  [VEO3.1] Candidate {attempt+1}: no video returned, skipping")
            continue

        video = videos[0].video
        if not video:
            continue

        if video.uri:
            _download_uri(video.uri, tmp, api_key)
        elif video.video_bytes:
            Path(tmp).write_bytes(video.video_bytes)
        else:
            continue

        size = os.path.getsize(tmp)
        print(f"  [VEO3.1] Candidate {attempt+1}: {size//1024}KB")
        candidate_paths.append((size, tmp))

    if not candidate_paths:
        raise RuntimeError("Veo 3.1: all candidates empty")

    # Pick largest (most visual content = least likely glitchy)
    candidate_paths.sort(reverse=True)
    best_size, best_path = candidate_paths[0]

    import shutil
    shutil.move(best_path, dest_path)
    # Clean up other candidates
    for _, tmp in candidate_paths[1:]:
        if os.path.exists(tmp):
            os.unlink(tmp)

    print(f"  [VEO3.1] ✓ Best candidate: {best_size//1024}KB → {dest_path}")
    return dest_path


def _download_uri(uri: str, dest_path: str, api_key: str):
    """Download a Veo clip from the Gemini Files API URI."""
    req = urllib.request.Request(uri, headers={"x-goog-api-key": api_key})
    with urllib.request.urlopen(req, timeout=120, context=_ssl_ctx()) as resp:
        data = resp.read()
    with open(dest_path, "wb") as f:
        f.write(data)


def _write_mock_clip(dest_path: str, duration: int = DEFAULT_DURATION):
    """Write a silent black MP4 stub using FFmpeg (MOCK_APIS=true)."""
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


# ── Pipeline entry point ──────────────────────────────────────────────────────

def fetch_broll_veo2(job: dict) -> dict:
    """
    Generate Veo 3.1 clips for all scenes in a job.
    Pipeline:
      1. _veo_safe_prompt()  — strip actions, add stability keywords
      2. _enrich_prompt()    — add niche-specific visual style
      3. generate_clip()     — HQ model, best_of=2, pick largest
    """
    job_dir = os.path.abspath(os.path.join(JOBS_DIR, job["job_id"]))
    os.makedirs(job_dir, exist_ok=True)

    for scene in job.get("scenes", []):
        scene_id   = scene["scene_id"]
        broll_path = os.path.join(job_dir, f"{scene_id}_broll.mp4")
        raw_prompt = scene.get("broll_prompt", "cinematic environment, 9:16 vertical")

        # Step 1: make it Veo-safe (action → scene)
        safe   = _veo_safe_prompt(raw_prompt)
        # Step 2: add niche visual style
        final  = _enrich_prompt(safe, job.get("niche", ""))

        print(f"  [VEO3.1] {scene_id} prompt: {final[:100]}...")

        try:
            generate_clip(final, broll_path, best_of=2)
            scene["broll_path"]        = broll_path
            scene["broll_source"]      = "veo3.1"
            scene["broll_prompt_used"] = final
            scene["broll_meta"]        = {
                "source": "veo3.1",
                "model":  VEO_MODEL,
                "best_of": 2,
                "original_prompt": raw_prompt,
                "safe_prompt": final,
            }
        except Exception as e:
            print(f"  [WARN] Veo 3.1 failed for {scene_id}: {e}")
            scene["broll_path"]   = None
            scene["broll_source"] = "veo_failed"
            scene["broll_meta"]   = {"source": "veo_failed", "reason": str(e)}

    return job
