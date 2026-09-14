"""
Phase 2b: Word-level timestamp extraction via faster-whisper (local, RTX 2070S).
Produces word timestamps used for karaoke caption highlighting.
"""
import os
import json
from pathlib import Path

MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")   # base / small / medium / large-v3


def extract_timestamps(scene: dict) -> dict:
    """
    Given a scene dict with audio_path, run faster-whisper to extract
    word-level timestamps. Adds 'timestamps' key to scene.
    Each entry: {"word": str, "start": float, "end": float}
    """
    audio_path = scene.get("audio_path")
    if not audio_path or not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    if MOCK_APIS:
        scene["timestamps"] = _mock_timestamps(scene["voiceover_text"])
        print(f"  [MOCK] Timestamps → {scene['scene_id']}: {len(scene['timestamps'])} words")
        return scene

    return _run_faster_whisper(scene, audio_path)


def _run_faster_whisper(scene: dict, audio_path: str) -> dict:
    """Extract word timestamps using faster-whisper (CTranslate2, GPU-accelerated)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("faster-whisper not installed. Run: pip install faster-whisper")

    # Force CPU — CUDA malloc is unreliable when GPU is under load from other processes
    device  = "cpu"
    compute = "int8"
    print(f"  Whisper [{WHISPER_MODEL}] on CPU...", end=" ", flush=True)
    model = WhisperModel(WHISPER_MODEL, device=device, compute_type=compute)
    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        language="en",
        beam_size=5,
        vad_filter=True,               # skip silence
        vad_parameters={"min_silence_duration_ms": 200},
    )

    words = []
    for segment in segments:
        for w in (segment.words or []):
            word = w.word.strip()
            if word:
                words.append({
                    "word":  word,
                    "start": round(float(w.start), 3),
                    "end":   round(float(w.end),   3),
                })

    scene["timestamps"] = words
    print(f"{len(words)} words detected")
    return scene


def _cuda_available() -> bool:
    try:
        import ctypes
        ctypes.cdll.LoadLibrary("nvcuda.dll")
        return True
    except Exception:
        return False


def _mock_timestamps(text: str) -> list:
    """Evenly-spaced word timestamps for mock/dev mode."""
    words = text.split()
    timestamps = []
    t = 0.0
    for word in words:
        dur = 0.25 + len(word) * 0.045
        timestamps.append({
            "word":  word,
            "start": round(t, 3),
            "end":   round(t + dur, 3),
        })
        t += dur + 0.04
    return timestamps
