"""
Phase 2b: Word-level timestamp extraction.

Priority:
  1. OpenAI Whisper API (OPENAI_API_KEY set) — accurate, no local RAM needed
  2. faster-whisper local (CPU int8) — self-hosted, needs ~2GB RAM free
  3. Mock timestamps — evenly spaced, for MOCK_APIS=true or fallback
"""
import os
import urllib.request
from pathlib import Path

MOCK_APIS      = os.getenv("MOCK_APIS",      "true").lower() == "true"
WHISPER_MODEL  = os.getenv("WHISPER_MODEL",  "base")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


def extract_timestamps(scene: dict) -> dict:
    """
    Populate scene['timestamps'] = [{"word", "start", "end"}, ...].
    """
    audio_path = scene.get("audio_path")
    if not audio_path or not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    if MOCK_APIS:
        scene["timestamps"] = _mock_timestamps(scene["voiceover_text"])
        print(f"  [MOCK] Timestamps → {scene['scene_id']}: {len(scene['timestamps'])} words")
        return scene

    if OPENAI_API_KEY:
        try:
            return _whisper_api(scene, audio_path)
        except Exception as e:
            print(f"  [WARN] Whisper API failed ({e}), trying local...")

    try:
        return _faster_whisper_local(scene, audio_path)
    except Exception as e:
        print(f"  [WARN] Local Whisper failed ({e}), using mock timestamps")
        scene["timestamps"] = _mock_timestamps(scene["voiceover_text"])
        return scene


def _whisper_api(scene: dict, audio_path: str) -> dict:
    """OpenAI Whisper API — verbose_json with word-level timestamps."""
    import json as _json
    print(f"  Whisper API → {scene['scene_id']}...", end=" ", flush=True)

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    filename  = os.path.basename(audio_path)
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: audio/mpeg\r\n\r\n"
    ).encode() + audio_bytes + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="response_format"\r\n\r\nverbose_json\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="timestamp_granularities[]"\r\n\r\nword\r\n'
        f"--{boundary}--\r\n"
    ).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type":  f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = _json.loads(resp.read())

    scene["timestamps"] = [
        {"word": w["word"].strip(), "start": round(w["start"], 3), "end": round(w["end"], 3)}
        for w in data.get("words", []) if w.get("word", "").strip()
    ]
    print(f"{len(scene['timestamps'])} words")
    return scene


def _faster_whisper_local(scene: dict, audio_path: str) -> dict:
    """faster-whisper local inference (needs ~2GB free RAM)."""
    from faster_whisper import WhisperModel
    print(f"  Whisper local [{WHISPER_MODEL}] CPU...", end=" ", flush=True)
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8",
                         cpu_threads=2, num_workers=1)
    segments, _ = model.transcribe(audio_path, word_timestamps=True,
                                   language="en", beam_size=3, vad_filter=True)
    scene["timestamps"] = [
        {"word": w.word.strip(), "start": round(float(w.start), 3), "end": round(float(w.end), 3)}
        for seg in segments for w in (seg.words or []) if w.word.strip()
    ]
    print(f"{len(scene['timestamps'])} words")
    return scene


def _mock_timestamps(text: str) -> list:
    """Evenly-spaced word timestamps — dev mode / fallback."""
    result, t = [], 0.0
    for word in text.split():
        dur = 0.25 + len(word) * 0.045
        result.append({"word": word, "start": round(t, 3), "end": round(t + dur, 3)})
        t += dur + 0.04
    return result
