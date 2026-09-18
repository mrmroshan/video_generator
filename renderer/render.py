"""
Phase 4: Renderer — FFmpeg pipeline
  1. Compose B-roll + audio per scene (exact audio duration)
  2. Extract WAV from composed clip → run Whisper on that → perfect sync
  3. Burn captions (static or karaoke) into each scene
  4. Concat all scenes → master output
  5. Crop/letterbox master to any platform size (no re-encode, just filters)

PLATFORM SIZES (all from a single master 720×1280 render):
  All platforms export as Shorts/Reels — 9:16 vertical (720×1280).
  youtube, tiktok, instagram, facebook — all identical dimensions.
  One master render, copied to all selected platforms (no crop).

  NOTE: Master stays at 720p (baseline level 3.1 cap = ~3600 macroblocks).
  Upgrading to 1080p requires -level 4.0+ — tracked as future work.

Karaoke sync fix:
  We used to run Whisper on the original MP3, which has a 25ms start_time
  offset AND accumulates an AAC encoder delay (~23ms) during compose.
  We now extract audio directly from the composed MP4 (after encoding) and
  run Whisper on that — the timestamps are guaranteed to match the encoded
  video timeline perfectly.

SINGLE SOURCE OF TRUTH:
  VALID_PLATFORMS — import this everywhere instead of redefining locally.
  PLATFORMS       — full spec dict for export. Add new formats here only.
"""
import os
import json
import subprocess
from pathlib import Path

_ROOT     = Path(__file__).parent.parent
JOBS_DIR  = os.getenv("JOBS_DIR",  str(_ROOT / "data" / "jobs"))
MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"

DEFAULT_CAPTION_STYLE = "none"

# ── Platform specs ────────────────────────────────────────────────────
# Each entry: (width, height, label, description)
PLATFORMS = {
    # ── Short-form vertical (9:16) — all derived from 720×1280 master ──
    "tiktok":             (720, 1280, "TikTok",             "9:16 · Vertical"),
    "youtube_shorts":     (720, 1280, "YouTube Shorts",     "9:16 · Shorts"),
    "instagram_reels":    (720, 1280, "Instagram Reels",    "9:16 · Reels"),
    "facebook_reels":     (720, 1280, "Facebook Reels",     "9:16 · Reels"),
    # ── Square (1:1) — center-crop from 720×1280 master ────────────────
    "instagram_square":   (720,  720, "Instagram Square",   "1:1 · Feed"),
    "facebook_square":    (720,  720, "Facebook Square",    "1:1 · Feed"),
    # ── Portrait (4:5) — center-crop from 720×1280 master ──────────────
    "instagram_portrait": (720,  900, "Instagram Portrait", "4:5 · Feed"),
    # ── Backward-compat aliases — kept so existing jobs don't break ─────
    "youtube":   (720, 1280, "YouTube",   "9:16 · Shorts"),
    "instagram": (720, 1280, "Instagram", "9:16 · Reels"),
    "facebook":  (720, 1280, "Facebook",  "9:16 · Reels"),
}

# SINGLE SOURCE OF TRUTH: import this from render.py everywhere.
# Never redefine VALID_PLATFORMS in server.py, pipeline.py, or tests.
VALID_PLATFORMS: frozenset = frozenset(PLATFORMS.keys())

# ── Platform groups (used by /api/platforms for the UI picker) ─────────
# Each group = one platform brand; each format = one exportable size.
# available=False → shown in UI as "Coming soon" (grayed out).
PLATFORM_GROUPS: dict = {
    "tiktok": {
        "label": "TikTok", "icon": "🎵",
        "formats": [
            {"key": "tiktok",         "label": "Vertical",  "desc": "9:16 · Vertical",    "available": True,  "default": True},
        ],
    },
    "youtube": {
        "label": "YouTube", "icon": "▶️",
        "formats": [
            {"key": "youtube_shorts", "label": "Shorts",    "desc": "9:16 · Shorts",       "available": True,  "default": True},
            {"key": "youtube_long",   "label": "Long-form", "desc": "16:9 · Main channel", "available": False, "default": False},
        ],
    },
    "instagram": {
        "label": "Instagram", "icon": "📸",
        "formats": [
            {"key": "instagram_reels",    "label": "Reels",    "desc": "9:16 · Reels", "available": True,  "default": True},
            {"key": "instagram_square",   "label": "Square",   "desc": "1:1 · Feed",   "available": True,  "default": False},
            {"key": "instagram_portrait", "label": "Portrait", "desc": "4:5 · Feed",   "available": True,  "default": False},
        ],
    },
    "facebook": {
        "label": "Facebook", "icon": "👥",
        "formats": [
            {"key": "facebook_reels",  "label": "Reels",   "desc": "9:16 · Reels", "available": True,  "default": True},
            {"key": "facebook_square", "label": "Square",  "desc": "1:1 · Feed",   "available": True,  "default": False},
        ],
    },
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
    _mock = os.getenv("MOCK_APIS", "true").lower() == "true"
    if job["status"] != "approved":
        raise PermissionError(
            f"Job {job['job_id']} is not approved (status={job['status']}). Cannot render."
        )
    if _mock:
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

    # Mock mode: evaluate lazily so monkeypatched env vars in tests take effect
    if os.getenv("MOCK_APIS", "true").lower() == "true":
        out = os.path.join(job_dir, f"output_{platform}.mp4")
        os.makedirs(job_dir, exist_ok=True)
        with open(out, "wb") as f:
            f.write(b"MOCK_EXPORT_" + platform.encode())
        print(f"[MOCK] Exported {platform} → {out}")
        return out
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
    try:
        vstream = next(
            (s for s in json.loads(r.stdout).get("streams", []) if s.get("codec_type") == "video"),
            {"width": 1280, "height": 720}
        )
    except (json.JSONDecodeError, StopIteration):
        vstream = {"width": 1280, "height": 720}
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

    # Step 2: burn captions sized for this exact resolution (skip if none)
    caption_style = job.get("caption_style", "none")
    use_captions  = caption_style != "none"
    use_karaoke   = use_captions and caption_style.startswith("karaoke")

    if use_karaoke and any(s.get("timestamps") for s in job.get("scenes", [])):
        _burn_karaoke_platform(job, out_crop, out, w, h, caption_style)
        try: os.unlink(out_crop)
        except: pass
    else:
        # No captions or static — just use the cropped file as-is
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
      - Same AR (within 2%): just scale
      - Src wider than dst (landscape→portrait or landscape→square):
          scale to match height, then centre-crop width
      - Src taller than dst (portrait→square or portrait→landscape):
          scale to match width, then centre-crop height  ← key fix for 9:16→1:1
      - Exact same size: passthrough scale

    Centre-crop ensures the subject stays centred in the frame — critical
    for captions (always at the bottom third) not getting cut off.
    """
    # Guard: ffprobe can return 0 on corrupt/stub files — fall back to scale only
    if src_h == 0 or src_w == 0:
        return f"scale={dst_w}:{dst_h}"

    src_ar = src_w / src_h
    dst_ar = dst_w / dst_h

    if abs(src_ar - dst_ar) < 0.02:
        # Same aspect ratio — just scale
        return f"scale={dst_w}:{dst_h}"

    if src_ar > dst_ar:
        # Src wider than dst → scale to dst height, centre-crop width
        return (
            f"scale=-2:{dst_h},"
            f"crop={dst_w}:{dst_h}"
        )
    else:
        # Src taller than dst (e.g. 9:16 → 1:1 or 9:16 → 4:5)
        # Scale to dst width, then centre-crop height to keep the middle of the frame
        return (
            f"scale={dst_w}:-2,"
            f"crop={dst_w}:{dst_h}"
        )


# ── FFmpeg renderer ───────────────────────────────────────────────────

def _get_audio_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
        capture_output=True, text=True,
    )
    try:
        for s in json.loads(r.stdout).get("streams", []):
            if s.get("codec_type") == "audio" and "duration" in s:
                return float(s["duration"])
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    return 5.0


def _get_video_duration(path: str) -> float:
    """Return duration of the first video stream in seconds (0.0 on failure)."""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
        capture_output=True, text=True,
    )
    try:
        for s in json.loads(r.stdout).get("streams", []):
            if s.get("codec_type") == "video" and "duration" in s:
                return float(s["duration"])
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    return 0.0


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

    # Master always renders at 720×1280 (9:16 vertical — Shorts/Reels format)
    # Platform-specific exports happen via export_platform() — most get the same file
    width, height = 720, 1280
    use_captions = style != "none"
    use_karaoke  = use_captions and style.startswith("karaoke")

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

        # Probe broll duration — loop if shorter than audio
        broll_dur = _get_video_duration(bp)
        need_loop = broll_dur > 0 and broll_dur < audio_dur

        # ── Step 1: compose ──────────────────────────────────────────
        print(f"  {sid} compose ({audio_dur:.2f}s, broll={broll_dur:.1f}s{'→loop' if need_loop else ''})...", end=" ", flush=True)

        video_input = ["-stream_loop", "-1", "-i", bp] if need_loop else ["-i", bp]

        r = subprocess.run([
            "ffmpeg", "-y",
            *video_input, "-i", ap,
            "-t", f"{audio_dur:.3f}",
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
            "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
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

        # ── Step 4: burn captions (skipped when style=="none") ───────
        captioned = os.path.join(job_dir, f"{sid}_captioned.mp4")
        if not use_captions:
            # No captions — use composed directly
            import shutil
            shutil.copy2(composed, captioned)
        elif use_karaoke and scene.get("timestamps"):
            from renderer.captions import burn_karaoke
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

    # Concat all scenes → caption-free master
    # IMPORTANT: use -reset_timestamps 1 so each scene's PTS is re-based from 0
    # before joining. Without this, broll clips that started mid-stream carry
    # their original PTS into the concat and cause multi-second freeze gaps.
    nocap_output = os.path.join(job_dir, "output_nocap.mp4")
    concat_file  = os.path.join(job_dir, "concat_nocap.txt")
    composed_files = [scene["composed_path"] for scene in job["scenes"]
                      if scene.get("composed_path") and os.path.exists(scene.get("composed_path",""))]
    if composed_files:
        with open(concat_file, "w") as f:
            for sf in composed_files:
                f.write(f"file '{os.path.abspath(sf).replace(chr(92),'/')}'\n")
                f.write("duration 0\n")  # hint to concat demuxer; actual dur read from file
        r_nocap = subprocess.run(
            ["ffmpeg", "-y",
             "-f", "concat", "-safe", "0", "-segment_time_metadata", "1",
             "-i", concat_file,
             "-vf", "setpts=N/FRAME_RATE/TB",
             "-af", "aselect=1,asetpts=N/SR/TB",
             "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
             "-preset", "fast", "-crf", "22",
             "-c:a", "aac", "-b:a", "128k",
             nocap_output],
            capture_output=True, text=True
        )
        if r_nocap.returncode != 0:
            # Fallback: plain copy (may have freeze if PTS mismatch)
            r_nocap = subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", nocap_output],
                capture_output=True, text=True
            )
        if r_nocap.returncode != 0:
            print(f"  [WARN] nocap concat failed (code {r_nocap.returncode}) — platform exports will use captioned master")

    # Concat captioned scenes → final output.mp4
    concat_file = os.path.join(job_dir, "concat.txt")
    with open(concat_file, "w") as f:
        for sf in scene_files:
            f.write(f"file '{os.path.abspath(sf).replace(chr(92),'/')}'\n")

    print(f"  Concatenating {len(scene_files)} scenes...", end=" ", flush=True)
    r = subprocess.run(
        ["ffmpeg", "-y",
         "-f", "concat", "-safe", "0",
         "-i", concat_file,
         "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
         "-preset", "fast", "-crf", "22",
         "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart",
         output],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"Concat failed:\n{r.stderr[-400:]}")
    print(f"{os.path.getsize(output)//1024//1024}MB ✓")
    return output


# ── Remotion (future) ─────────────────────────────────────────────────

def _render_remotion(job: dict) -> str:
    raise NotImplementedError("Remotion not wired. Use renderer='ffmpeg' or MOCK_APIS=true.")
