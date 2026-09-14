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
    """Convert float seconds to ASS timestamp H:MM:SS.cc"""
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
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


# ── Scene pipeline helper ─────────────────────────────────────────────

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
