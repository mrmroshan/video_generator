"""
Phase 4: Renderer — FFmpeg pipeline
  1. Compose B-roll + audio per scene (exact audio duration)
  2. Extract WAV from composed clip → run Whisper on that → perfect sync
  3. Burn captions (static or karaoke) into each scene
  4. Concat all scenes → master output
  5. Crop/letterbox master to any platform size (no re-encode, just filters)

PLATFORM SIZES (all from a single master 1280×720 render):
  youtube   — 1280×720  (16:9)
  tiktok    — 720×1280  (9:16)  ← also Instagram/Facebook Reels
  instagram — 720×720   (1:1)   ← Facebook Post square
  facebook  — 1280×720  (16:9)  ← Facebook video post (landscape)

Karaoke sync fix:
  We used to run Whisper on the original MP3, which has a 25ms start_time
  offset AND accumulates an AAC encoder delay (~23ms) during compose.
  We now extract audio directly from the composed MP4 (after encoding) and
  run Whisper on that — the timestamps are guaranteed to match the encoded
  video timeline perfectly.
"""
import os
import json
import subprocess
from pathlib import Path

_ROOT     = Path(__file__).parent.parent
JOBS_DIR  = os.getenv("JOBS_DIR",  str(_ROOT / "data" / "jobs"))
MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"

DEFAULT_CAPTION_STYLE = "clean"

# ── Platform specs ────────────────────────────────────────────────────
# Each entry: (width, height, label, description)
PLATFORMS = {
    "youtube":   (1280, 720,  "YouTube",          "16:9 landscape — standard YouTube/Facebook video"),
    "tiktok":    (720,  1280, "TikTok",           "9:16 vertical — TikTok, Instagram Reels, Facebook Reels"),
    "instagram": (720,  720,  "Instagram Square", "1:1 square — Instagram/Facebook post"),
    "facebook":  (1280, 720,  "Facebook",         "16:9 landscape — Facebook video post"),
}

# Aliases: any of these map to the canonical platform key
PLATFORM_ALIASES = {
    "ig": "instagram", "ig_square": "instagram", "fb_post": "instagram",
    "fb": "facebook",  "fb_video": "facebook",
    "reels": "tiktok", "shorts": "tiktok", "fb_reels": "tiktok",
}

def _canonical_platform(name: str) -> str:
    name = (name or "youtube").lower().strip()
    return PLATFORM_ALIASES.get(name, name if name in PLATFORMS else "youtube")


# ── Public API ────────────────────────────────────────────────────────

def render_job(job: dict, caption_style: str = None) -> str:
    """Render approved job → master output.mp4. Returns path."""
    if job["status"] != "approved":
        raise PermissionError(
            f"Job {job['job_id']} is not approved (status={job['status']}). Cannot render."
        )
    if MOCK_APIS:
        job_dir = os.path.join(JOBS_DIR, job["job_id"])
        os.makedirs(job_dir, exist_ok=True)
        out = os.path.join(job_dir, "output.mp4")
        with open(out, "wb") as f: f.write(b"MOCK_OUTPUT_MP4")
        print(f"[MOCK] Rendered → {out}")
        return out
    return _render_ffmpeg(job, caption_style=caption_style)


def export_platform(job: dict, platform: str) -> str:
    """
    Crop/letterbox the master (caption-free) to a platform size,
    then burn captions sized for that exact resolution.
    Returns path to the platform-specific file.
    """
    platform = _canonical_platform(platform)
    if platform not in PLATFORMS:
        raise ValueError(f"Unknown platform: {platform}")

    job_dir = os.path.join(JOBS_DIR, job["job_id"])
    # Use the uncaptioned master for cropping so we can burn correct-sized captions
    master_nocap = os.path.join(job_dir, "output_nocap.mp4")
    master       = os.path.join(job_dir, "output.mp4")

    # Prefer the caption-free master; fall back to the captioned one
    src = master_nocap if os.path.exists(master_nocap) else master
    if not os.path.exists(src):
        raise FileNotFoundError(f"Master not found: {src} — run render_job first")

    w, h, label, _ = PLATFORMS[platform]
    out      = os.path.join(job_dir, f"output_{platform}.mp4")
    out_crop = os.path.join(job_dir, f"output_{platform}_crop.mp4")

    # Probe source dimensions
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-select_streams", "v:0", src],
        capture_output=True, text=True
    )
    vstream = next(
        (s for s in json.loads(r.stdout).get("streams", []) if s.get("codec_type") == "video"),
        {"width": 1280, "height": 720}
    )
    src_w, src_h = vstream["width"], vstream["height"]

    # Step 1: crop/scale to platform size (no captions yet)
    vf = _platform_vf(src_w, src_h, w, h)
    print(f"  Cropping [{label}] {w}×{h}...", end=" ", flush=True)
    r = subprocess.run([
        "ffmpeg", "-y", "-i", src,
        "-vf", vf,
        "-c:v", "libx264", "-profile:v", "baseline", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        out_crop,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Crop failed for {platform}:\n{r.stderr[-400:]}")

    # Step 2: burn captions sized for this exact resolution
    caption_style = job.get("caption_style", "karaoke")
    use_karaoke   = caption_style.startswith("karaoke")

    if use_karaoke and any(s.get("timestamps") for s in job.get("scenes", [])):
        # Rebuild per-platform karaoke: concatenate all scene timestamp lists
        # with cumulative offsets matching the cropped video timeline
        _burn_karaoke_platform(job, out_crop, out, w, h, caption_style)
        try: os.unlink(out_crop)
        except: pass
    else:
        # Static captions or no timestamps — simple rename
        os.replace(out_crop, out)

    sz = os.path.getsize(out) // 1024
    print(f"{sz}KB ✓")
    return out


def _burn_karaoke_platform(job: dict, video_in: str, video_out: str,
                            width: int, height: int, style: str):
    """
    Burn karaoke captions into a full-length platform video.
    Timestamps are stitched across all scenes with cumulative time offsets.
    """
    from renderer.captions import make_karaoke_ass, burn_karaoke
    import tempfile

    # Build a single word list for the whole video with cumulative offsets
    all_words = []
    t_offset  = 0.0
    for scene in job.get("scenes", []):
        ts  = scene.get("timestamps", [])
        dur = scene.get("actual_duration", scene.get("target_duration_seconds", 5.0))
        for w in ts:
            all_words.append({
                "word":  w["word"],
                "start": w["start"] + t_offset,
                "end":   w["end"]   + t_offset,
            })
        t_offset += dur

    if not all_words:
        # No timestamps — just pass through unchanged
        import shutil
        shutil.move(video_in, video_out)
        return

    # Probe total duration of the cropped video
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", video_in],
        capture_output=True, text=True
    )
    total_dur = max(
        (float(s["duration"]) for s in json.loads(r.stdout).get("streams", []) if "duration" in s),
        default=t_offset
    )

    burn_karaoke(video_in, all_words, total_dur,
                 style=style, out_path=video_out,
                 audio_path=None, width=width, height=height)


def export_all_platforms(job: dict) -> dict:
    """Export master to all 4 platform sizes. Returns {platform: path}."""
    results = {}
    for platform in PLATFORMS:
        try:
            results[platform] = export_platform(job, platform)
        except Exception as e:
            print(f"  [WARN] {platform} export failed: {e}")
            results[platform] = None
    return results


# ── Platform video filter ─────────────────────────────────────────────

def _platform_vf(src_w: int, src_h: int, dst_w: int, dst_h: int) -> str:
    """
    Build an ffmpeg -vf string that converts src to dst dimensions.
    Strategy:
      - Same AR: just scale
      - Wider src (landscape→portrait): scale to height, crop width (centre)
      - Taller src (portrait→landscape): scale to width, pad height (black bars)
      - Square target: scale to longest side, pad shorter side
    """
    src_ar = src_w / src_h
    dst_ar = dst_w / dst_h

    if abs(src_ar - dst_ar) < 0.02:
        # Same aspect ratio — just scale
        return f"scale={dst_w}:{dst_h}"

    if src_ar > dst_ar:
        # Src is wider than dst (e.g. 16:9 → 9:16 or 1:1)
        # Scale to match height, then centre-crop to width
        scale_h = dst_h
        scale_w = -2  # keep AR
        return (
            f"scale={scale_w}:{scale_h},"
            f"crop={dst_w}:{dst_h}"
        )
    else:
        # Src is taller than dst (e.g. 9:16 → 16:9)
        # Scale to match width, letterbox (pad) to height
        scale_w = dst_w
        scale_h = -2
        return (
            f"scale={scale_w}:{scale_h},"
            f"pad={dst_w}:{dst_h}:(ow-iw)/2:(oh-ih)/2:black"
        )


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


def _extract_wav_from_composed(composed_path: str, wav_path: str):
    """Extract PCM WAV from the composed MP4 — Whisper timestamps will perfectly match."""
    r = subprocess.run([
        "ffmpeg", "-y", "-i", composed_path,
        "-map", "0:a:0", "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1",
        wav_path,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"WAV extraction failed:\n{r.stderr[-200:]}")


def _render_ffmpeg(job: dict, caption_style: str = None) -> str:
    """
    Per-scene pipeline:
      1. Compose B-roll + MP3 → scene_XX_composed.mp4
      2. Extract WAV from composed → scene_XX.wav
      3. Run Whisper on WAV (timestamps now aligned to encoded video)
      4. Burn captions (karaoke or static) into composed → scene_XX_captioned.mp4
    Then concat all captioned scenes → output.mp4
    """
    style = caption_style or job.get("caption_style", DEFAULT_CAPTION_STYLE)

    job_id  = job["job_id"]
    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    output  = os.path.join(job_dir, "output.mp4")

    # Always render master at 1280×720 regardless of platform
    # Platform-specific exports happen via export_platform()
    width, height = 1280, 720
    use_karaoke = style.startswith("karaoke")

    scene_files = []

    for scene in job["scenes"]:
        sid = scene["scene_id"]
        bp  = scene.get("broll_path", "")
        ap  = scene.get("audio_path", "")

        if not bp or not os.path.exists(bp):
            print(f"  [WARN] {sid}: missing broll — skipping"); continue
        if not ap or not os.path.exists(ap):
            print(f"  [WARN] {sid}: missing audio — skipping"); continue

        audio_dur = _get_audio_duration(ap)
        composed  = os.path.join(job_dir, f"{sid}_composed.mp4")

        # ── Step 1: compose ──────────────────────────────────────────
        print(f"  {sid} compose ({audio_dur:.2f}s)...", end=" ", flush=True)
        r = subprocess.run([
            "ffmpeg", "-y",
            "-i", bp, "-i", ap,
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

        # ── Step 2+3: karaoke timestamps from composed audio ─────────
        if use_karaoke and not scene.get("timestamps"):
            wav = os.path.join(job_dir, f"{sid}.wav")
            print(f"extracting WAV...", end=" ", flush=True)
            try:
                _extract_wav_from_composed(composed, wav)
                scene_for_ts = {"scene_id": sid, "audio_path": wav,
                                 "voiceover_text": scene.get("voiceover_text", "")}
                from audio.timestamps import extract_timestamps
                extract_timestamps(scene_for_ts)
                scene["timestamps"] = scene_for_ts["timestamps"]
                print(f"{len(scene['timestamps'])} words", end=" ", flush=True)
                try: os.unlink(wav)
                except: pass
            except Exception as e:
                print(f"[WARN Whisper: {e}]", end=" ", flush=True)
                use_karaoke = False

        # ── Step 4: burn captions ────────────────────────────────────
        captioned = os.path.join(job_dir, f"{sid}_captioned.mp4")
        if use_karaoke and scene.get("timestamps"):
            from renderer.captions import burn_karaoke
            # No audio_offset needed — WAV was extracted from composed, ts=0 aligned
            burn_karaoke(composed, scene["timestamps"], audio_dur,
                         style=style, out_path=captioned,
                         audio_path=None, width=width, height=height)
        else:
            from renderer.captions import burn_captions
            static = style if not use_karaoke else "clean"
            burn_captions(composed, scene.get("voiceover_text", ""), audio_dur,
                          style=static, out_path=captioned)

        print(f"{os.path.getsize(captioned)//1024}KB ✓")
        scene["composed_path"]   = composed
        scene["captioned_path"]  = captioned
        scene["actual_duration"] = audio_dur
        scene_files.append(captioned)

    if not scene_files:
        raise RuntimeError("No scenes rendered successfully")

    # Concat all scenes → caption-free master (used by export_platform for per-platform captions)
    nocap_output = os.path.join(job_dir, "output_nocap.mp4")
    concat_file  = os.path.join(job_dir, "concat_nocap.txt")
    composed_files = [scene["composed_path"] for scene in job["scenes"]
                      if scene.get("composed_path") and os.path.exists(scene.get("composed_path",""))]
    if composed_files:
        with open(concat_file, "w") as f:
            for sf in composed_files:
                f.write(f"file '{os.path.abspath(sf).replace(chr(92),'/')}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", nocap_output],
            capture_output=True, text=True
        )

    # Concat captioned scenes → final output.mp4
    concat_file = os.path.join(job_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for sf in scene_files:
            f.write(f"file '{os.path.abspath(sf).replace(chr(92),'/')}'\n")

    print(f"  Concatenating {len(scene_files)} scenes...", end=" ", flush=True)
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", output],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"Concat failed:\n{r.stderr[-400:]}")
    print(f"{os.path.getsize(output)//1024//1024}MB ✓")
    return output


# ── Remotion (future) ─────────────────────────────────────────────────

def _render_remotion(job: dict) -> str:
    raise NotImplementedError("Remotion not wired. Use renderer='ffmpeg' or MOCK_APIS=true.")
