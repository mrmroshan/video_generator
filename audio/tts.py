"""
Phase 2a: TTS — ElevenLabs voice generation per scene

Default voice: Adam (pNInz6obpgDQGcFmaJgB) — always available on free tier
Default model: eleven_multilingual_v2 — confirmed working on Roshan's account
"""
import os
import json
import urllib.request
import urllib.error

from pathlib import Path

_ROOT = Path(__file__).parent.parent
MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"
JOBS_DIR = os.getenv("JOBS_DIR", str(_ROOT / "data" / "jobs"))

# ElevenLabs built-in voices (always available, no voices_read permission needed)
VOICES = {
    "adam":    "pNInz6obpgDQGcFmaJgB",  # Male, American, deep — good for narration
    "rachel":  "21m00Tcm4TlvDq8ikWAM",  # Female, American, calm
    "domi":    "AZnzlk1XvdvUeBnXmlld",  # Female, American, energetic
    "bella":   "EXAVITQu4vr4xnSDxMaL",  # Female, American, soft
    "elli":    "MF3mGyEYCl7XYWbV9V6O",  # Female, American, young
    "josh":    "TxGEqnHWrfWFTfGW9XjX",  # Male, American, young
    "arnold":  "VR6AewLTigWG4xSOukaG",  # Male, American, crisp
    "sam":     "yoZ06aMxZJJ28mfd3POQ",  # Male, American, raspy
}

DEFAULT_VOICE = "adam"
DEFAULT_MODEL = "eleven_multilingual_v2"
ELEVENLABS_API = "https://api.elevenlabs.io/v1"


def generate_audio_for_job(job: dict, voice: str = DEFAULT_VOICE) -> dict:
    """
    For each scene in job, generate a .mp3 audio file via ElevenLabs.
    Adds 'audio_path' and 'audio_meta' to each scene.
    Returns updated job dict.
    """
    mock = os.getenv("MOCK_APIS", "true").lower() == "true"
    api_key = os.getenv("ELEVENLABS_API_KEY", "")

    for scene in job["scenes"]:
        scene_id = scene["scene_id"]
        job_dir = os.path.abspath(os.path.join(JOBS_DIR, job['job_id']))
        os.makedirs(job_dir, exist_ok=True)
        audio_path = os.path.join(job_dir, f"{scene_id}.mp3")

        if mock:
            with open(audio_path, "wb") as f:
                f.write(b"MOCK_AUDIO_MP3")
            scene["audio_path"] = audio_path
            scene["audio_meta"] = {"source": "mock", "voice": voice, "chars": len(scene["voiceover_text"])}
            print(f"[MOCK] Audio for {scene_id} → {audio_path}")
        else:
            chars = len(scene["voiceover_text"])
            _call_elevenlabs(
                text=scene["voiceover_text"],
                output_path=audio_path,
                voice_id=VOICES.get(voice, VOICES[DEFAULT_VOICE]),
                api_key=api_key,
            )
            size = os.path.getsize(audio_path)
            scene["audio_path"] = audio_path
            scene["audio_meta"] = {
                "source": "elevenlabs",
                "voice": voice,
                "voice_id": VOICES.get(voice, VOICES[DEFAULT_VOICE]),
                "model": DEFAULT_MODEL,
                "chars": chars,
                "size_bytes": size,
            }
            print(f"✓ Audio [{scene_id}] — {voice} — {chars} chars — {size:,} bytes")

    return job


def _call_elevenlabs(text: str, output_path: str, voice_id: str, api_key: str):
    """POST to ElevenLabs TTS API and write mp3 to output_path."""
    url = f"{ELEVENLABS_API}/text-to-speech/{voice_id}"
    payload = json.dumps({
        "text": text,
        "model_id": DEFAULT_MODEL,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            audio_bytes = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ElevenLabs API error {e.code}: {body}") from e

    if len(audio_bytes) < 1000:
        raise RuntimeError(f"Audio response too small ({len(audio_bytes)} bytes) — likely an error")

    with open(output_path, "wb") as f:
        f.write(audio_bytes)


def list_available_voices() -> dict:
    """Return the built-in voice name → ID mapping."""
    return dict(VOICES)
