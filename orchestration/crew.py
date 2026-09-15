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

TOPIC_PROMPT = """You are a viral short-form video content strategist.

Generate 8 trending, highly specific video topic ideas for the niche: "{niche_label}"

AUDIENCE: {audience}
TONE: {tone}
HOOK STYLES THAT WORK FOR THIS NICHE: {hook_styles}

Rules:
- Output ONLY valid JSON — no markdown, no explanation, no code fences
- Each topic must be SPECIFIC, not generic (not "how to save money" → yes "The 3 bank accounts every 20-something needs")
- Each topic must have a punchy hook that grabs in the first 2 seconds using one of the hook styles above
- Topics must be evergreen AND feel current — tap into what this audience is anxious or curious about RIGHT NOW
- why_trending must reference a real tension, trend, or anxiety in this audience

Output this exact JSON structure:
{{
  "niche": "{niche_key}",
  "platform": "{platform}",
  "topics": [
    {{
      "id": "t1",
      "title": "...",
      "hook": "One punchy opening sentence that stops the scroll",
      "why_trending": "One sentence on why this hits for this audience right now"
    }}
  ]
}}"""

SCRIPT_PROMPT = """You are a world-class short-form video script writer.

Write a 70-90 second Shorts/Reels script for this topic: "{topic}"

AUDIENCE: {audience}
TONE & VOICE: {tone}
LANGUAGE STYLE: {language_style}
HOOK REPERTOIRE (use ONE of these approaches for scene 1): {hook_styles}
VISUAL STYLE: {broll_style}

STRUCTURE RULES:
- 7 scenes total
- Scene 1 — HOOK (8-12s): Stop the scroll in the first 3 words. Use one hook type from above. Make it impossible to swipe away.
- Scenes 2-6 — VALUE (10-14s each): Deliver concrete, specific insight. No filler. Each scene = one clear idea. Build to a satisfying arc.
- Scene 7 — CTA (8-12s): Natural, not salesy. Give them a reason to save, share, or follow.

WRITING RULES:
- Write like you're talking to ONE person, not an audience
- Short sentences. Punchy rhythm. No corporate speak.
- Every sentence must earn its place — cut anything that doesn't inform or hook
- Use the TONE and LANGUAGE STYLE for this niche consistently throughout
- B-roll prompts must be SPECIFIC to this topic, not generic stock-photo clichés

Output ONLY this exact JSON — no markdown, no explanation:
{{
  "title": "...",
  "description": "...",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"],
  "scenes": [
    {{
      "scene_id": "scene_01",
      "voiceover_text": "...",
      "target_duration_seconds": 10,
      "broll_prompt": "...",
      "platform": "shorts"
    }}
  ]
}}"""

# Per-niche voice guide — passed into both prompts so Claude knows
# exactly who it's writing for, what tone to use, and what hooks land.
NICHE_VOICE = {
    "finance": {
        "audience": "25-40 year olds anxious about money, wanting financial independence, skeptical of 'get rich quick' but hungry for actionable steps",
        "tone": "authoritative but accessible — like a smart friend who works in finance, not a banker; direct, credible, slightly urgent",
        "language_style": "plain English, specific numbers and percentages where possible, avoid jargon unless you immediately explain it",
        "hook_styles": "shocking stat ('The average person loses $X to Y'), myth-busting ('Stop doing X — it's costing you'), uncomfortable truth ('Most people will never retire because of this one thing'), specific number hook ('3 accounts, $100/month, 1 million dollars')",
        "broll_style": "clean money visuals — stacks of bills, stock charts, phone showing banking app, person reviewing budget on laptop, real estate, coffee shop receipt, paycheck stub",
    },
    "entrepreneurship": {
        "audience": "aspiring founders and early-stage entrepreneurs 22-38, frustrated with 9-5, looking for permission and practical path to building something",
        "tone": "honest and real — like a founder 2 years ahead of them, not a guru; mix of encouragement and hard truth, zero hype",
        "language_style": "conversational, first-person stories work well, specific dollar amounts and timelines build credibility, avoid buzzwords like 'synergy' or 'pivot'",
        "hook_styles": "personal failure story ('I lost $40k because of this mistake'), contrarian take ('Your business idea doesn't need to be original'), direct identity challenge ('If you do these 3 things, you're not built for a 9-5'), specific result ('One conversation added $50k to my revenue')",
        "broll_style": "real workspace vibes — laptop with analytics dashboard, person on phone looking stressed then relieved, whiteboard with business plan, home office setup, delivery box with logo, Shopify/Stripe dashboard on screen",
    },
    "health": {
        "audience": "health-conscious 25-45 year olds who feel overwhelmed by conflicting health advice, want simple evidence-based habits, not extreme diets",
        "tone": "calm, informed, and reassuring — like a knowledgeable friend, not a drill sergeant; science-backed but never condescending",
        "language_style": "simple biology explanations that make people feel smart, avoid fearmongering, use 'your body' language to make it personal",
        "hook_styles": "body function reveal ('Your gut has more neurons than your spine — here's why that matters'), myth-bust ('The health advice your doctor never has time to give you'), pattern interrupt ('Stop eating breakfast. Here's what happens'), counterintuitive science ('The cheapest longevity drug costs nothing')",
        "broll_style": "clean health visuals — fresh food close-ups, person sleeping peacefully, morning routine, bloodwork results on screen, person hiking, doctor consultation, supplement bottles, gut anatomy diagram",
    },
    "tech": {
        "audience": "tech-curious 20-40 year olds who want to stay ahead of trends, use tools to save time, and understand what's actually changing vs hype",
        "tone": "enthusiastic but grounded — a tech-savvy friend who cuts through the hype and tells you what actually matters and what to ignore",
        "language_style": "concrete examples over abstract concepts, show the 'so what' for normal people, avoid acronyms without explanation",
        "hook_styles": "speed demonstration ('This tool does in 30 seconds what took me 3 hours'), future shock ('By 2026 this will replace X — here's what to do now'), tool reveal ('I deleted 10 apps and replaced them with this one'), skeptic flip ('I thought AI was overhyped — then this happened')",
        "broll_style": "screen recordings of apps working, side-by-side before/after comparisons, person's face reacting to impressive result on screen, futuristic UI, code editor, notification on phone, product demo",
    },
    "mindset": {
        "audience": "self-improvement seekers 22-38 who feel stuck or unfulfilled despite doing 'everything right', looking for a perspective shift not a 5-step list",
        "tone": "philosophical and calm but with urgency — Stoic-influenced, measured, the kind of voice that makes you pause and think",
        "language_style": "thoughtful and layered — ask questions that stick, use short punchy sentences after longer setups, reference psychology/philosophy lightly without being academic",
        "hook_styles": "assumption challenge ('You're not lazy. You're operating on the wrong goal'), identity reframe ('The person you want to become already exists — you're just not acting like them yet'), uncomfortable truth ('Nobody is coming to save you'), paradox opener ('The more you chase happiness, the further it gets')",
        "broll_style": "contemplative visuals — person alone looking at horizon, journaling, meditating at sunrise, slow-motion walk in nature, hands writing, clock ticking, minimalist room, person staring out window in thought",
    },
    "productivity": {
        "audience": "ambitious 25-40 year olds who feel overwhelmed and behind, want to work smarter not harder, frustrated that their effort isn't converting to results",
        "tone": "practical and no-nonsense — like a systems thinker who has already optimised their life and is showing you the shortcut, zero fluff",
        "language_style": "specific, numbered, actionable — 'Do X, then Y, in Z minutes' structure works well, use before/after framing",
        "hook_styles": "time shock ('I saved 3 hours a day by stopping this one habit'), system reveal ('This $0 system is why I never miss a deadline'), myth-bust ('Your to-do list is why you're unproductive'), speed challenge ('I ran my entire week in 20 minutes on Sunday')",
        "broll_style": "clean desk with minimal setup, calendar/task app on screen, timer running, person focused typing with no distractions, physical notebook with clear handwriting, morning routine time-lapse, phone with notifications turned off",
    },
    "ai": {
        "audience": "knowledge workers and entrepreneurs 25-45 who want to use AI to save time and stay competitive, not be replaced, a mix of excited and anxious",
        "tone": "pragmatic and forward-thinking — someone who has actually used these tools at depth and is sharing what actually works, not what's impressive in a demo",
        "language_style": "show don't tell — specific tool names, exact prompts, real results with numbers; avoid 'revolutionary' and 'game-changing' — show the actual game change",
        "hook_styles": "live result ('I gave this prompt to Claude and got this in 8 seconds'), replacement reveal ('I let go of my copywriter. This tool replaced them'), capability shock ('ChatGPT can do this — most people have no idea'), personal ROI ('This AI workflow saves me 12 hours every week')",
        "broll_style": "screen capture of AI tool in action, side-by-side prompt and output, chat interface with impressive response, before/after work comparison, person's face reacting to AI output, workflow automation diagram",
    },
    "marketing": {
        "audience": "small business owners, creators, and marketers 25-40 who feel like they're shouting into the void — posting consistently but not growing",
        "tone": "sharp, savvy, and slightly provocative — a marketing insider who knows the game and isn't afraid to call out what's not working",
        "language_style": "direct and opinionated, use platform-specific language (algorithm, hooks, retention), back claims with examples or numbers from real accounts",
        "hook_styles": "platform insider reveal ('The algorithm change nobody is talking about'), counter-strategy ('Stop posting daily — here's what actually grows accounts'), case study hook ('This 60-second video got 2 million views — here's the exact structure'), myth-bust ('Engagement rate means nothing. Here's what does')",
        "broll_style": "social media analytics dashboard, content calendar, person filming vertical video, comment section showing engagement, viral video screenshot, brand logo, ad creative mockup, phone with growing follower count",
    },
    "relationships": {
        "audience": "20-35 year olds navigating dating, early relationships, or wanting to improve how they connect with others — looking for real insight not generic advice",
        "tone": "warm but honest — like a psychologically-literate friend who tells you the truth with compassion, not judgment",
        "language_style": "relatable scenarios and specific examples, 'you've probably done this' framing, psychology-informed without being clinical",
        "hook_styles": "relatable scenario ('If you go quiet when you're upset, this is for you'), psychology reveal ('There's a word for what you're feeling — and once you know it, everything makes sense'), uncomfortable mirror ('The reason your relationships keep failing has nothing to do with the other person'), pattern interrupt ('Stop trying to fix your communication — do this instead')",
        "broll_style": "couple interactions (tasteful), person alone looking thoughtful, phone with message thread, coffee conversation, person journaling about a relationship, hands intertwined, person looking relieved after a conversation",
    },
    "fitness": {
        "audience": "25-40 year olds who want to get fit but are confused by conflicting advice, short on time, and skeptical of extreme programs — want sustainable results",
        "tone": "motivating but realistic — a knowledgeable training partner who respects that you have a life outside the gym, zero bro-science",
        "language_style": "energetic and direct, specific numbers (sets, reps, minutes, weeks), use 'your body' language, debunk myths with simple science",
        "hook_styles": "result promise with timeframe ('3 exercises. 20 minutes. Every major muscle group'), myth-bust ('Doing cardio to lose weight is keeping you fat'), science flip ('Your muscle is built outside the gym — here's why'), transformation hook ('I changed one thing in my routine and lost 8kg in 10 weeks')",
        "broll_style": "gym close-ups (weights, cables, machines), person demonstrating exercise with correct form, transformation split-screen, healthy meal prep, sleep tracker showing 8 hours, protein shake, person checking physique in mirror with satisfaction",
    },
}

PLATFORM_RULES = {
    # All platforms use Shorts/Reels format (9:16 vertical, 70-90s)
    "tiktok":    "TikTok Shorts — hook must land in first 3 words, punchy rhythm, 70-90s total",
    "youtube":   "YouTube Shorts — hook must land in first 3 words, punchy rhythm, 70-90s total",
    "instagram": "Instagram Reels — hook must land in first 3 words, punchy rhythm, 70-90s total",
    "facebook":  "Facebook Reels — hook must land in first 3 words, punchy rhythm, 70-90s total",
    "shorts":    "Shorts/Reels — hook must land in first 3 words, punchy rhythm, 70-90s total",
}


def generate_topic_ideas(niche: str, platform: str) -> dict:
    """
    Generate 8 trending topic ideas for a given niche and platform.
    Uses Claude Max CLI. Falls back to curated mock topics if unavailable.
    """
    if os.getenv("MOCK_APIS", "true").lower() == "true":
        return _mock_topics(niche, platform)

    niche_info  = NICHES.get(niche, NICHES["finance"])
    voice       = NICHE_VOICE.get(niche, NICHE_VOICE["finance"])
    prompt = TOPIC_PROMPT.format(
        platform=platform,
        niche_label=niche_info["label"],
        niche_key=niche,
        audience=voice["audience"],
        tone=voice["tone"],
        hook_styles=voice["hook_styles"],
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


def generate_script(topic: str, platform: str, niche: str = "finance") -> dict:
    """
    Generate a full job blueprint JSON for a given topic, platform, and niche.
    Niche is used to inject audience/tone/hook context into the prompt.
    Uses Claude Max subscription via claude CLI. Falls back to mock if unavailable.
    """
    if MOCK_APIS:
        print("[MOCK] Generating script blueprint")
        return _mock_blueprint(topic, platform)

    try:
        return _generate_with_claude(topic, platform, niche)
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


def _generate_with_claude(topic: str, platform: str, niche: str = "finance") -> dict:
    """Call claude -p to generate the script JSON using Claude Max subscription."""
    import tempfile

    voice = NICHE_VOICE.get(niche, NICHE_VOICE["finance"])
    prompt = SCRIPT_PROMPT.format(
        topic=topic,
        platform=platform,
        audience=voice["audience"],
        tone=voice["tone"],
        language_style=voice["language_style"],
        hook_styles=voice["hook_styles"],
        broll_style=voice["broll_style"],
    )

    claude_cmd = _get_claude_cmd()

    print(f"🤖 Generating script via Claude Max for: '{topic}' ({platform}, {niche})")

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
        "job_id":      job_id,
        "status":      "pending",
        "platform":    platform,
        "platforms":   [platform],   # list — expanded by wizard to multi-select
        "title":       script.get("title", f"The Truth About {topic.title()}"),
        "description": script.get("description", ""),
        "hashtags":    script.get("hashtags", [f"#{topic.replace(' ', '')}"]),
        "scenes":      scenes,
        "renderer":    renderer,
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "approved_at": None,
        "output_path": None,
        "generated_by": "claude-max",
        "topic":       topic,
    }


def _mock_blueprint(topic: str, platform: str) -> dict:
    job_id = str(uuid.uuid4())
    scenes = [
        {
            "scene_id": "scene_01",
            "voiceover_text": f"Nobody talks about what {topic} is actually doing to your life. Here's the truth most people miss.",
            "target_duration_seconds": 10,
            "broll_prompt": f"{topic} close-up dramatic cinematic reveal slow motion golden hour lighting",
            "platform": "shorts",
        },
        {
            "scene_id": "scene_02",
            "voiceover_text": f"First thing to understand about {topic} — it's not what you think. Most people approach it completely wrong.",
            "target_duration_seconds": 12,
            "broll_prompt": "person looking confused at laptop screen, shallow depth of field, moody office lighting",
            "platform": "shorts",
        },
        {
            "scene_id": "scene_03",
            "voiceover_text": "Here's what the research actually shows. And the numbers are going to surprise you.",
            "target_duration_seconds": 12,
            "broll_prompt": "researcher pointing at data on whiteboard, focused expression, clean lab environment bright lighting",
            "platform": "shorts",
        },
        {
            "scene_id": "scene_04",
            "voiceover_text": f"The people who get {topic} right share one thing in common. They stopped doing what everyone else does.",
            "target_duration_seconds": 12,
            "broll_prompt": "successful person walking confidently through modern city at sunrise, tracking shot, cinematic",
            "platform": "shorts",
        },
        {
            "scene_id": "scene_05",
            "voiceover_text": "Most experts won't tell you this part — because it's inconvenient. But it's the most important thing.",
            "target_duration_seconds": 12,
            "broll_prompt": "expert speaking directly to camera in front of bookshelf, warm lighting, confident expression",
            "platform": "shorts",
        },
        {
            "scene_id": "scene_06",
            "voiceover_text": f"Once you understand this about {topic}, you can't unsee it. It changes every decision you make.",
            "target_duration_seconds": 12,
            "broll_prompt": "person having lightbulb moment at desk, looking up from laptop with surprised expression, natural light",
            "platform": "shorts",
        },
        {
            "scene_id": "scene_07",
            "voiceover_text": f"Start applying this to {topic} today. Share this with someone who needs to hear it. Follow for more.",
            "target_duration_seconds": 10,
            "broll_prompt": "person smiling confidently at sunrise, motivated energy, cinematic dolly forward shot, hopeful",
            "platform": "shorts",
        },
    ]
    return {
        "job_id":      job_id,
        "status":      "pending",
        "platform":    platform,
        "platforms":   [platform],
        "title":       f"The Truth About {topic.title()}",
        "description": f"What most people get wrong about {topic} — and how to fix it.",
        "hashtags":    [f"#{topic.replace(' ', '')}", "#shorts", "#fyp", "#reels", "#viral"],
        "scenes":      scenes,
        "renderer":    "ffmpeg",
        "created_at":  datetime.now(timezone.utc).isoformat(),
        "approved_at": None,
        "output_path": None,
        "generated_by": "mock",
        "topic":       topic,
    }


if __name__ == "__main__":
    import sys
    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "artificial intelligence"
    os.environ["MOCK_APIS"] = "false"
    job = generate_script(topic, "tiktok")
    print(json.dumps(job, indent=2))
