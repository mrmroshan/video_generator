"""
Phase 5: Distribution — n8n webhook trigger + YouTube/TikTok upload
"""
import os
import json
import urllib.request
import urllib.parse

MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")


def distribute(job: dict) -> bool:
    """
    Trigger distribution for a rendered job.
    Returns True on success.
    """
    if job["status"] not in {"rendering", "distributing"} and not MOCK_APIS:
        raise ValueError(f"Job must be in 'rendering' or 'distributing' state (got: {job['status']})")

    output_path = job.get("output_path")
    if not output_path and not MOCK_APIS:
        raise ValueError("No output_path set on job — render first")

    if MOCK_APIS:
        print(f"[MOCK] Would upload to {job['platform']}: {job['title']}")
        print(f"[MOCK] Would fire n8n webhook: {N8N_WEBHOOK_URL or 'N8N_WEBHOOK_URL not set'}")
        return True

    raise NotImplementedError(
        "Real distribution not yet implemented. Set MOCK_APIS=true or implement upload handlers."
    )


def _fire_n8n_webhook(job: dict):
    if not N8N_WEBHOOK_URL:
        print("[WARN] N8N_WEBHOOK_URL not set — skipping webhook")
        return
    payload = json.dumps({"job_id": job["job_id"], "platform": job["platform"]}).encode()
    req = urllib.request.Request(N8N_WEBHOOK_URL, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        print("n8n webhook fired ✓")
    except Exception as e:
        print(f"[WARN] n8n webhook failed (non-fatal): {e}")


def _upload_youtube(job: dict) -> bool:
    """YouTube Data API v3 upload — TODO: implement OAuth + resumable upload"""
    raise NotImplementedError("YouTube upload not yet wired")


def _upload_tiktok(job: dict) -> bool:
    """TikTok Direct API upload — TODO: implement OAuth2 + video upload"""
    raise NotImplementedError("TikTok upload not yet wired")
