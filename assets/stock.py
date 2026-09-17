"""
Phase 2c: B-Roll acquisition — Pexels stock video (primary source)
"""
import os
import json
import ssl
import urllib.request
import urllib.parse
import urllib.error

from pathlib import Path

_ROOT = Path(__file__).parent.parent
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
# NOTE: MOCK_APIS and JOBS_DIR are read lazily inside functions (os.getenv at call time)
# so that monkeypatching in tests takes effect. Do NOT cache them at module level.


def _ssl_context() -> ssl.SSLContext:
    """
    Build an SSL context using certifi's CA bundle.
    Python on Windows sometimes has an empty/broken system trust store,
    which causes 'certificate chain ... not trusted' errors mid-pipeline.
    certifi ships a stable Mozilla bundle that sidesteps that entirely.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_broll_pexels(job: dict) -> dict:
    """
    For each scene, search Pexels for a matching video clip.
    Adds 'broll_path' to each scene in the job.
    """
    # Re-read key at call time (supports late env loading)
    api_key = os.getenv("PEXELS_API_KEY", "")
    mock = os.getenv("MOCK_APIS", "true").lower() == "true"
    jobs_dir = os.getenv("JOBS_DIR", str(_ROOT / "data" / "jobs"))

    for scene in job["scenes"]:
        scene_id = scene["scene_id"]
        job_dir = os.path.abspath(os.path.join(jobs_dir, job['job_id']))
        os.makedirs(job_dir, exist_ok=True)
        broll_path = os.path.join(job_dir, f"{scene_id}_broll.mp4")

        if mock:
            with open(broll_path, "wb") as f:
                f.write(b"MOCK_BROLL_MP4")
            scene["broll_path"] = broll_path
            scene["broll_meta"] = {"source": "mock"}
            print(f"[MOCK] B-roll for {scene_id} → {broll_path}")
        else:
            result = _search_pexels(scene["broll_prompt"], api_key)
            if result:
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
                print(f"✓ B-roll [{scene_id}] — {result['photographer']} — {result['duration']}s")
            else:
                scene["broll_path"] = None
                scene["broll_meta"] = {"source": "none", "reason": "no results"}
                print(f"[WARN] No B-roll found for {scene_id}: {scene['broll_prompt']}")

    return job


def _search_pexels(query: str, api_key: str = None) -> dict | None:
    """
    Search Pexels Videos API.
    Returns a dict with: url, video_id, photographer, pexels_url, width, height, duration
    or None if no results.
    """
    key = api_key or os.getenv("PEXELS_API_KEY", "")
    encoded = urllib.parse.quote(query)
    url = f"https://api.pexels.com/videos/search?query={encoded}&per_page=5&orientation=landscape"

    req = urllib.request.Request(url, headers={
        "Authorization": key,
        "User-Agent": "VideoMaker/1.0",
        "Accept": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=15, context=_ssl_context()) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"[ERROR] Pexels API returned {e.code}: {e.reason}")
        return None
    except Exception as e:
        print(f"[ERROR] Pexels request failed: {e}")
        return None

    videos = data.get("videos", [])
    if not videos:
        return None

    video = videos[0]
    files = video.get("video_files", [])

    # Prefer FHD (1920×1080), then HD (1280×720), then SD
    def quality_rank(f):
        q = f.get("quality", "")
        if q == "fhd": return 0
        if q == "hd":  return 1
        if q == "sd":  return 2
        return 3

    files_sorted = sorted(files, key=quality_rank)
    chosen = files_sorted[0] if files_sorted else None
    if not chosen:
        return None

    return {
        "url": chosen["link"],
        "video_id": video["id"],
        "photographer": video.get("user", {}).get("name", "Unknown"),
        "pexels_url": video.get("url", ""),
        "width": chosen.get("width", 0),
        "height": chosen.get("height", 0),
        "duration": video.get("duration", 0),
    }


def _download_video(url: str, dest: str):
    """Download a video from URL to dest path using chunked streaming (no RAM spike)."""
    import shutil
    print(f"  Downloading → {dest} ...")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.pexels.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as resp:
            with open(dest, "wb") as f:
                shutil.copyfileobj(resp, f, length=1024 * 256)  # 256KB chunks
    except Exception as e:
        # Clean up partial file on failure
        try:
            os.unlink(dest)
        except OSError:
            pass
        raise RuntimeError(f"Download failed for {url}: {e}") from e
    size = os.path.getsize(dest)
    print(f"  Done — {size:,} bytes ({size // 1024} KB)")


# Backward-compat alias — existing imports still work during transition
fetch_broll_for_job = fetch_broll_pexels
