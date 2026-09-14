"""
Captions renderer — generates ASS subtitle files and burns them into video via FFmpeg.

Styles:
  clean      — white bold Arial, black outline, bottom center  (YouTube)
  cinematic  — yellow on dark semi-transparent bar
  tiktok     — giant white Impact, thick outline, center screen
  minimal    — small light gray, no outline, bottom right

Usage:
    from renderer.captions import burn_captions
    out = burn_captions(video_path, caption_text, audio_duration, style='clean', out_path='scene.mp4')
"""

import os
import re
import math
import subprocess
import tempfile
from pathlib import Path

# ── Style definitions ─────────────────────────────────────────────────

STYLES = {
    "clean": {
        "font":         "Arial",
        "font_file":    r"C:\Windows\Fonts\arialbd.ttf",
        "size":         52,
        "primary":      "&H00FFFFFF",   # white
        "secondary":    "&H00FFFFFF",
        "outline_col":  "&H00000000",   # black
        "back_col":     "&H80000000",   # semi-transparent (not used in clean)
        "bold":         1,
        "italic":       0,
        "outline":      3.0,
        "shadow":       1.5,
        "alignment":    2,              # 2 = bottom center
        "margin_v":     60,
        "margin_l":     80,
        "margin_r":     80,
        "border_style": 1,              # 1 = outline + shadow
        "line_spacing": 8,
    },
    "cinematic": {
        "font":         "Arial",
        "font_file":    r"C:\Windows\Fonts\arialbd.ttf",
        "size":         48,
        "primary":      "&H00F5E642",   # yellow
        "secondary":    "&H00F5E642",
        "outline_col":  "&H00000000",
        "back_col":     "&HC0000000",   # 75% black box
        "bold":         1,
        "italic":       0,
        "outline":      0,
        "shadow":       0,
        "alignment":    2,
        "margin_v":     50,
        "margin_l":     80,
        "margin_r":     80,
        "border_style": 3,              # 3 = opaque box background
        "line_spacing": 8,
    },
    "tiktok": {
        "font":         "Impact",
        "font_file":    r"C:\Windows\Fonts\impact.ttf",
        "size":         72,
        "primary":      "&H00FFFFFF",   # white
        "secondary":    "&H00FFFFFF",
        "outline_col":  "&H00000000",   # thick black
        "back_col":     "&H00000000",
        "bold":         0,
        "italic":       0,
        "outline":      5.0,
        "shadow":       2.0,
        "alignment":    5,              # 5 = center screen (middle)
        "margin_v":     0,
        "margin_l":     60,
        "margin_r":     60,
        "border_style": 1,
        "line_spacing": 10,
    },
    "minimal": {
        "font":         "Arial",
        "font_file":    r"C:\Windows\Fonts\arial.ttf",
        "size":         36,
        "primary":      "&H00CCCCCC",   # light gray
        "secondary":    "&H00CCCCCC",
        "outline_col":  "&H00000000",
        "back_col":     "&H00000000",
        "bold":         0,
        "italic":       0,
        "outline":      1.0,
        "shadow":       0,
        "alignment":    2,
        "margin_v":     30,
        "margin_l":     60,
        "margin_r":     60,
        "border_style": 1,
        "line_spacing": 6,
    },
}

DEFAULT_STYLE = "clean"


# ── ASS file generation ───────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    """Convert float seconds to ASS timestamp H:MM:SS.cc  (round to avoid float precision errors)."""
    total_cs = round(seconds * 100)   # centiseconds, rounded — avoids 1.20→1.19 fp issues
    cs = total_cs % 100
    s  = (total_cs // 100) % 60
    m  = (total_cs // 6000) % 60
    h  = total_cs // 360000
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _wrap_text(text: str, max_chars: int = 38) -> str:
    """Wrap long caption lines at word boundaries."""
    words = text.split()
    lines, line = [], []
    for word in words:
        if sum(len(w) for w in line) + len(line) + len(word) > max_chars and line:
            lines.append(" ".join(line))
            line = [word]
        else:
            line.append(word)
    if line:
        lines.append(" ".join(line))
    return r"\N".join(lines)  # ASS line break


def make_ass(caption_text: str, duration: float, style_name: str = "clean") -> str:
    """
    Generate ASS subtitle file content for a single scene caption.
    The caption is displayed for the full scene duration with a 0.3s fade in/out.
    """
    st = STYLES.get(style_name, STYLES[DEFAULT_STYLE])
    text = _wrap_text(caption_text.strip(), max_chars=36 if style_name == "tiktok" else 42)

    fade_ms = 300
    start   = 0.0
    end     = max(duration - 0.1, 0.5)

    ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{st['font']},{st['size']},{st['primary']},{st['secondary']},{st['outline_col']},{st['back_col']},{st['bold']},{st['italic']},0,0,100,100,{st['line_spacing']},0,{st['border_style']},{st['outline']},{st['shadow']},{st['alignment']},{st['margin_l']},{st['margin_r']},{st['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,{_fmt_time(start)},{_fmt_time(end)},Default,,0,0,0,,{{\\fad({fade_ms},{fade_ms})}}{text}
"""
    return ass


# ── Main burn function ────────────────────────────────────────────────

def burn_captions(
    video_path: str,
    caption_text: str,
    audio_duration: float,
    style: str = "clean",
    out_path: str = None,
) -> str:
    """
    Burn styled captions into a video clip.
    Returns path to the output file.
    """
    if not out_path:
        base = os.path.splitext(video_path)[0]
        out_path = base + "_captioned.mp4"

    # Write ASS file
    ass_content = make_ass(caption_text, audio_duration, style)
    ass_file = video_path + ".captions.ass"
    with open(ass_file, "w", encoding="utf-8") as f:
        f.write(ass_content)

    # FFmpeg: burn subtitles
    # Use ass= filter — handles Windows paths, no shell escaping needed
    ass_escaped = ass_file.replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"ass='{ass_escaped}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        out_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    try:
        os.unlink(ass_file)
    except Exception:
        pass

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg caption burn failed:\n{result.stderr[-500:]}")

    return out_path


# ── Karaoke styles ────────────────────────────────────────────────────

KARAOKE_STYLES = {
    "karaoke": {
        # active word (highlighted)
        "font":         "Arial",
        "size":         60,
        "active_color": "&H0000FFFF",   # yellow
        "rest_color":   "&H00FFFFFF",   # white
        "outline_col":  "&H00000000",   # black outline
        "back_col":     "&H00000000",
        "bold":         1,
        "outline":      3.5,
        "shadow":       2.0,
        "alignment":    2,              # bottom center
        "margin_v":     80,
        "margin_l":     60,
        "margin_r":     60,
    },
    "karaoke_tiktok": {
        "font":         "Impact",
        "size":         78,
        "active_color": "&H0000FFFF",   # yellow
        "rest_color":   "&H00FFFFFF",   # white
        "outline_col":  "&H00000000",
        "back_col":     "&H00000000",
        "bold":         0,
        "outline":      5.0,
        "shadow":       2.0,
        "alignment":    5,              # center screen
        "margin_v":     0,
        "margin_l":     40,
        "margin_r":     40,
    },
    "karaoke_fire": {
        "font":         "Arial",
        "size":         64,
        "active_color": "&H000080FF",   # orange-red
        "rest_color":   "&H00E0E0E0",   # light gray
        "outline_col":  "&H00000000",
        "back_col":     "&H00000000",
        "bold":         1,
        "outline":      3.0,
        "shadow":       2.0,
        "alignment":    2,
        "margin_v":     80,
        "margin_l":     60,
        "margin_r":     60,
    },
}


def make_karaoke_ass(
    words: list,          # [{"word": str, "start": float, "end": float}, ...]
    total_duration: float,
    style_name: str = "karaoke",
    line_max_chars: int = 30,
    audio_offset: float = 0.0,   # MP3 start_time offset — shift all timestamps forward
) -> str:
    """
    Generate an ASS subtitle file with word-by-word karaoke highlighting.

    Sync fixes applied here:
    - audio_offset: compensates for MP3 start_time (e.g. 0.025s) so timestamps
      align with the composed video's 0-based timeline
    - Each word's Dialogue extends to the NEXT word's start (no blank gaps during
      natural speech pauses)
    - Last word of each phrase extends to the next phrase's first word start
      (caption stays visible across sentence boundaries)
    - Phrases fade in at start, fade out only at the very end
    """
    st = KARAOKE_STYLES.get(style_name, KARAOKE_STYLES["karaoke"])

    # Apply offset: Whisper timestamps are relative to the raw audio start;
    # the composed video resets to t=0, so subtract the MP3 start_time offset.
    def ts(t):
        return max(0.0, t - audio_offset)

    # ── Build a flat list of all words with adjusted timestamps ──────
    adj = [{"word": w["word"], "start": ts(w["start"]), "end": ts(w["end"])}
           for w in words if w.get("word", "").strip()]

    # Extend each word's display to the next word's start (covers gaps/pauses)
    for i in range(len(adj) - 1):
        adj[i]["disp_end"] = adj[i + 1]["start"]
    adj[-1]["disp_end"] = min(total_duration, adj[-1]["end"] + 1.5)  # hold last word

    # ── Split words into phrase groups ────────────────────────────────
    phrases = []
    current = []
    char_count = 0
    for w in adj:
        if char_count + len(w["word"]) + 1 > line_max_chars and current:
            phrases.append(current)
            current = [w]
            char_count = len(w["word"])
        else:
            current.append(w)
            char_count += len(w["word"]) + 1
    if current:
        phrases.append(current)

    # Extend last word of each phrase to reach next phrase's first word
    for pi in range(len(phrases) - 1):
        next_phrase_start = phrases[pi + 1][0]["start"]
        phrases[pi][-1]["disp_end"] = next_phrase_start

    # ── Build ASS header ──────────────────────────────────────────────
    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1280",
        "PlayResY: 720",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]

    ass_lines.append(
        f"Style: Base,{st['font']},{st['size']},"
        f"{st['rest_color']},{st['rest_color']},"
        f"{st['outline_col']},{st['back_col']},"
        f"{st['bold']},0,0,0,100,100,0,0,1,"
        f"{st['outline']},{st['shadow']},"
        f"{st['alignment']},{st['margin_l']},{st['margin_r']},{st['margin_v']},1"
    )

    ass_lines += ["", "[Events]",
                  "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    # ── Build one Dialogue per word ───────────────────────────────────
    is_last_phrase = len(phrases) - 1
    for pi, phrase in enumerate(phrases):
        for active_idx, active_word in enumerate(phrase):
            w_start   = active_word["start"]
            w_end     = active_word["disp_end"]   # extended to cover gap

            # Build line: rest words white, active word highlighted
            parts = []
            for i, w in enumerate(phrase):
                word_text = w["word"]
                if i == active_idx:
                    parts.append(
                        f"{{\\c{st['active_color']}\\an{st['alignment']}}}{word_text}"
                        f"{{\\c{st['rest_color']}}}"
                    )
                else:
                    parts.append(word_text)

            line_text = " ".join(parts)

            # Fade in on first word of phrase, fade out on last word of last phrase only
            fade_in  = 80  if active_idx == 0 else 0
            is_last_word = (pi == is_last_phrase and active_idx == len(phrase) - 1)
            fade_out = 120 if is_last_word else 0

            ass_lines.append(
                f"Dialogue: 0,{_fmt_time(w_start)},{_fmt_time(w_end)},"
                f"Base,,0,0,0,"
                f",{{\\fad({fade_in},{fade_out})}}{line_text}"
            )

    return "\n".join(ass_lines) + "\n"


def burn_karaoke(
    video_path: str,
    words: list,
    total_duration: float,
    style: str = "karaoke",
    out_path: str = None,
    audio_path: str = None,   # if supplied, auto-detect MP3 start_time offset
) -> str:
    """
    Burn word-by-word karaoke captions into a video clip.
    `words` = list of {"word", "start", "end"} from Whisper.
    `audio_path` = original MP3 — used to measure start_time offset automatically.
    """
    if not out_path:
        out_path = video_path.replace("_composed.mp4", "_captioned.mp4")

    # Auto-detect MP3 start_time offset (ElevenLabs MP3s often have ~25ms offset)
    audio_offset = 0.0
    if audio_path and os.path.exists(audio_path):
        try:
            import subprocess as _sp, json as _json
            r = _sp.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", audio_path],
                capture_output=True, text=True
            )
            for s in _json.loads(r.stdout).get("streams", []):
                if s.get("codec_type") == "audio":
                    audio_offset = float(s.get("start_time", 0.0))
                    break
        except Exception:
            pass

    ass_content = make_karaoke_ass(words, total_duration, style_name=style,
                                   audio_offset=audio_offset)
    ass_file    = video_path + ".karaoke.ass"
    with open(ass_file, "w", encoding="utf-8") as f:
        f.write(ass_content)

    ass_escaped = ass_file.replace("\\", "/").replace(":", "\\:")
    r = subprocess.run([
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"ass='{ass_escaped}'",
        "-c:v", "libx264", "-profile:v", "baseline", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        out_path,
    ], capture_output=True, text=True)

    try:
        os.unlink(ass_file)
    except Exception:
        pass

    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg karaoke burn failed:\n{r.stderr[-500:]}")

    return out_path


# ── Scene pipeline helper ─────────────────────────────────────────────

def burn_karaoke_for_job(job: dict, style: str = "karaoke") -> dict:
    """
    Burn karaoke captions into every composed scene that has word timestamps.
    Falls back to static captions if timestamps are missing.
    """
    caption_style = job.get("caption_style", style)
    use_karaoke = caption_style.startswith("karaoke")

    for scene in job["scenes"]:
        composed = scene.get("composed_path")
        if not composed or not os.path.exists(composed):
            print(f"  [SKIP] {scene['scene_id']} — no composed_path")
            continue

        dur = scene.get("actual_duration") or scene.get("target_duration_seconds", 5.0)
        out = composed.replace("_composed.mp4", "_captioned.mp4")

        timestamps = scene.get("timestamps", [])
        if use_karaoke and timestamps:
            print(f"  Burning karaoke [{caption_style}] → {scene['scene_id']} ({len(timestamps)} words)...", end=" ", flush=True)
            try:
                burn_karaoke(composed, timestamps, float(dur), style=caption_style, out_path=out)
                scene["captioned_path"] = out
                print(f"{os.path.getsize(out)//1024}KB ✓")
            except Exception as e:
                print(f"ERR: {e}")
                scene["captioned_path"] = composed
        else:
            # Fall back to static captions
            static_style = "clean" if not use_karaoke else "clean"
            print(f"  Burning static [{static_style}] → {scene['scene_id']}...", end=" ", flush=True)
            try:
                burn_captions(composed, scene.get("voiceover_text", ""), float(dur),
                              style=static_style, out_path=out)
                scene["captioned_path"] = out
                print(f"{os.path.getsize(out)//1024}KB ✓")
            except Exception as e:
                print(f"ERR: {e}")
                scene["captioned_path"] = composed

    return job



def burn_captions_for_job(job: dict, style: str = "clean") -> dict:
    """
    Burn captions into every composed scene in the job.
    Expects each scene to have a 'composed_path' (video+audio already merged).
    Adds/updates 'captioned_path' on each scene.
    Returns the updated job dict.
    """
    caption_style = job.get("caption_style", style)

    for scene in job["scenes"]:
        composed = scene.get("composed_path")
        if not composed or not os.path.exists(composed):
            print(f"  [SKIP] {scene['scene_id']} — no composed_path")
            continue

        text = scene.get("voiceover_text", "")
        dur  = scene.get("actual_duration") or scene.get("target_duration_seconds", 5.0)

        out = composed.replace("_composed.mp4", "_captioned.mp4")
        print(f"  Burning captions [{caption_style}] → {scene['scene_id']}...", end=" ", flush=True)

        try:
            burn_captions(composed, text, float(dur), style=caption_style, out_path=out)
            scene["captioned_path"] = out
            sz = os.path.getsize(out) // 1024
            print(f"{sz}KB ✓")
        except Exception as e:
            print(f"ERR: {e}")
            scene["captioned_path"] = composed  # fallback: use uncaptioned

    return job


# ── CLI quick-test ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python captions.py <video.mp4> <duration> [style]")
        sys.exit(1)
    vp  = sys.argv[1]
    dur = float(sys.argv[2])
    st  = sys.argv[3] if len(sys.argv) > 3 else "clean"
    txt = "This is what the dark side of social media is really doing to you."
    out = burn_captions(vp, txt, dur, style=st)
    print(f"Output: {out} ({os.path.getsize(out)//1024}KB)")
