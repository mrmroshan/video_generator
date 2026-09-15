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

# ── Niche & Topic Catalogue ───────────────────────────────────────────────────

NICHES = {
    "finance": {
        "label": "Finance & Money",
        "icon": "💰",
        "description": "Investing, budgeting, passive income, wealth building",
        "color": "#10b981",
    },
    "entrepreneurship": {
        "label": "Entrepreneurship",
        "icon": "🚀",
        "description": "Starting a business, founder mindset, startup lessons",
        "color": "#6366f1",
    },
    "health": {
        "label": "Health & Wellness",
        "icon": "🧬",
        "description": "Fitness, nutrition, mental health, longevity",
        "color": "#ec4899",
    },
    "tech": {
        "label": "Technology",
        "icon": "⚡",
        "description": "AI, gadgets, software, future trends",
        "color": "#3b82f6",
    },
    "mindset": {
        "label": "Mindset & Growth",
        "icon": "🧠",
        "description": "Habits, psychology, self-improvement, stoicism",
        "color": "#f59e0b",
    },
    "productivity": {
        "label": "Productivity",
        "icon": "⚙️",
        "description": "Time management, focus, systems, tools",
        "color": "#8b5cf6",
    },
    "ai": {
        "label": "AI & Future",
        "icon": "🤖",
        "description": "AI tools, automation, future of work",
        "color": "#06b6d4",
    },
    "marketing": {
        "label": "Marketing",
        "icon": "📣",
        "description": "Content strategy, social media growth, personal brand",
        "color": "#f97316",
    },
    "relationships": {
        "label": "Relationships",
        "icon": "❤️",
        "description": "Communication, dating, family, social skills",
        "color": "#ef4444",
    },
    "fitness": {
        "label": "Fitness",
        "icon": "💪",
        "description": "Workouts, muscle building, weight loss, sports",
        "color": "#14b8a6",
    },
}

TOPIC_PROMPT = """You are a viral video content strategist for {platform}.

Generate 8 trending, highly engaging video topic ideas for the niche: "{niche_label}"

Rules:
- Output ONLY valid JSON — no markdown, no explanation, no code fences
- Each topic must be specific, not generic (not "how to save money" — yes "The 3 bank accounts every 20-something needs")
- Each topic must have a punchy hook line that grabs attention in 2 seconds
- Topics must be evergreen AND currently trending
- Platform rules: {platform_rules}

Output this exact JSON structure:
{{
  "niche": "{niche_key}",
  "platform": "{platform}",
  "topics": [
    {{
      "id": "t1",
      "title": "...",
      "hook": "One punchy sentence that opens the video",
      "why_trending": "One sentence on why this works right now"
    }}
  ]
}}"""

SCRIPT_PROMPT = """You are a video script writer for {platform} videos.

Generate a video script for the topic: \"{topic}\"

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


def generate_topic_ideas(niche: str, platform: str) -> dict:
    """
    Generate 8 trending topic ideas for a given niche and platform.
    Uses Claude Max CLI. Falls back to curated mock topics if unavailable.
    """
    if os.getenv("MOCK_APIS", "true").lower() == "true":
        return _mock_topics(niche, platform)

    niche_info = NICHES.get(niche, NICHES["finance"])
    prompt = TOPIC_PROMPT.format(
        platform=platform,
        niche_label=niche_info["label"],
        niche_key=niche,
        platform_rules=PLATFORM_RULES.get(platform, PLATFORM_RULES["youtube"]),
    )

    try:
        result = _call_claude(prompt)
        data = json.loads(result)
        if "topics" not in data:
            raise ValueError("Missing 'topics' key")
        return data
    except Exception as e:
        print(f"[WARN] Topic generation failed ({e}), using mock topics")
        return _mock_topics(niche, platform)


def _mock_topics(niche: str, platform: str) -> dict:
    """Curated fallback topics per niche."""
    MOCK = {
        "finance": [
            {"id": "t1", "title": "The 3 bank accounts every 20-something needs", "hook": "You only need ONE bank account — right? Wrong.", "why_trending": "Financial literacy for Gen Z is exploding on short-form"},
            {"id": "t2", "title": "Why your savings account is making you poor", "hook": "Leaving money in a savings account is losing money.", "why_trending": "Inflation awareness driving high engagement"},
            {"id": "t3", "title": "The side hustle that made me $5k in 30 days", "hook": "I made more money last month than my full-time job.", "why_trending": "Side hustle content dominates every platform"},
            {"id": "t4", "title": "5 money rules rich people never talk about", "hook": "Rich people don't talk about money — they follow rules.", "why_trending": "Wealth secrets framing drives massive clicks"},
            {"id": "t5", "title": "The credit score trick banks don't want you to know", "hook": "I raised my credit score 100 points in 60 days.", "why_trending": "Credit education is perennially top-performing"},
            {"id": "t6", "title": "Why most people never retire (and how to be different)", "hook": "Most people will work until they die. Here's why.", "why_trending": "Retirement anxiety is at an all-time high"},
            {"id": "t7", "title": "The hidden costs of working from home", "hook": "You saved on commute — so why are you broker?", "why_trending": "WFH reality check content resonates post-pandemic"},
            {"id": "t8", "title": "Invest $100/month and retire with $1 million", "hook": "A hundred dollars a month. One million dollars. Math.", "why_trending": "Compound interest visualisations go viral constantly"},
        ],
        "entrepreneurship": [
            {"id": "t1", "title": "3 signs you are meant to be an entrepreneur", "hook": "If you do these 3 things, a 9-to-5 will never satisfy you.", "why_trending": "Entrepreneurial identity content spikes annually"},
            {"id": "t2", "title": "The mistake that killed my first business", "hook": "I lost everything — here is exactly what went wrong.", "why_trending": "Failure stories outperform success stories 3:1"},
            {"id": "t3", "title": "Why most startups fail in year 2 (not year 1)", "hook": "Year 1 is easy. Year 2 kills most founders. Here's why.", "why_trending": "Contrarian startup insight drives debate and shares"},
            {"id": "t4", "title": "The $0 business model that made me $10k/month", "hook": "Zero investment. Ten thousand dollars a month. No catch.", "why_trending": "Zero-cost business models are the #1 searched topic"},
            {"id": "t5", "title": "What I wish I knew before starting a business at 25", "hook": "I started my first business at 25. I wish someone told me this.", "why_trending": "Founder retrospective content has evergreen appeal"},
            {"id": "t6", "title": "The one meeting that changed my business forever", "hook": "One conversation added $50k to my annual revenue.", "why_trending": "Story-format business content has highest completion rates"},
            {"id": "t7", "title": "Why your business idea doesn't need to be original", "hook": "Stop waiting for a genius idea. Copy first. Innovate later.", "why_trending": "Permission-giving content drives massive saves"},
            {"id": "t8", "title": "The silent skill every successful founder has", "hook": "It's not networking. It's not coding. It's this.", "why_trending": "Mystery-format hooks drive top-of-funnel curiosity"},
        ],
        "ai": [
            {"id": "t1", "title": "5 AI tools that do in 1 hour what took me a week", "hook": "I deleted 10 apps and replaced them with 5 AI tools.", "why_trending": "AI productivity tools are the most searched topic in 2025"},
            {"id": "t2", "title": "The AI skill that will make you irreplaceable", "hook": "AI won't replace you — but someone using AI will.", "why_trending": "Job security anxiety drives massive engagement"},
            {"id": "t3", "title": "How I built a $5k/month business using only AI", "hook": "No employees. No code. Just me and 4 AI tools.", "why_trending": "AI-powered income stories are viral across platforms"},
            {"id": "t4", "title": "The AI prompt that writes better than most humans", "hook": "I spent 3 months perfecting this prompt. It's yours.", "why_trending": "Prompt engineering tips have insane save rates"},
            {"id": "t5", "title": "Why most people are using ChatGPT wrong", "hook": "90% of people use ChatGPT like a search engine. Don't.", "why_trending": "Correcting common misconceptions = guaranteed engagement"},
            {"id": "t6", "title": "The AI tool that replaced my entire marketing team", "hook": "I let go of 3 contractors. One AI tool did their jobs.", "why_trending": "AI vs human work debate is peak virality right now"},
            {"id": "t7", "title": "5 ways AI is about to change your job forever", "hook": "This isn't fear-mongering. This is what's already happening.", "why_trending": "Future-of-work content has 10x average view duration"},
            {"id": "t8", "title": "I tested every AI video tool so you don't have to", "hook": "15 tools. 30 days. One clear winner.", "why_trending": "Comparison content drives the highest trust engagement"},
        ],
        "mindset": [
            {"id": "t1", "title": "The morning routine that changed my life in 90 days", "hook": "I changed one hour of my morning. My life looks nothing like it did.", "why_trending": "Morning routine content is perennially top-performing"},
            {"id": "t2", "title": "Why discipline beats motivation every single time", "hook": "Motivation will leave you. Discipline never does.", "why_trending": "Discipline vs motivation debate drives comments"},
            {"id": "t3", "title": "The stoic habit that eliminates 90% of anxiety", "hook": "The ancient Romans had a cure for modern anxiety.", "why_trending": "Stoicism content is surging across all demographics"},
            {"id": "t4", "title": "Stop waiting to feel ready — it never comes", "hook": "Readiness is a lie your brain tells you to stay safe.", "why_trending": "Activation energy content drives highest save rates"},
            {"id": "t5", "title": "The identity shift that makes habits effortless", "hook": "You don't need more willpower. You need a different identity.", "why_trending": "Identity-based habit content resonates deeply"},
            {"id": "t6", "title": "Why your environment is sabotaging your goals", "hook": "It's not you. It's where you are.", "why_trending": "Environment design content is underserved and viral"},
            {"id": "t7", "title": "The 5-second rule that fixes procrastination", "hook": "Your brain decides in 5 seconds whether to act or retreat.", "why_trending": "Procrastination solutions are perennially searched"},
            {"id": "t8", "title": "What successful people do differently on Sundays", "hook": "Sunday isn't a rest day. It's a prep day.", "why_trending": "Routine-reveal content has highest repeat viewership"},
        ],
    }
    # Default to finance if niche not in mock
    topics = MOCK.get(niche, MOCK["finance"])
    return {"niche": niche, "platform": platform, "topics": topics}


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


def _call_claude(prompt: str) -> str:
    """
    Call claude -p with a raw prompt string. Returns the result text.
    Reused by both _generate_with_claude and generate_topic_ideas.
    """
    import tempfile
    claude_cmd = _get_claude_cmd()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as pf:
        pf.write(prompt)
        prompt_file = pf.name

    out_file = prompt_file + ".out.json"
    try:
        bat = (
            f'type "{prompt_file}" | '
            f'"{claude_cmd}" -p --max-turns 1 --output-format json > "{out_file}"'
        )
        subprocess.run(bat, shell=True, timeout=90,
                       cwd=os.path.expanduser("~"),
                       capture_output=True)

        if not os.path.exists(out_file) or os.path.getsize(out_file) == 0:
            raise RuntimeError("claude produced no output")

        with open(out_file, "rb") as f:
            raw = f.read().decode("utf-8-sig", errors="replace").strip()

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
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        raw_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    return raw_text


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
