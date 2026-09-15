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
    "tiktok":    "TikTok style — fast hook in scene_01 (≤4s), punchy lines, each scene ≤6s, total ≤30s",
    "youtube":   "YouTube style — engaging narrative, build curiosity, each scene 5-10s, total 45-90s",
    "instagram": "Instagram Reels/Feed style — strong visual hook, concise scenes 5-8s, total 30-60s, square-friendly framing",
    "facebook":  "Facebook video style — engaging hook, accessible language, scenes 6-10s, total 45-90s, auto-play-friendly",
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
    # Add generic fallback topics for niches not yet in MOCK
    GENERIC = {
        "health":         [
            {"id": "t1", "title": "The morning habit that adds 10 years to your life", "hook": "One habit. Backed by science. Takes 5 minutes.", "why_trending": "Longevity content is top-performing across all age groups"},
            {"id": "t2", "title": "Why most diets fail by week 3 (and what actually works)", "hook": "It's not willpower. It's biology. Here's the fix.", "why_trending": "Diet myth-busting drives high save rates"},
            {"id": "t3", "title": "The gut health secret no doctor tells you", "hook": "Your gut runs your brain. Most people ignore it.", "why_trending": "Gut microbiome content is surging across platforms"},
            {"id": "t4", "title": "5 signs your body is inflamed right now", "hook": "Inflammation is silent. These symptoms scream it.", "why_trending": "Symptom-awareness content drives fear-based engagement"},
            {"id": "t5", "title": "The sleep habit that doubles your energy", "hook": "It's not how long you sleep. It's when.", "why_trending": "Sleep optimization is consistently top-searched"},
            {"id": "t6", "title": "Why walking is the most underrated exercise", "hook": "No gym. No equipment. Just 30 minutes.", "why_trending": "Low-barrier fitness content gets the highest saves"},
            {"id": "t7", "title": "The mental health habit athletes swear by", "hook": "Pro athletes don't just train their body.", "why_trending": "Mental health content has universal appeal"},
            {"id": "t8", "title": "What happens to your body when you quit sugar for 30 days", "hook": "Day 1 is hell. Day 30 is transformation.", "why_trending": "Before/after format content has maximum completion rate"},
        ],
        "tech":           [
            {"id": "t1", "title": "5 free tools that replace $500/month software", "hook": "Stop paying for tools you don't need.", "why_trending": "Cost-cutting tool content spikes during economic uncertainty"},
            {"id": "t2", "title": "The browser extension that saves me 2 hours a day", "hook": "I installed it. I never uninstalled it.", "why_trending": "Specific tool recommendations drive the highest CTR"},
            {"id": "t3", "title": "Why your phone is secretly hurting your focus", "hook": "It's not social media. It's the notifications.", "why_trending": "Screen time and focus content is perennial"},
            {"id": "t4", "title": "The keyboard shortcut most people never learn", "hook": "I've used computers for 20 years. I learned this last year.", "why_trending": "Productivity shortcuts have the highest save-to-view ratio"},
            {"id": "t5", "title": "How I automated my entire workflow for $0", "hook": "Every task I hated is now done automatically.", "why_trending": "No-code automation content is exploding"},
            {"id": "t6", "title": "The tech setup that made me 3x more productive", "hook": "Same hours. Three times the output.", "why_trending": "Desk setup/workflow reveals are highly shareable"},
            {"id": "t7", "title": "Why I deleted all my apps and started over", "hook": "200 apps. Now I use 12.", "why_trending": "Digital minimalism content drives high engagement"},
            {"id": "t8", "title": "The security setting every phone user needs to turn on", "hook": "Your phone is not as secure as you think.", "why_trending": "Security awareness content drives fear-based shares"},
        ],
        "productivity":   [
            {"id": "t1", "title": "The 2-minute rule that clears your to-do list", "hook": "If it takes 2 minutes, do it now. Not later.", "why_trending": "GTD-based content is perennially top-performing"},
            {"id": "t2", "title": "Why your to-do list is making you less productive", "hook": "The problem isn't your tasks. It's your list.", "why_trending": "Contrarian productivity content drives debate"},
            {"id": "t3", "title": "The focus technique used by Navy SEALs", "hook": "When distraction is life or death, you learn to focus.", "why_trending": "Elite performance frameworks drive aspiration content"},
            {"id": "t4", "title": "How I get more done in 4 hours than most in 8", "hook": "Work less. Do more. It's not magic.", "why_trending": "4-hour workday content is a perennial viral format"},
            {"id": "t5", "title": "The Sunday planning system that changed my weeks", "hook": "One hour on Sunday saves 10 hours during the week.", "why_trending": "Weekly planning systems have the highest save rates"},
            {"id": "t6", "title": "Stop multitasking — it's costing you 40% of your brain", "hook": "Multitasking isn't a skill. It's a myth.", "why_trending": "Scientific backing for habit change drives credibility"},
            {"id": "t7", "title": "The email habit that saves 90 minutes a day", "hook": "I check email twice a day. That's it.", "why_trending": "Email productivity is universally relatable"},
            {"id": "t8", "title": "Why the most productive people have boring mornings", "hook": "No cold plunge. No meditation app. Just boring habits.", "why_trending": "Contrarian morning routine content outperforms conventional"},
        ],
        "marketing":      [
            {"id": "t1", "title": "The hook formula that gets 90% of people to stop scrolling", "hook": "3 seconds. That's all you have to grab attention.", "why_trending": "Short-form hook writing is the #1 skill marketers want"},
            {"id": "t2", "title": "Why your personal brand is worth more than your resume", "hook": "Your LinkedIn is your new CV. Most people waste it.", "why_trending": "Personal brand content peaks every Q1"},
            {"id": "t3", "title": "How to get 10,000 followers without spending a cent", "hook": "No ads. No virality tricks. Just strategy.", "why_trending": "Organic growth tactics are evergreen top-performers"},
            {"id": "t4", "title": "The content type that gets shared 10x more than anything else", "hook": "I stopped posting opinions. I started posting this.", "why_trending": "Shareable content strategy drives creator growth"},
            {"id": "t5", "title": "Why most brands fail at social media (and how to fix it)", "hook": "Posting is not a strategy. This is.", "why_trending": "Brand accountability content drives B2B engagement"},
            {"id": "t6", "title": "The email subject line that gets 60% open rates", "hook": "Most email subjects are wrong. Here's why.", "why_trending": "Email marketing ROI content is top B2B search"},
            {"id": "t7", "title": "How one piece of content can work across 6 platforms", "hook": "Create once. Publish everywhere. Grow everywhere.", "why_trending": "Content repurposing is the #1 productivity ask"},
            {"id": "t8", "title": "The storytelling formula that makes anything go viral", "hook": "Every viral video uses this 3-part structure.", "why_trending": "Storytelling frameworks have consistently high save rates"},
        ],
        "relationships":  [
            {"id": "t1", "title": "The 5-second response that defuses any argument", "hook": "Before you react, say this. Every time.", "why_trending": "Conflict resolution content has universal appeal"},
            {"id": "t2", "title": "Why most friendships fade after 25 (and how to keep yours)", "hook": "Adult friendships die quietly. Here's the rescue.", "why_trending": "Adult friendship anxiety is a top-searched topic"},
            {"id": "t3", "title": "The communication habit of every successful relationship", "hook": "Happy couples don't fight less. They fight differently.", "why_trending": "Relationship longevity content is perennially viral"},
            {"id": "t4", "title": "Red flags most people ignore until it's too late", "hook": "The signs were always there. You just didn't know them.", "why_trending": "Red flag content consistently tops engagement charts"},
            {"id": "t5", "title": "Why setting boundaries is the most loving thing you can do", "hook": "Saying no isn't selfish. It's necessary.", "why_trending": "Boundary content is top-performing mental health adjacent"},
            {"id": "t6", "title": "The question that tells you if someone truly listens to you", "hook": "Ask this. Their answer tells you everything.", "why_trending": "Relationship litmus-test content drives saves"},
            {"id": "t7", "title": "How to reconnect with someone after a long silence", "hook": "You don't need a reason. You just need this.", "why_trending": "Reconnection anxiety is widely relatable"},
            {"id": "t8", "title": "The difference between loneliness and being alone", "hook": "Millions are surrounded by people and still lonely.", "why_trending": "Loneliness is the defining social trend of the decade"},
        ],
        "fitness":        [
            {"id": "t1", "title": "The 10-minute workout that builds more muscle than an hour at the gym", "hook": "Gym rats hate this. Scientists love it.", "why_trending": "Time-efficient fitness content dominates mobile"},
            {"id": "t2", "title": "Why you're not losing weight despite working out", "hook": "You're doing everything right. And still nothing.", "why_trending": "Plateau-breaking content drives frustrated searchers"},
            {"id": "t3", "title": "The recovery habit that elite athletes never skip", "hook": "Training hard is 50% of it. This is the other 50%.", "why_trending": "Recovery science content is underserved and growing"},
            {"id": "t4", "title": "Why your warm-up is more important than your workout", "hook": "The first 5 minutes determine the next 50.", "why_trending": "Pre-workout science content drives high saves"},
            {"id": "t5", "title": "The protein timing myth fitness influencers still spread", "hook": "The 30-minute anabolic window is not real.", "why_trending": "Myth-busting fitness content drives debate and shares"},
            {"id": "t6", "title": "How to build muscle without ever going to the gym", "hook": "No membership. No equipment. Real results.", "why_trending": "Home workout demand never drops"},
            {"id": "t7", "title": "The bodyweight move that replaces 5 gym machines", "hook": "One move. Full body. No excuses.", "why_trending": "Efficiency-focused fitness drives the highest saves"},
            {"id": "t8", "title": "Why consistency beats intensity every time in fitness", "hook": "The person who shows up wins. Every time.", "why_trending": "Motivational fitness framing drives comment engagement"},
        ],
    }
    all_topics = {**MOCK, **GENERIC}
    topics = all_topics.get(niche, MOCK["finance"])
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
        r = subprocess.run(bat, shell=True, timeout=90,
                           cwd=os.path.expanduser("~"),
                           capture_output=True)

        if r.returncode != 0:
            stderr = r.stderr.decode("utf-8", errors="replace")[:300] if r.stderr else ""
            raise RuntimeError(f"claude exited {r.returncode}: {stderr}")

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
