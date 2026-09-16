# Veo 2 B-roll Pipeline — Second Pipeline Mode

> **Status:** PLANNED — not built yet.
> **To build:** Say "build the Veo 2 pipeline" and I'll execute task by task.

**Goal:** Add a second b-roll mode to the existing pipeline. When `broll_source=veo2`, each scene's `broll_prompt` is sent to Google's Veo 2 model to generate a custom 8-second video clip instead of searching Pexels. Everything else (script, TTS, captions, render, review, publish) stays identical.

**Approach:** Drop-in replacement at the `fetch_broll_for_job()` layer. The pipeline doesn't care where `broll_path` comes from — it just needs an MP4 file at that path. Add a new `assets/veo.py` module, a thin orchestrator `assets/broll.py`, and wire a `broll_source` field through the wizard and job record.

**SDK:** `google-genai 2.10.0` — already installed. Uses `client.models.generate_videos()`.

**API Key:** `GEMINI_API_KEY` in `.env` — same key used in OCI project. Add to this project's `.env`.

---

## How Veo 2 Works (API)

```python
from google import genai
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

operation = client.models.generate_videos(
    model="veo-2.0-generate-001",
    prompt="Close-up of a hand circling a number on a bank statement, 
            warm desk lamp, shallow depth of field, cinematic",
    config=genai.types.GenerateVideosConfig(
        aspect_ratio="9:16",        # vertical Shorts format
        duration_seconds=8,          # 5-8s supported
        number_of_videos=1,
    ),
)

# Poll until done (typically 30-90s)
while not operation.done:
    time.sleep(10)
    operation = client.operations.get(operation)

video_bytes = operation.result.generated_videos[0].video.video_bytes
with open(dest_path, "wb") as f:
    f.write(video_bytes)
```

**Constraints:**
- Duration: 5-8 seconds (we'll use 8)
- Aspect ratio: supports `9:16` ✅ — matches our 720×1280 master
- Generation time: ~30-90s per clip
- Total pipeline time: ~4-10 min for 7 scenes (can run parallel)
- Requires Gemini API key with Veo 2 access enabled

**Cost estimate (Veo 2 pricing):**
- ~$0.30-0.50 per 8-second clip
- 7 scenes × $0.35 avg = ~$2.50 per video
- At 1 video/day = ~$75/month for b-roll

---

## Architecture

```
BEFORE (Pexels mode):
  broll_prompt → Pexels search API → download clip → broll_path

AFTER (two modes via broll_source field):
  job.broll_source = "pexels"  → assets/stock.py (unchanged)
  job.broll_source = "veo2"    → assets/veo.py   (new)

Orchestrator (assets/broll.py — new):
  def fetch_broll_for_job(job):
      if job.get("broll_source") == "veo2":
          return fetch_broll_veo2(job)
      return fetch_broll_pexels(job)   # existing logic
```

The rest of the pipeline is untouched.

---

## Files to Create / Modify

| File | Action | What |
|------|--------|------|
| `assets/veo.py` | **CREATE** | Veo 2 clip generation per scene |
| `assets/broll.py` | **CREATE** | Orchestrator — routes to pexels or veo2 |
| `assets/stock.py` | **MODIFY** | Rename `fetch_broll_for_job` → `fetch_broll_pexels` (keep as-is internally) |
| `dashboard/server.py` | **MODIFY** | Pass `broll_source` through wizard; update progress message; add `broll_source` to `CreateJobPayload` |
| `orchestration/crew.py` | **NO CHANGE** | `broll_prompt` already written for cinematic AI generation |
| `pipeline.py` | **MODIFY** | Add `--broll-source pexels|veo2` arg |
| `dashboard/src/components/NicheWizard.jsx` | **MODIFY** | Add b-roll source toggle |
| `dashboard/src/App.css` | **MODIFY** | Toggle styles |
| `requirements.txt` | **NO CHANGE** | `google-genai` already installed |
| `.env.example` | **MODIFY** | Add `GEMINI_API_KEY` |
| `.gitignore` | **NO CHANGE** | Already ignores `.env` |
| `tests/test_veo_broll.py` | **CREATE** | Unit tests with mocked Veo API |

---

## Task 1: assets/veo.py — Veo 2 clip generator

**Objective:** Generate one 8s 9:16 clip from a text prompt using Veo 2.

**File:** `assets/veo.py`

**Full implementation:**

```python
"""
assets/veo.py — Veo 2 video generation via Google Gemini API

Generates an 8-second 9:16 clip from a broll_prompt.
Each scene in the job gets its own clip.

MOCK_APIS=true → creates a silent black MP4 stub (no API call).
"""
import os
import time
import subprocess
from pathlib import Path

MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def generate_clip(prompt: str, dest_path: str, duration: int = 8) -> str:
    """
    Generate a single Veo 2 clip from prompt.
    Saves to dest_path. Returns dest_path.
    Raises RuntimeError on failure.
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    if MOCK_APIS or os.getenv("MOCK_APIS", "true").lower() == "true":
        _write_mock_clip(dest_path, duration)
        print(f"[MOCK/VEO2] Clip → {dest_path}")
        return dest_path

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set — cannot generate Veo 2 clip")

    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)

    print(f"  [VEO2] Generating clip: {prompt[:80]}...")

    operation = client.models.generate_videos(
        model="veo-2.0-generate-001",
        prompt=prompt,
        config=genai.types.GenerateVideosConfig(
            aspect_ratio="9:16",
            duration_seconds=duration,
            number_of_videos=1,
        ),
    )

    # Poll until done (Veo 2 typically takes 30-90s)
    max_wait = 180  # seconds
    waited   = 0
    poll_interval = 10

    while not operation.done:
        if waited >= max_wait:
            raise RuntimeError(f"Veo 2 generation timed out after {max_wait}s")
        time.sleep(poll_interval)
        waited += poll_interval
        operation = client.operations.get(operation)
        print(f"  [VEO2] Waiting... ({waited}s)")

    videos = operation.result.generated_videos
    if not videos:
        raise RuntimeError("Veo 2 returned no videos")

    video_bytes = videos[0].video.video_bytes
    if not video_bytes:
        raise RuntimeError("Veo 2 video bytes are empty")

    with open(dest_path, "wb") as f:
        f.write(video_bytes)

    print(f"  [VEO2] ✓ {dest_path} ({len(video_bytes)//1024}KB)")
    return dest_path


def _write_mock_clip(dest_path: str, duration: int = 8):
    """Write a silent black MP4 stub using FFmpeg (for MOCK_APIS=true)."""
    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:s=720x1280:r=30:d={duration}",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            "-c:v", "libx264", "-profile:v", "baseline",
            "-c:a", "aac", "-shortest",
            dest_path,
        ], capture_output=True, check=True)
    except Exception:
        # Ultimate fallback — empty file (render will skip it gracefully)
        Path(dest_path).write_bytes(b"MOCK_VEO2_CLIP")


def fetch_broll_veo2(job: dict) -> dict:
    """
    Generate Veo 2 clips for all scenes in a job.
    Adds 'broll_path' to each scene. Returns updated job.
    Scenes are processed sequentially (API rate limits).
    """
    job_dir = os.path.join(
        os.getenv("JOBS_DIR", "./data/jobs"),
        job["job_id"]
    )
    os.makedirs(job_dir, exist_ok=True)

    for scene in job.get("scenes", []):
        scene_id    = scene["scene_id"]
        broll_path  = os.path.join(job_dir, f"{scene_id}_broll.mp4")
        prompt      = scene.get("broll_prompt", f"cinematic short video clip, 9:16 vertical")

        # Enrich prompt for Veo 2 — add style context
        enriched = _enrich_prompt(prompt, job.get("niche", ""))

        try:
            generate_clip(enriched, broll_path)
            scene["broll_path"]   = broll_path
            scene["broll_source"] = "veo2"
        except Exception as e:
            print(f"  [WARN] Veo 2 failed for {scene_id}: {e}")
            scene["broll_path"]   = None
            scene["broll_source"] = "veo2_failed"

    return job


def _enrich_prompt(prompt: str, niche: str) -> str:
    """
    Append consistent cinematic style guidance to the broll_prompt.
    Keeps prompts concise — Veo 2 works better with focused prompts.
    """
    style_suffixes = {
        "finance":        "cinematic, warm colour grade, shallow depth of field, 4K",
        "entrepreneurship": "documentary style, natural light, handheld energy",
        "health":         "clean bright aesthetic, soft natural light, calm",
        "tech":           "sleek modern, blue-tinted light, sharp focus",
        "mindset":        "moody cinematic, golden hour, contemplative",
        "productivity":   "clean minimal, natural light, focused energy",
        "ai":             "futuristic, blue-purple tones, sharp crisp",
        "marketing":      "bold vibrant, high contrast, energetic",
        "fitness":        "high energy, warm golden tones, dynamic motion",
        "relationships":  "warm intimate, soft bokeh, authentic moments",
    }
    suffix = style_suffixes.get(niche, "cinematic, 4K, professional")
    # Avoid duplicating style words already in prompt
    if "cinematic" in prompt.lower():
        return prompt
    return f"{prompt}, {suffix}"
```

**Tests (`tests/test_veo_broll.py`):**
```python
def test_generate_clip_mock_creates_file(tmp_path)
def test_fetch_broll_veo2_adds_broll_path(tmp_path, monkeypatch)
def test_fetch_broll_veo2_handles_single_scene_failure(monkeypatch)
def test_enrich_prompt_adds_style_for_finance()
def test_enrich_prompt_skips_if_cinematic_present()
def test_generate_clip_raises_without_api_key(monkeypatch)
```

**Commit:** `feat: assets/veo.py — Veo 2 clip generation`

---

## Task 2: assets/broll.py — Orchestrator

**Objective:** Single entry point that routes to Pexels or Veo 2 based on job's `broll_source`.

**File:** `assets/broll.py`

```python
"""
assets/broll.py — B-roll orchestrator

Routes to Pexels or Veo 2 based on job["broll_source"].
  "pexels" (default) → assets/stock.py
  "veo2"             → assets/veo.py
"""

def fetch_broll_for_job(job: dict) -> dict:
    """Fetch b-roll for all scenes. Source determined by job['broll_source']."""
    source = job.get("broll_source", "pexels")

    if source == "veo2":
        from assets.veo import fetch_broll_veo2
        return fetch_broll_veo2(job)

    # Default: Pexels
    from assets.stock import fetch_broll_pexels
    return fetch_broll_pexels(job)
```

**Modify `assets/stock.py`:**
- Rename `fetch_broll_for_job` → `fetch_broll_pexels` (add alias for backward compat)
- Keep all internal logic identical

```python
# Add alias so existing imports still work during transition
fetch_broll_for_job = fetch_broll_pexels
```

**Tests:**
```python
def test_orchestrator_routes_pexels_by_default(monkeypatch)
def test_orchestrator_routes_veo2_when_set(monkeypatch)
def test_orchestrator_uses_pexels_for_unknown_source(monkeypatch)
```

**Commit:** `feat: assets/broll.py — b-roll orchestrator (pexels|veo2)`

---

## Task 3: Wire broll_source through server.py + pipeline.py

**Objective:** Pass `broll_source` from wizard payload through to job record and into the fetch step.

### server.py changes

**1. `CreateJobPayload` model — add field:**
```python
class CreateJobPayload(BaseModel):
    ...
    broll_source: str = "pexels"   # "pexels" | "veo2"
```

**2. `_run_wizard_pipeline` — stamp on job + update import:**
```python
# After generate_script() returns:
job["broll_source"] = getattr(payload, "broll_source", "pexels")

# Update progress message dynamically:
source_label = "Veo 2 AI" if job.get("broll_source") == "veo2" else "Pexels"
update_progress(job_id, "downloading_broll", 
    f"Generating B-roll with {source_label}... (this takes longer for Veo 2)")

# Change import from assets.stock to assets.broll:
from assets.broll import fetch_broll_for_job
```

**3. Top-level import fix:**
```python
# Remove: from assets.stock import _search_pexels, _download_video
# Keep only in the endpoint that uses them directly (search-broll)
```

### pipeline.py changes
```python
parser.add_argument("--broll-source", choices=["pexels", "veo2"], default="pexels",
                    help="B-roll source: pexels (free, fast) or veo2 (AI-generated, slower)")
```
```python
job["broll_source"] = args.broll_source
```

**Tests:**
```python
def test_wizard_defaults_to_pexels(client)
def test_wizard_accepts_veo2_source(client)
def test_wizard_rejects_unknown_broll_source(client)
def test_veo2_progress_message_says_ai(client, monkeypatch)
```

**Commit:** `feat: wire broll_source through wizard + pipeline`

---

## Task 4: Frontend — B-roll source toggle in NicheWizard

**Objective:** Let user choose Pexels or Veo 2 before generating a video.

**File:** `dashboard/src/components/NicheWizard.jsx`

**Where it goes:** Below platform checkboxes, above the "Generate Topics" button.

**UI:**
```
B-roll Source
  ○ 📦 Pexels  Free · Fast · Stock footage
  ● 🤖 Veo 2   AI-generated · ~3 min · ~$2.50/video
```

**Implementation:**
```jsx
const [brollSource, setBrollSource] = useState('pexels')

// In the payload sent to POST /jobs/create:
broll_source: brollSource

// UI:
<div className="broll-source-picker">
  <p className="broll-source-label">B-roll Source</p>
  <label className={`broll-option${brollSource==='pexels'?' active':''}`}>
    <input type="radio" value="pexels"
      checked={brollSource==='pexels'}
      onChange={() => setBrollSource('pexels')} />
    <span>📦 Pexels</span>
    <span className="broll-option-desc">Free · Fast · Stock footage</span>
  </label>
  <label className={`broll-option${brollSource==='veo2'?' active':''}`}>
    <input type="radio" value="veo2"
      checked={brollSource==='veo2'}
      onChange={() => setBrollSource('veo2')} />
    <span>🤖 Veo 2</span>
    <span className="broll-option-desc">AI-generated · ~3 min · ~$2.50/video</span>
  </label>
</div>
```

**Also update TopicBank.jsx `start_video_from_topic` call:**
- Default to `pexels` (no UI in topic bank — can add later)

**Commit:** `feat: b-roll source picker in NicheWizard`

---

## Task 5: GeneratingScreen — Veo 2 progress awareness

**Objective:** Show the user that Veo 2 takes longer — don't let them think it's stuck.

**File:** `dashboard/src/components/GeneratingScreen.jsx`

**Change:** When phase = `downloading_broll` and job's broll_source = `veo2`, show extended messaging:

```jsx
// In the phase display:
{phase === 'downloading_broll' && brollSource === 'veo2' && (
  <p className="veo2-note">
    🤖 Veo 2 is generating custom clips (~30-90s per scene).<br/>
    Grab a coffee — this will take 3-7 minutes.
  </p>
)}
```

Also extend the polling timeout for the generating screen from 5 min to 15 min when `broll_source === 'veo2'`.

**Commit:** `feat: veo2 progress messaging in GeneratingScreen`

---

## Task 6: CSS

**Objective:** Style the b-roll source picker.

**Additions to `App.css`:**

```css
/* B-roll source picker */
.broll-source-picker   { margin: 16px 0; }
.broll-source-label    { font-size: 11px; font-weight: 700; color: #555;
                          text-transform: uppercase; letter-spacing: .04em;
                          margin-bottom: 8px; }
.broll-option          { display: flex; align-items: center; gap: 10px;
                          background: #111; border: 1px solid #1e1e2e;
                          border-radius: 8px; padding: 10px 14px;
                          cursor: pointer; margin-bottom: 6px;
                          transition: border-color .15s; }
.broll-option.active   { border-color: #6366f1; background: #0e0e1a; }
.broll-option input    { accent-color: #6366f1; }
.broll-option span:first-of-type { font-weight: 700; font-size: 13px; }
.broll-option-desc     { font-size: 11px; color: #555; margin-left: auto; }
.veo2-note             { font-size: 12px; color: #ab7cf5; margin-top: 8px;
                          line-height: 1.6; text-align: center; }
```

**Commit:** `style: b-roll source picker`

---

## Task 7: .env.example + README

**Objective:** Document Gemini API key requirement for Veo 2.

**`.env.example` addition:**
```bash
# ─── AI Video Generation (Veo 2) ─────────────────────────────────────
GEMINI_API_KEY=          # Required for Veo 2 b-roll mode
                         # Get from: aistudio.google.com/app/apikey
```

**`README.md` — new section under Tech Stack:**
```markdown
## B-roll Modes

| Mode | Source | Speed | Cost |
|------|--------|-------|------|
| `pexels` (default) | Pexels stock library | ~10s | Free |
| `veo2` | Google Veo 2 AI generation | ~3-7 min | ~$2.50/video |

### Using Veo 2
1. Get a Gemini API key at aistudio.google.com/app/apikey
2. Add `GEMINI_API_KEY=your_key` to `.env`
3. In the wizard, select **🤖 Veo 2** under B-roll Source
4. Pipeline runs as normal — Veo 2 generates custom clips per scene
```

**Commit:** `docs: Veo 2 setup instructions`

---

## Final Verification

```bash
# All existing tests still pass
python -m pytest tests/ -q

# New Veo 2 tests pass
python -m pytest tests/test_veo_broll.py -v

# Mock mode end-to-end with veo2
MOCK_APIS=true python pipeline.py \
  --topic "compound interest" --niche finance \
  --broll-source veo2 --platform tiktok

# Check mock clips were created
ls data/jobs/*/scene_*_broll.mp4

# Frontend builds clean
npm run build --prefix dashboard
```

---

## Scope Boundaries (Not In This Plan)

| Feature | Reason excluded |
|---------|-----------------|
| Parallel Veo 2 generation | Rate limits unclear — sequential is safe for v1 |
| Hybrid mode (Pexels first → Veo fallback) | Add after v1 validated — more complex |
| Veo 3 (with audio) | Not stable API yet — upgrade path is trivial when ready |
| Veo 2 in topic bank start-video | Default to pexels — add toggle later |
| Storing generated clips in cloud | Out of scope — local storage only |
| Regenerate single scene clip | Phase 2 — swap b-roll in review already works for Pexels |

---

## Risk Register

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Veo 2 API not enabled on key | Medium | Clear error message: "Enable Veo 2 in AI Studio" |
| Generation timeout (>90s per clip) | Low | 180s timeout per clip, skip with warning on failure |
| Clip quality doesn't match prompt | Medium | Enrich prompts with niche style suffix; user can swap in review |
| Cost surprise | Medium | Show cost warning in UI when veo2 selected |
| API quota exhausted | Low | Graceful fallback message — pipeline marks scenes with null broll_path |
| `google-genai` SDK API change | Low | Pin to `google-genai==2.10.0` in requirements.txt |

---

## Change Summary (Minimal Surface Area)

The key design principle: **the pipeline doesn't know or care which b-roll source was used.** Every scene ends up with a `broll_path` pointing to an MP4. The render, captions, review, and publish steps are completely unchanged.

Total new code: ~200 lines across 2 new files.
Total changed code: ~30 lines across 4 existing files.
