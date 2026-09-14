"""
Phase 2c: B-Roll acquisition — Pexels stock video (primary source)
"""
import os
import json
import urllib.request
import urllib.parse
import urllib.error

MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
JOBS_DIR = os.getenv("JOBS_DIR", "./data/jobs")

PEXELS_HEADERS = {
    "Authorization": PEXELS_API_KEY or os.getenv("PEXELS_API_KEY", ""),
    "User-Agent": "VideoMaker/1.0 (personal automation tool)",
    "Accept": "application/json",
}


def fetch_broll_for_job(job: dict) -> dict:
    """
    For each scene, search Pexels for a matching video clip.
    Adds 'broll_path' to each scene in the job.
    """
    # Re-read key at call time (supports late env loading)
    api_key = os.getenv("PEXELS_API_KEY", "")
    mock = os.getenv("MOCK_APIS", "true").lower() == "true"

    for scene in job["scenes"]:
        scene_id = scene["scene_id"]
        job_dir = os.path.abspath(os.path.join(JOBS_DIR, job['job_id']))
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
        with urllib.request.urlopen(req, timeout=15) as resp:
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

    # Prefer HD (1280x720), then FHD, then whatever we get
    def quality_rank(f):
        q = f.get("quality", "")
        if q == "hd": return 0
        if q == "sd": return 1
        return 2

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
    """Download a video from URL to dest path with progress logging."""
    print(f"  Downloading → {dest} ...")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.pexels.com/",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        with open(dest, "wb") as f:
            f.write(resp.read())
    size = os.path.getsize(dest)
    print(f"  Done — {size:,} bytes ({size // 1024} KB)")
