# YouTube Publish Integration Plan

> **Status:** PLANNED — not built yet. Approved by Roshan 2026-09-15.
> **To build:** Say "build the YouTube publish module" and I'll execute task by task.

**Goal:** Upload rendered MP4s to YouTube directly from the review dashboard, with optional scheduling via YouTube's own built-in scheduler. No cron job on our side — we upload immediately and let YouTube handle the publish time.

**Approach:** OAuth 2.0 (Web App flow), YouTube Data API v3 resumable upload, privacy=private + publishAt for scheduled posts. All publish copy (title, description, tags) pulled from what Claude already generated — zero extra input needed.

**Key constraint:** User uploads immediately. YouTube holds the video as private and publishes at the chosen time. If "Publish Now" is chosen, privacy=public on upload.

---

## Prerequisites (User Must Do — One Time)

1. Go to https://console.cloud.google.com
2. Create a new project (e.g. "Video Maker")
3. Enable **YouTube Data API v3** (APIs & Services → Library)
4. Create OAuth 2.0 credentials:
   - Credentials → + Create Credentials → OAuth 2.0 Client ID
   - Application type: **Web application**
   - Authorised redirect URI: `http://localhost:8001/publish/youtube/callback`
   - Download or copy **Client ID** and **Client Secret**
5. Add to `.env`:
   ```
   YOUTUBE_CLIENT_ID=your_client_id
   YOUTUBE_CLIENT_SECRET=your_client_secret
   YOUTUBE_REDIRECT_URI=http://localhost:8001/publish/youtube/callback
   ```
6. In Google Cloud Console → OAuth consent screen:
   - User type: External
   - Add your own Gmail as a test user
   - Scopes: `youtube.upload`

> Note: App stays in "Testing" mode — no Google review needed for personal use (up to 100 test users).

---

## Architecture

```
User clicks "Connect YouTube"
  → GET /publish/youtube/auth-url
  → Opens Google OAuth in new browser tab
  → User approves
  → Google redirects to http://localhost:8001/publish/youtube/callback?code=xxx
  → Server exchanges code for access + refresh token
  → Tokens saved to data/credentials/youtube_token.json (gitignored)

User clicks "Upload to YouTube" on a done job
  → POST /jobs/{id}/publish/youtube  { schedule_at: "2026-09-20T09:00:00" | null }
  → Server reads output.mp4
  → Starts resumable upload to YouTube
  → Sets title/description/tags from job.publish_copy
  → privacy = "private" + publishAt if scheduled, "public" if now
  → YouTube returns video_id
  → Stored in DB publish_log table
  → Review screen shows: ✅ youtu.be/VIDEO_ID · publishes Sep 20 9:00 AM
```

---

## Files to Create / Modify

| File | Action | What |
|------|--------|------|
| `distribution/publishers/youtube.py` | **CREATE** | OAuth flow + resumable upload |
| `data/db.py` | **MODIFY** | Add `publish_log` table |
| `dashboard/server.py` | **MODIFY** | 5 new endpoints |
| `dashboard/src/components/YouTubePublish.jsx` | **CREATE** | Connect + schedule UI |
| `dashboard/src/components/JobReview.jsx` | **MODIFY** | Add YouTubePublish panel |
| `dashboard/src/App.css` | **MODIFY** | YouTube panel styles |
| `requirements.txt` | **MODIFY** | Add google-auth + google-api-python-client |
| `.env.example` | **MODIFY** | Add YouTube cred keys |
| `.gitignore` | **MODIFY** | Ignore data/credentials/ |
| `tests/test_youtube_publish.py` | **CREATE** | Unit tests with mocked API |

---

## Task 1: Dependencies + Gitignore

**Objective:** Install Google API packages, protect credentials directory.

**Files:**
- Modify: `requirements.txt`
- Modify: `.gitignore`
- Create: `data/credentials/.gitkeep`

**requirements.txt additions:**
```
google-auth>=2.0.0
google-auth-oauthlib>=1.0.0
google-api-python-client>=2.0.0
```

**`.gitignore` addition:**
```
# YouTube / platform credentials
data/credentials/
```

**Verify:** `pip install -r requirements.txt` exits 0.

**Commit:** `chore: add Google API deps + protect credentials dir`

---

## Task 2: DB — publish_log table

**Objective:** Store a record every time a video is uploaded to any platform.

**File:** `data/db.py`

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS publish_log (
    log_id       TEXT PRIMARY KEY,
    job_id       TEXT NOT NULL REFERENCES jobs(job_id),
    platform     TEXT NOT NULL,             -- 'youtube'
    status       TEXT NOT NULL DEFAULT 'uploading',
                                            -- uploading|scheduled|published|failed
    video_id     TEXT,                      -- platform's video ID
    video_url    TEXT,                      -- full watch URL
    scheduled_at TEXT,                      -- ISO8601, null = published immediately
    published_at TEXT,                      -- when it actually went live
    error        TEXT,                      -- error message if failed
    created_at   TEXT NOT NULL
)
```

**New functions:**
```python
def log_publish(job_id, platform, status, video_id=None,
                video_url=None, scheduled_at=None) -> dict
def update_publish_log(log_id, status, video_id=None,
                       video_url=None, error=None) -> dict
def list_publish_log(job_id) -> list
def get_publish_log(log_id) -> dict | None
```

**Tests (`tests/test_youtube_publish.py`):**
```python
def test_log_publish_creates_record(tmp_db)
def test_update_publish_log_status(tmp_db)
def test_list_publish_log_by_job(tmp_db)
```

**Commit:** `feat: publish_log table + DB helpers`

---

## Task 3: YouTube OAuth + Upload Module

**Objective:** Full YouTube integration — OAuth flow + resumable upload.

**File:** `distribution/publishers/youtube.py`

**Key functions:**

```python
def get_auth_url() -> str:
    """Return Google OAuth2 URL. User opens this in browser."""

def exchange_code(code: str) -> dict:
    """Exchange auth code for tokens. Save to data/credentials/youtube_token.json."""

def is_connected() -> bool:
    """Return True if valid token exists and is not expired."""

def get_channel_info() -> dict | None:
    """Return {channel_id, title, thumbnail} or None if not connected."""

def disconnect():
    """Delete stored token file."""

def upload_video(job: dict, schedule_at: str | None = None) -> dict:
    """
    Upload job's output.mp4 to YouTube.
    
    - title          = job.publish_copy.youtube_title (fallback: job.title)
    - description    = job.publish_copy.youtube_description (fallback: job.description)
    - tags           = job.hashtags (stripped of #)
    - category_id    = "22" (People & Blogs)
    - privacy_status = "public" if schedule_at is None else "private"
    - publish_at     = schedule_at (ISO8601, YouTube format) if scheduling
    
    Returns:
    {
        "video_id":    "abc123",
        "video_url":   "https://youtu.be/abc123",
        "status":      "scheduled" | "published",
        "scheduled_at": "2026-09-20T09:00:00+03:00" | None
    }
    """
```

**Implementation notes:**
- Use `google-auth-oauthlib` for OAuth flow
- Token file: `data/credentials/youtube_token.json`
- Auto-refresh token on expiry using refresh_token
- Use resumable upload for files > 5MB (all our renders will be)
- YouTube `publishAt` must be in RFC 3339 format with timezone
- `publishAt` only works with `privacyStatus: "private"` — YouTube publishes and changes to public at the scheduled time

**MOCK_APIS support:**
```python
if os.getenv("MOCK_APIS", "true").lower() == "true":
    return {
        "video_id":    "MOCK_VIDEO_ID",
        "video_url":   "https://youtu.be/MOCK_VIDEO_ID",
        "status":      "scheduled" if schedule_at else "published",
        "scheduled_at": schedule_at,
    }
```

**Tests:**
```python
def test_upload_mock_returns_video_id(monkeypatch)
def test_upload_uses_publish_copy_title(monkeypatch)
def test_upload_uses_publish_copy_description(monkeypatch)
def test_schedule_sets_privacy_private(monkeypatch)
def test_publish_now_sets_privacy_public(monkeypatch)
def test_tags_strip_hash_symbols(monkeypatch)
def test_disconnect_removes_token_file(tmp_path, monkeypatch)
def test_is_connected_false_when_no_token(tmp_path, monkeypatch)
```

**Commit:** `feat: youtube.py — OAuth flow + resumable upload`

---

## Task 4: API Endpoints

**Objective:** 5 new endpoints in `dashboard/server.py`.

**Endpoints:**

```python
GET  /publish/youtube/status
# Returns:
# { "connected": bool, "channel": { "title": str, "thumbnail": str } | null }

GET  /publish/youtube/auth-url
# Returns:
# { "auth_url": "https://accounts.google.com/o/oauth2/auth?..." }

GET  /publish/youtube/callback?code=xxx&state=yyy
# Exchanges code, saves token, redirects to:
# http://localhost:5173/?youtube_connected=true
# (frontend detects query param and shows success toast)

DELETE /publish/youtube/disconnect
# Removes token file. Returns { "disconnected": true }

POST /jobs/{job_id}/publish/youtube
# Body: { "schedule_at": "2026-09-20T09:00:00+03:00" }  (null = publish now)
# Guards:
#   - job.status must be "done" (has rendered output)
#   - output.mp4 must exist on disk
#   - YouTube must be connected
# Runs upload in background task
# Returns: { "log_id": "...", "status": "uploading", "message": "..." }

GET /jobs/{job_id}/publish/youtube/status
# Returns latest publish_log entry for this job
# { "status": "scheduled|published|failed", "video_url": "...", "scheduled_at": "..." }
```

**Tests:**
```python
def test_youtube_status_disconnected(client)
def test_youtube_auth_url_returns_google_url(client)
def test_publish_youtube_requires_done_status(client)
def test_publish_youtube_requires_output_file(client)
def test_publish_youtube_mock_success(client, monkeypatch)
def test_publish_youtube_stores_log(client, monkeypatch)
```

**Commit:** `feat: YouTube publish API endpoints`

---

## Task 5: Frontend — YouTubePublish Component

**Objective:** UI panel in JobReview showing connect state + schedule picker.

**File:** `dashboard/src/components/YouTubePublish.jsx`

**States the panel has:**

**State A — Not connected:**
```
┌─────────────────────────────────────────────────┐
│ ▶️ Publish to YouTube                           │
│                                                  │
│  Connect your YouTube channel to publish         │
│  directly from here.                             │
│                                                  │
│  [ Connect YouTube ]                             │
└─────────────────────────────────────────────────┘
```

**State B — Connected, not yet published:**
```
┌─────────────────────────────────────────────────┐
│ ▶️ YouTube  ✓ Connected as "Roshan's Channel"   │
│                                                  │
│  Title:   5 AI Tools That Turn a 40-Hour...     │
│  Tags:    #AItools #productivity...              │
│                                                  │
│  ○ Publish Now                                   │
│  ● Schedule   📅 [date picker]  🕐 [time]       │
│                                                  │
│  [ Upload to YouTube ]   [ Disconnect ]          │
└─────────────────────────────────────────────────┘
```

**State C — Uploading:**
```
│  ⏳ Uploading… (this may take a minute)         │
```

**State D — Done:**
```
│  ✅ Uploaded · youtu.be/abc123                  │
│  Scheduled: Monday Sep 20, 9:00 AM              │
│  [ Open on YouTube ↗ ]                          │
```

**State E — Failed:**
```
│  ❌ Upload failed: [error message]               │
│  [ Try Again ]                                   │
```

**Key behaviour:**
- "Connect YouTube" → fetch `/publish/youtube/auth-url` → open URL in new tab (`window.open`)
- On return, page detects `?youtube_connected=true` query param → re-fetches status → shows connected state
- Date picker defaults to tomorrow 9:00 AM user's local time
- Time zone: user's local timezone (use `Intl.DateTimeFormat().resolvedOptions().timeZone`)
- After upload starts, poll `/jobs/{id}/publish/youtube/status` every 3s until status ≠ uploading

**Wire into JobReview.jsx:**
```jsx
{/* ── YouTube Publish ───────────────────────────────────── */}
{rendered && <YouTubePublish job={job} />}
```
Only shown when job is fully rendered (status=done, output exists).

**Commit:** `feat: YouTubePublish.jsx — connect + schedule UI`

---

## Task 6: CSS

**Objective:** Style the YouTube panel consistently with the rest of the dashboard.

**Additions to `App.css`:**

```css
/* YouTube publish panel */
.yt-publish-panel { ... }
.yt-connect-btn   { background: #FF0000; color: #fff; ... }
.yt-upload-btn    { background: #1a1a2e; border: 1px solid #6366f1; ... }
.yt-schedule-row  { display: flex; gap: 8px; align-items: center; ... }
.yt-done-badge    { color: #4caf6e; ... }
.yt-failed-badge  { color: #f08080; ... }
.yt-channel-badge { font-size: 11px; color: #4caf6e; ... }
```

**Commit:** `style: YouTube publish panel`

---

## Task 7: .env.example + README update

**Objective:** Document credentials setup for new installs.

**`.env.example` additions:**
```bash
# ─── YouTube Publishing ───────────────────────────────────────────────
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REDIRECT_URI=http://localhost:8001/publish/youtube/callback
```

**`README.md` — new section:**
```markdown
## Publishing to YouTube

### One-time setup
1. Create a Google Cloud project at console.cloud.google.com
2. Enable YouTube Data API v3
3. Create OAuth 2.0 credentials (Web application)
4. Add redirect URI: http://localhost:8001/publish/youtube/callback
5. Copy Client ID + Secret into .env

### Publishing a video
1. Render the video (Approve & Lock → Render MP4)
2. In the review screen, scroll to "Publish to YouTube"
3. Click "Connect YouTube" (first time only)
4. Choose "Publish Now" or pick a schedule date/time
5. Click "Upload to YouTube"
6. Done — YouTube handles publishing at the scheduled time
```

**Commit:** `docs: YouTube publish setup instructions`

---

## Final Verify

```bash
python -m pytest tests/ -q              # all tests pass
npm run build --prefix dashboard        # frontend builds clean
curl http://localhost:8001/publish/youtube/status  # {"connected": false}
```

---

## Scope Boundaries (Not In This Plan)

| Feature | Reason not included |
|---------|---------------------|
| Edit video after upload | YouTube API doesn't support replacing video files |
| Analytics / view counts | Separate feature, needs YouTube Analytics API |
| Playlist management | Out of scope for v1 |
| TikTok / Instagram | Separate plan — harder API approval |
| Auto-publish from topic bank | Phase 2 — do manual first, automate after validated |
| Thumbnail upload | Future feature — needs image generation pipeline |

---

## Risk Register

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Google OAuth consent screen rejected | Low | Stay in Testing mode (100 users) — no review needed for personal use |
| Token expires mid-upload | Low | google-auth auto-refreshes using refresh_token |
| Upload fails on large file | Medium | Resumable upload retries automatically |
| YouTube quota exceeded | Low | Default quota = 10,000 units/day; 1 upload = ~1,600 units → ~6 uploads/day free |
| publishAt timezone mismatch | Medium | Always send RFC3339 with explicit timezone offset |
