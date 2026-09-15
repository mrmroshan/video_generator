# Video Generator — AI Short-Form Video Pipeline

End-to-end short-form video production: niche → topic → AI script → TTS voiceover → B-roll → karaoke captions → review dashboard → multi-platform export.

---

## Features

| Feature | Detail |
|---------|--------|
| **Job Creation Wizard** | Pick niche → auto-generate 8 topic ideas → select topic → generate video |
| **Niche-Aware Scripts** | 10 niches × unique audience, tone, hook styles, language guide, visual style |
| **AI Script** | Claude Max — 7-scene Shorts structure (hook → value × 5 → CTA), 70-90s |
| **TTS Voiceover** | ElevenLabs Adam — eleven_multilingual_v2, stability 0.65 |
| **Karaoke Captions** | Whisper word-level timestamps → frame-accurate word-by-word highlight sync |
| **B-roll** | Pexels stock footage per scene, swappable in review |
| **Review Dashboard** | Edit script, swap B-roll, reorder scenes, change caption style |
| **Save Draft** | Save edits without locking — come back and keep editing |
| **Approve & Render** | Lock → FFmpeg render at 720×1280 (9:16 master) |
| **Multi-Platform Export** | Auto-export to all selected platforms after render |

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- FFmpeg 5+ in PATH
- `claude` CLI: `npm install -g @anthropic-ai/claude-code` (logged in with Claude Max)

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set ELEVENLABS_API_KEY and PEXELS_API_KEY

cd dashboard && npm install && cd ..
```

### Run

```bash
bash start.sh
# Opens: http://localhost:5173  (dashboard)
#        http://localhost:8001/docs  (API docs)
```

Or manually:

```bash
# Terminal 1 — API
python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8001

# Terminal 2 — UI (dev)
cd dashboard && npm run dev
```

### CLI (no dashboard)

```bash
# Mock mode (no API calls)
MOCK_APIS=true python pipeline.py --topic "5 AI tools" --niche ai --platform tiktok

# Live mode
python pipeline.py --topic "5 AI tools" --niche ai --platform tiktok
```

---

## Architecture

```
Wizard UI
  ├── Pick niche (10 options)
  ├── Select platforms (TikTok / Instagram / YouTube / Facebook — all pre-checked)
  ├── Choose topic (AI-generated, niche-aware)
  └── Generate →

Phase 1 — Script
  └── Claude Max: 7-scene Shorts script with niche-specific audience, tone, hooks

Phase 2 — Assets
  ├── ElevenLabs TTS: voiceover per scene
  ├── faster-whisper: word-level timestamps for karaoke sync
  └── Pexels: B-roll footage per scene

Phase 3 — Human Review (dashboard)
  ├── Edit voiceover text per scene
  ├── Swap B-roll (search + pick new clip)
  ├── Reorder scenes (drag-and-drop)
  ├── Change caption style
  ├── 💾 Save Draft  (editable, not locked)
  └── ✓ Approve & Lock

Phase 4 — Render
  └── FFmpeg: render 720×1280 (9:16) master with burned-in captions

Phase 5 — Export
  └── Auto-export to all selected platforms (same 9:16 dims)
```

---

## Job Status Flow

```
pending → in_review ──→ draft ──→ approved → rendering → done
              └─────────────────────────↑
              (edits preserve draft status)
```

---

## Niche System

10 niches, each with a distinct voice profile injected into Claude:

| Niche | Audience | Tone |
|-------|----------|------|
| Finance | 25-40, money-anxious, want independence | Authoritative friend, credible, urgent |
| Entrepreneurship | 22-38, frustrated with 9-5 | Honest founder, zero hype |
| Health | 25-45, overwhelmed by advice | Calm, science-backed, reassuring |
| Technology | 20-40, want to stay ahead | Enthusiastic, cuts through hype |
| Mindset | 22-38, feel stuck | Stoic, philosophical, makes you pause |
| Productivity | 25-40, overwhelmed | No-nonsense systems thinker |
| AI & Future | 25-45, excited + anxious | Pragmatic, shows real results |
| Marketing | 25-40, not growing | Sharp, insider, calls out what doesn't work |
| Relationships | 20-35, want real insight | Warm, psychologically-literate |
| Fitness | 25-40, short on time | Motivating, realistic, zero bro-science |

---

## Platform Exports

All platforms use **9:16 vertical** (Shorts / Reels):

| Platform | Dimensions | Format |
|----------|-----------|--------|
| TikTok | 720×1280 | TikTok video / Shorts |
| Instagram | 720×1280 | Reels |
| YouTube | 720×1280 | Shorts |
| Facebook | 720×1280 | Reels |

---

## Caption Styles

| Style | Description |
|-------|-------------|
| `karaoke` | Word-by-word highlight (default) |
| `karaoke_tiktok` | Bold centre highlight, Impact font |
| `karaoke_fire` | Animated fire effect |
| `clean` | Static subtitle |
| `cinematic` | Lower-third cinematic |
| `tiktok` | Giant Impact, thick outline |
| `minimal` | Minimal bottom caption |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/niches` | All niches with metadata |
| POST | `/topics` | Generate 8 topic ideas for niche |
| POST | `/jobs/create` | Start wizard pipeline (async) |
| GET | `/jobs/{id}/progress` | Poll pipeline progress |
| GET | `/jobs` | List all jobs |
| PATCH | `/jobs/{id}/scenes/{scene_id}` | Edit scene voiceover/duration |
| POST | `/jobs/{id}/reorder` | Reorder scenes |
| POST | `/jobs/{id}/save-draft` | Save as draft (keeps editable) |
| POST | `/jobs/{id}/approve` | Lock for render |
| POST | `/jobs/{id}/render` | Start FFmpeg render (async) |
| GET | `/jobs/{id}/render-status` | Poll render progress |
| POST | `/jobs/{id}/export/{platform}` | Export to specific platform |
| GET | `/jobs/{id}/output` | Download rendered MP4 |
| GET | `/caption-styles` | List available caption styles |
| PATCH | `/jobs/{id}/caption-style` | Change caption style |
| GET | `/platforms` | Platform dimensions and metadata |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ELEVENLABS_API_KEY` | ✅ | ElevenLabs TTS API key |
| `PEXELS_API_KEY` | ✅ | Pexels stock footage API key |
| `MOCK_APIS` | No | `true` to skip all API calls (dev/test mode) |
| `CLAUDE_CMD` | No | Override path to `claude` CLI |
| `DB_PATH` | No | SQLite DB path (default: `./data/video_maker.db`) |
| `JOBS_DIR` | No | Job files directory (default: `./data/jobs`) |

See `.env.example` for full reference.

---

## Development

```bash
python -m pytest tests/ -v          # 57 tests
npm run build --prefix dashboard    # build frontend
MOCK_APIS=true python pipeline.py --topic "test" --niche finance
```

---

## Tech Stack

| Layer | Tech | Version |
|-------|------|---------|
| Script AI | Claude Max via `claude -p` CLI | claude-opus-4 |
| TTS | ElevenLabs Adam | eleven_multilingual_v2 |
| Speech-to-timestamps | faster-whisper | 1.2.1, CPU int8 |
| B-roll | Pexels API | — |
| Render | FFmpeg | 5+ (libx264 baseline, ASS subtitles) |
| Backend | FastAPI + uvicorn | 0.100+ |
| Frontend | React + Vite | — |
| Storage | SQLite | via `data/db.py` |
| Tests | pytest | 57 tests |

---

## Not Built Yet

| Feature | Status |
|---------|--------|
| Direct publish to TikTok / YouTube | `NotImplementedError` — use `distribution/publishers/distribute.py` stub |
| Background music | Intentionally excluded — use CapCut for trending sounds |
| Remotion renderer | Stubbed — `renderer='ffmpeg'` is the active path |
