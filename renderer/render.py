"""
Phase 4: Renderer — FFmpeg (primary) or Remotion (future)
Composes B-roll + audio + burned-in captions for each scene, then concatenates.
"""
import os
import json
import subprocess
from pathlib import Path

_ROOT    = Path(__file__).parent.parent
JOBS_DIR = os.getenv("JOBS_DIR", str(_ROOT / "data" / "jobs"))
MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"

DEFAULT_CAPTION_STYLE = "clean"


def render_job(job: dict, caption_style: str = None) -> str:
    """
    Render the approved job into a final MP4 with burned-in captions.
    Returns path to output file.
    """
    if job["status"] != "approved":
        raise PermissionError(
            f"Job {job['job_id']} is not approved (status={job['status']}). Cannot render."
        )

    if MOCK_APIS:
        job_dir = os.path.join(JOBS_DIR, job["job_id"])
        os.makedirs(job_dir, exist_ok=True)
        output_path = os.path.join(job_dir, "output.mp4")
        with open(output_path, "wb") as f:
            f.write(b"MOCK_OUTPUT_MP4")
        print(f"[MOCK] Rendered → {output_path}")
        return output_path

    renderer = job.get("renderer", "ffmpeg")
    if renderer == "remotion":
        return _render_remotion(job)
    return _render_ffmpeg(job, caption_style=caption_style)


# ── FFmpeg renderer ───────────────────────────────────────────────────

def _get_audio_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
        capture_output=True, text=True,
    )
    for s in json.loads(r.stdout).get("streams", []):
        if s.get("codec_type") == "audio" and "duration" in s:
            return float(s["duration"])
    return 5.0


def _render_ffmpeg(job: dict, caption_style: str = None) -> str:
    """
    Per-scene:  crop/scale B-roll → trim to audio duration → burn captions
    Final step: concat all scenes → output.mp4
    """
    from renderer.captions import burn_captions, STYLES

    style    = caption_style or job.get("caption_style", DEFAULT_CAPTION_STYLE)
    if style not in STYLES and not style.startswith("karaoke"):
        style = DEFAULT_CAPTION_STYLE

    job_id   = job["job_id"]
    job_dir  = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    output   = os.path.join(job_dir, "output.mp4")

    platform  = job.get("platform", "youtube")
    # 720p avoids libx264 OOM on constrained hardware; still HD quality
    width, height = (720, 1280) if platform == "tiktok" else (1280, 720)

    scene_files = []

    for scene in job["scenes"]:
        sid = scene["scene_id"]
        bp  = scene.get("broll_path", "")
        ap  = scene.get("audio_path", "")

        if not bp or not os.path.exists(bp):
            print(f"  [WARN] {sid}: missing broll — skipping")
            continue
        if not ap or not os.path.exists(ap):
            print(f"  [WARN] {sid}: missing audio — skipping")
            continue

        audio_dur = _get_audio_duration(ap)
        composed  = os.path.join(job_dir, f"{sid}_composed.mp4")

        # Step 1: scale/crop B-roll + merge audio
        # Step 1: scale/crop B-roll + merge audio — direct subprocess, no bat file
        print(f"  {sid} compose ({audio_dur:.2f}s)...", end=" ", flush=True)
        r = subprocess.run([
            "ffmpeg", "-y",
            "-i", bp,
            "-i", ap,
            "-t", f"{audio_dur:.3f}",
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
            "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            composed,
        ], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"Compose failed for {sid}:\n{r.stderr[-400:]}")

        # Step 2: extract word timestamps (for karaoke) or skip
        caption_style = caption_style or job.get("caption_style", DEFAULT_CAPTION_STYLE)
        use_karaoke = caption_style.startswith("karaoke")

        if use_karaoke and not scene.get("timestamps"):
            print(f"  {sid} Whisper timestamps...", end=" ", flush=True)
            try:
                from audio.timestamps import extract_timestamps
                extract_timestamps(scene)
                print(f"{len(scene.get('timestamps', []))} words")
            except Exception as e:
                print(f"WARN ({e}) — falling back to static captions")
                use_karaoke = False

        # Step 3: burn captions
        captioned = os.path.join(job_dir, f"{sid}_captioned.mp4")
        if use_karaoke and scene.get("timestamps"):
            from renderer.captions import burn_karaoke
            burn_karaoke(composed, scene["timestamps"], audio_dur,
                         style=caption_style, out_path=captioned)
        else:
            from renderer.captions import burn_captions
            static = caption_style if not use_karaoke else "clean"
            burn_captions(composed, scene.get("voiceover_text", ""), audio_dur,
                          style=static, out_path=captioned)

        sz = os.path.getsize(captioned) // 1024
        print(f"{sz}KB ✓")

        scene["composed_path"]  = composed
        scene["captioned_path"] = captioned
        scene["actual_duration"] = audio_dur
        scene_files.append(captioned)

    if not scene_files:
        raise RuntimeError("No scenes rendered successfully")

    # Concat all scenes
    concat_file = os.path.join(job_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for sf in scene_files:
            # Always use forward slashes and absolute paths in concat files
            abs_sf = os.path.abspath(sf).replace("\\", "/")
            f.write(f"file '{abs_sf}'\n")

    print(f"  Concatenating {len(scene_files)} scenes...", end=" ", flush=True)
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", output],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"Concat failed:\n{r.stderr[-400:]}")

    sz = os.path.getsize(output)
    print(f"{sz // 1024 // 1024}MB ✓")
    return output


# ── Remotion renderer (future) ────────────────────────────────────────

def _render_remotion(job: dict) -> str:
    raise NotImplementedError(
        "Remotion renderer not yet wired. Use renderer='ffmpeg' or set MOCK_APIS=true."
    )
