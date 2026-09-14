# VIDEO MAKER — Automated Video Generation Pipeline

End-to-end video production: topic → script → TTS → B-roll → captions → review → export.

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+ (for dashboard)
- FFmpeg 5+ in PATH
- `claude` CLI: `npm install -g @anthropic-ai/claude-code` (logged in with Max subscription)

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set ELEVENLABS_API_KEY, PEXELS_API_KEY

cd dashboard && npm install && cd ..
bash start.sh
```

### Generate a video

```bash
# Mock mode (no API calls)
MOCK_APIS=true python pipeline.py --topic "5 AI tools" --platform youtube

# Live mode
python pipeline.py --topic "5 AI tools" --platform youtube

# Review dashboard  →  http://localhost:5173
# API docs          →  http://localhost:8000/docs
```

## Architecture

```
Topic → Phase 1: Claude script   → Phase 2: ElevenLabs TTS + Whisper + Pexels
      → Phase 3: Human review    → Phase 4: FFmpeg render + captions
      → Phase 5: Export (YouTube / TikTok / Instagram / Facebook)
```

## Platform Export Sizes

| Platform | Size | Use |
|---|---|---|
| YouTube / Facebook | 1280×720 | 16:9 landscape |
| TikTok / IG Reels / FB Reels | 720×1280 | 9:16 vertical |
| Instagram Post | 720×720 | 1:1 square |

## Caption Styles

`clean` · `cinematic` · `tiktok` · `minimal` · `karaoke` · `karaoke_tiktok` · `karaoke_fire`

Karaoke styles use Whisper word-level timestamps for word-by-word highlight sync.

## Development

```bash
pytest tests/ -v          # run test suite
npm run build --prefix dashboard  # build frontend
```

## Environment Variables

See `.env.example` for all required variables and documentation.
