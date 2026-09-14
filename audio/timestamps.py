"""
Phase 2b: Whisper — word-level timestamp extraction from audio
Runs locally using the whisper Python package (GPU via RTX 2070S)
"""
import os
import json

MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"


def extract_timestamps(scene: dict) -> dict:
    """
    Given a scene dict with audio_path, run Whisper to extract
    word-level timestamps. Adds 'timestamps' key to scene.
    """
    audio_path = scene.get("audio_path")
    if not audio_path or not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    if MOCK_APIS:
        scene["timestamps"] = _mock_timestamps(scene["voiceover_text"])
        print(f"[MOCK] Timestamps for {scene['scene_id']} → {len(scene['timestamps'])} words")
        return scene

    import whisper  # pip install openai-whisper
    model = whisper.load_model("base")  # upgrade to "medium" or "large" for accuracy
    result = model.transcribe(audio_path, word_timestamps=True)

    words = []
    for segment in result.get("segments", []):
        for word_info in segment.get("words", []):
            words.append({
                "word": word_info["word"].strip(),
                "start": word_info["start"],
                "end": word_info["end"],
            })

    scene["timestamps"] = words
    return scene


def _mock_timestamps(text: str) -> list:
    """Generate fake word-level timestamps for mock mode"""
    words = text.split()
    timestamps = []
    t = 0.0
    for word in words:
        duration = 0.3 + len(word) * 0.05
        timestamps.append({"word": word, "start": round(t, 2), "end": round(t + duration, 2)})
        t += duration + 0.05
    return timestamps
