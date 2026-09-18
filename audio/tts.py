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
# NOTE: MOCK_APIS and JOBS_DIR are read lazily inside functions (os.getenv at call time)
# so that monkeypatching in tests takes effect. Do NOT cache them at module level.

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
    jobs_dir = os.getenv("JOBS_DIR", str(_ROOT / "data" / "jobs"))

    for scene in job["scenes"]:
        scene_id = scene["scene_id"]
        job_dir = os.path.abspath(os.path.join(jobs_dir, job['job_id']))
        os.makedirs(job_dir, exist_ok=True)
        audio_path = os.path.join(job_dir, f"{scene_id}.mp3")

        if mock:
            with open(audio_path, "wb") as f:
                f.write(b"MOCK_AUDIO_MP3")
            scene["audio_path"] = audio_path
            scene["audio_meta"] = {"source": "mock", "voice": voice, "chars": len(scene["voiceover_text"])}
            print(f"[MOCK] Audio for {scene_id} → {audio_path}")
        else:
            chars = len(scene.get("voiceover_text", ""))
            if not chars:
                print(f"  [WARN] {scene_id}: empty voiceover_text — skipping TTS")
                continue
            try:
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
            except RuntimeError as e:
                err = str(e)
                quota_hit = "quota_exceeded" in err or "429" in err or "401" in err
                if quota_hit:
                    print(f"  [WARN] {scene_id}: ElevenLabs quota — falling back to edge-tts")
                    try:
                        _call_edge_tts(text=scene["voiceover_text"], output_path=audio_path)
                        size = os.path.getsize(audio_path)
                        scene["audio_path"] = audio_path
                        scene["audio_meta"] = {"source": "edge_tts", "chars": chars, "size_bytes": size}
                        print(f"✓ Audio [{scene_id}] — edge-tts fallback — {chars} chars")
                        continue
                    except Exception as e2:
                        print(f"  [ERROR] {scene_id}: edge-tts fallback also failed: {e2}")
                print(f"  [WARN] {scene_id}: TTS failed ({err}) — skipping scene")
                scene["audio_path"] = None
                scene["audio_meta"] = {"source": "failed", "error": err}

    return job


def _call_elevenlabs(text: str, output_path: str, voice_id: str, api_key: str):
    """POST to ElevenLabs TTS API and write mp3 to output_path."""
    url = f"{ELEVENLABS_API}/text-to-speech/{voice_id}"
    payload = json.dumps({
        "text": text,
        "model_id": DEFAULT_MODEL,
        "voice_settings": {
            "stability": 0.65,          # higher = slower, more consistent pacing (was 0.5)
            "similarity_boost": 0.75,
            "style": 0.15,              # slight style keeps warmth without rushing
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


def _call_edge_tts(text: str, output_path: str, voice: str = "en-US-GuyNeural") -> None:
    """Generate TTS audio using Microsoft Edge TTS (free, no quota).

    Uses the edge-tts package which streams from Microsoft's neural TTS.
    Voice 'en-US-GuyNeural' is a deep, clear male voice good for motivational content.
    Output is saved as MP3 to output_path.
    """
    import asyncio
    import edge_tts

    async def _run():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)

    asyncio.run(_run())
