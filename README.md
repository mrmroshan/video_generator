# Video Generator — Automated Short-Form Video Pipeline

End-to-end short-form video production: niche → topic → AI script → TTS voiceover → B-roll → captions → review → multi-platform export.

## Features

- **Job Creation Wizard** — pick niche, select platforms, auto-generate 7-scene Shorts script
- **Multi-Platform** — one 70-90s script rendered to 720×1280 (9:16), auto-exported to TikTok / Instagram / YouTube Shorts / Facebook Reels
- **AI Script** — Claude Max generates hook → value → CTA structure per niche
- **TTS Voiceover** — ElevenLabs Adam voice (eleven_multilingual_v2)
- **Karaoke Captions** — Whisper word-level timestamps → word-by-word highlight sync
- **B-roll** — Pexels stock footage per scene
- **Review Dashboard** — edit script, swap B-roll, reorder scenes, change caption style
- **Save Draft** — save edits without committing to render; come back later
- **Approve & Render** — lock approved jobs → FFmpeg render → captioned MP4

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- FFmpeg 5+ in PATH
- `claude` CLI: `npm install -g @anthropic-ai/claude-code` (logged in with Max subscription)

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set ELEVENLABS_API_KEY and PEXELS_API_KEY

cd dashboard && npm install && cd ..
```

### Run

```bash
# Terminal 1 — API server
python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8001

# Terminal 2 — React dashboard (dev)
cd dashboard && npm run dev

# Open http://localhost:5173
```

Or use the convenience script:

```bash
bash start.sh
```

### API docs

`http://localhost:8001/docs`

## Architecture

```
Wizard
  → Niche + Topic + Platform selection
  → Phase 1: Claude Max script (7 scenes, 70-90s, Shorts structure)
  → Phase 2: ElevenLabs TTS + Whisper timestamps + Pexels B-roll
  → Review dashboard (edit / save draft / approve)
  → Phase 3: FFmpeg render at 720×1280 (9:16 master)
  → Phase 4: Auto-export to all selected platforms
```

## Job Status Flow

```
pending → in_review → draft (save draft) → approved → rendering → done
                   └──────────────────────────────────────────────↑
```

## Platform Exports

All platforms use **9:16 vertical** (Shorts / Reels format):

| Platform | Dimensions | Format |
|----------|-----------|--------|
| TikTok | 720×1280 | TikTok video |
| Instagram | 720×1280 | Reels |
| YouTube | 720×1280 | Shorts |
| Facebook | 720×1280 | Reels |

## Caption Styles

| Style | Description |
|-------|-------------|
| `karaoke` | Word-by-word highlight (default) |
| `karaoke_tiktok` | Bold centre highlight, Impact font |
| `karaoke_fire` | Animated fire effect highlight |
| `clean` | Static subtitle, clean font |
| `cinematic` | Cinematic lower-third style |
| `tiktok` | Giant Impact, thick outline |
| `minimal` | Minimal bottom caption |

Karaoke styles use Whisper word-level timestamps for frame-accurate sync.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ELEVENLABS_API_KEY` | Yes | ElevenLabs TTS API key |
| `PEXELS_API_KEY` | Yes | Pexels stock footage API key |
| `MOCK_APIS` | No | `true` to skip all API calls (dev/test) |
| `CLAUDE_CMD` | No | Override path to `claude` CLI |

See `.env.example` for all variables.

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Build frontend
npm run build --prefix dashboard

# Mock mode (no API calls, instant)
MOCK_APIS=true python pipeline.py --topic "5 AI tools"
```

## Tech Stack

| Layer | Tech |
|-------|------|
| Script AI | Claude Max (claude-opus-4) via `claude -p` CLI |
| TTS | ElevenLabs Adam — eleven_multilingual_v2 |
| Timestamps | faster-whisper 1.2.1 — base model, CPU int8 |
| B-roll | Pexels API |
| Render | FFmpeg 5+ (libx264 baseline, ASS subtitles) |
| Backend | FastAPI + uvicorn |
| Frontend | React + Vite |
| Storage | SQLite (via `data/db.py`) |
| Tests | pytest — 57 tests |
