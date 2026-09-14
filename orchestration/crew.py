"""
Phase 1: Orchestration & Script Generation
Uses Claude Code CLI (claude -p) via your Claude Max subscription — no API key needed.
Falls back to mock blueprint if claude CLI unavailable.
"""
import os
import uuid
import json
import subprocess
from datetime import datetime, timezone

MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"
JOBS_DIR = os.getenv("JOBS_DIR", "./data/jobs")

SCRIPT_PROMPT = """You are a video script writer for {platform} videos.

Generate a video script for the topic: "{topic}"

Rules:
- Output ONLY valid JSON — no markdown, no explanation, no code fences
- {platform_rules}
- Every scene MUST have a specific, descriptive broll_prompt (10+ words)
- Keep voiceover_text punchy and conversational
- Generate exactly 5 scenes

Output this exact JSON structure:
{{
  "title": "...",
  "description": "...",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"],
  "scenes": [
    {{
      "scene_id": "scene_01",
      "voiceover_text": "...",
      "target_duration_seconds": 5,
      "broll_prompt": "...",
      "platform": "{platform}"
    }}
  ]
}}"""

PLATFORM_RULES = {
    "tiktok": "TikTok style — fast hook in scene_01 (≤4s), punchy lines, each scene ≤6s, total ≤30s",
    "youtube": "YouTube style — engaging narrative, build curiosity, each scene 5-10s, total 45-90s",
}


def generate_script(topic: str, platform: str) -> dict:
    """
    Generate a full job blueprint JSON for a given topic and platform.
    Uses Claude Max subscription via claude CLI. Falls back to mock if unavailable.
    """
    if MOCK_APIS:
        print("[MOCK] Generating script blueprint")
        return _mock_blueprint(topic, platform)

    try:
        return _generate_with_claude(topic, platform)
    except Exception as e:
        print(f"[WARN] Claude CLI failed ({e}), falling back to mock")
        return _mock_blueprint(topic, platform)


def _get_claude_cmd() -> str:
    """Auto-discover claude CLI path. Uses CLAUDE_CMD env var as override."""
    import shutil
    override = os.environ.get("CLAUDE_CMD", "")
    if override and os.path.exists(override):
        return override
    # Auto-discover via PATH (works cross-platform)
    found = shutil.which("claude") or shutil.which("claude.cmd")
    if found:
        return found
    # Windows default fallback
    default = r"C:\Users\roshan\AppData\Roaming\npm\claude.cmd"
    if os.path.exists(default):
        return default
    raise RuntimeError(
        "claude CLI not found. Set CLAUDE_CMD env var or install: "
        "npm install -g @anthropic-ai/claude-code"
    )


def _generate_with_claude(topic: str, platform: str) -> dict:
    """Call claude -p to generate the script JSON using Claude Max subscription."""
    import tempfile

    prompt = SCRIPT_PROMPT.format(
        topic=topic,
        platform=platform,
        platform_rules=PLATFORM_RULES.get(platform, PLATFORM_RULES["youtube"]),
    )

    claude_cmd = _get_claude_cmd()

    print(f"🤖 Generating script via Claude Max for: '{topic}' ({platform})")

    # Write prompt to a temp file and run from user home to avoid CLAUDE.md interference
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as pf:
        pf.write(prompt)
        prompt_file = pf.name

    out_file = prompt_file + ".out.json"

    try:
        # Redirect only stdout; capture stderr separately for diagnostics
        bat = (
            f'type "{prompt_file}" | '
            f'"{claude_cmd}" -p --max-turns 1 --output-format json > "{out_file}"'
        )
        r = subprocess.run(bat, shell=True, timeout=90,
                           cwd=os.path.expanduser("~"),
                           capture_output=True)

        if not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
            raise RuntimeError("claude produced no output")

        with open(out_file, "rb") as f:
            raw = f.read().decode("utf-8-sig", errors="replace").strip()

        # Find the JSON object start
        idx = raw.find("{")
        if idx < 0:
            raise RuntimeError(f"No JSON in output: {raw[:200]}")
        raw = raw[idx:]

    finally:
        for p in [prompt_file, out_file]:
            try: os.unlink(p)
            except: pass

    outer = json.loads(raw)
    if outer.get("is_error"):
        raise RuntimeError(f"Claude error: {outer.get('result','')[:300]}")

    raw_text = outer.get("result", "").strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        raw_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    script = json.loads(raw_text)
    return _assemble_job(script, topic, platform)


def _assemble_job(script: dict, topic: str, platform: str) -> dict:
    """Assemble a full job blueprint from the Claude-generated script."""
    job_id = str(uuid.uuid4())

    # Validate and normalise scenes
    scenes = []
    for i, s in enumerate(script.get("scenes", []), 1):
        sid = s.get("scene_id", f"scene_{i:02d}")
        scenes.append({
            "scene_id": sid,
            "voiceover_text": s.get("voiceover_text", ""),
            "target_duration_seconds": s.get("target_duration_seconds", 5),
            "broll_prompt": s.get("broll_prompt", topic),
            "platform": platform,
        })

    # Renderer: always ffmpeg — Remotion not yet wired
    renderer = "ffmpeg"

    return {
        "job_id": job_id,
        "status": "pending",
        "platform": platform,
        "title": script.get("title", f"The Truth About {topic.title()}"),
        "description": script.get("description", ""),
        "hashtags": script.get("hashtags", [f"#{topic.replace(' ', '')}"]),
        "scenes": scenes,
        "renderer": renderer,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approved_at": None,
        "output_path": None,
        "generated_by": "claude-max",
        "topic": topic,
    }


def _mock_blueprint(topic: str, platform: str) -> dict:
    job_id = str(uuid.uuid4())
    scenes = [
        {
            "scene_id": "scene_01",
            "voiceover_text": f"Did you know that {topic} is changing everything?",
            "target_duration_seconds": 4,
            "broll_prompt": f"{topic} aerial wide shot cinematic golden hour",
            "platform": platform,
        },
        {
            "scene_id": "scene_02",
            "voiceover_text": "Here's what most people get wrong about it.",
            "target_duration_seconds": 5,
            "broll_prompt": "person looking confused at laptop screen close up office",
            "platform": platform,
        },
        {
            "scene_id": "scene_03",
            "voiceover_text": f"The truth about {topic} will surprise you.",
            "target_duration_seconds": 5,
            "broll_prompt": f"{topic} technology futuristic concept 4k cinematic",
            "platform": platform,
        },
        {
            "scene_id": "scene_04",
            "voiceover_text": "Most experts won't tell you this part.",
            "target_duration_seconds": 5,
            "broll_prompt": "expert in suit speaking conference podium professional lighting",
            "platform": platform,
        },
        {
            "scene_id": "scene_05",
            "voiceover_text": f"Start using {topic} today. Your future self will thank you.",
            "target_duration_seconds": 4,
            "broll_prompt": f"person smiling sunrise new beginning motivated cinematic",
            "platform": platform,
        },
    ]
    return {
        "job_id": job_id,
        "status": "pending",
        "platform": platform,
        "title": f"The Truth About {topic.title()}",
        "description": f"Everything you need to know about {topic} in under 60 seconds.",
        "hashtags": [f"#{topic.replace(' ', '')}", "#shorts", "#fyp"],
        "scenes": scenes,
        "renderer": "ffmpeg",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approved_at": None,
        "output_path": None,
        "generated_by": "mock",
        "topic": topic,
    }


if __name__ == "__main__":
    import sys
    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "artificial intelligence"
    os.environ["MOCK_APIS"] = "false"
    job = generate_script(topic, "tiktok")
    print(json.dumps(job, indent=2))
