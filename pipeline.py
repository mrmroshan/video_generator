"""
PIPELINE RUNNER — orchestrates all phases end to end
Run: python pipeline.py --topic "solar energy" --niche finance --platform tiktok
"""
import argparse
import json
import sys
import os

# Ensure we can import sibling packages
sys.path.insert(0, os.path.dirname(__file__))

from orchestration.crew import generate_script
from audio.tts import generate_audio_for_job
from audio.timestamps import extract_timestamps
from assets.broll import fetch_broll_for_job
from data.db import init_db, save_job, update_status, load_job
from renderer.render import render_job, VALID_PLATFORMS  # single source of truth
from distribution.publishers.distribute import distribute


def run_pipeline(topic: str, platform: str, niche: str = "finance",
                 broll_source: str = "pexels"):
    print(f"\n🎬 Starting VIDEO MAKER pipeline")
    print(f"   Topic: {topic} | Niche: {niche} | Platform: {platform} | B-roll: {broll_source}\n")

    init_db()
    job = {}

    try:
        # Phase 1 — Script (niche-aware: injects audience/tone/hooks)
        print("── Phase 1: Generating script...")
        job = generate_script(topic, platform, niche=niche)
        job["niche"] = niche
        job["broll_source"] = broll_source
        save_job(job)
        print(f"   Job ID: {job['job_id']} ✓")

        # Phase 2 — Assets
        print("\n── Phase 2: Generating assets...")
        update_status(job["job_id"], "generating_assets")
        job = generate_audio_for_job(job)
        for scene in job["scenes"]:
            extract_timestamps(scene)
        job = fetch_broll_for_job(job)
        # save_job AFTER assets so audio_path / broll_path are persisted
        job["status"] = "in_review"
        save_job(job)
        print("   Assets ready ✓")

        # Phase 3 — Human Review (placeholder — dashboard handles this)
        print("\n── Phase 3: Human review required")
        print(f"   Open the dashboard and approve job: {job['job_id']}")
        print("   (In MOCK mode, auto-approving...)")

        if os.getenv("MOCK_APIS", "true").lower() == "true":
            from datetime import datetime, timezone
            update_status(job["job_id"], "approved", {"approved_at": datetime.now(timezone.utc).isoformat()})
            job = load_job(job["job_id"])

        # Phase 4 — Render
        if job["status"] == "approved":
            print("\n── Phase 4: Rendering...")
            update_status(job["job_id"], "rendering")
            output_path = render_job(job)
            update_status(job["job_id"], "distributing", {"output_path": output_path})
            job = load_job(job["job_id"])
            print(f"   Rendered → {output_path} ✓")

            # Phase 5 — Distribute
            print("\n── Phase 5: Distributing...")
            success = distribute(job)
            if success:
                update_status(job["job_id"], "done")
                print("   Done ✓")
        else:
            print(f"   Skipping render — job not approved (status={job['status']})")

        print(f"\n✅ Pipeline complete. Job: {job['job_id']}\n")
        return job

    except Exception as e:
        job_id = job.get("job_id", "?")
        print(f"\n[ERROR] Pipeline failed for job {job_id}: {e}")
        if job_id != "?":
            try:
                update_status(job_id, "failed")
                print(f"   Job {job_id} marked as failed.")
            except Exception:
                pass
        raise


if __name__ == "__main__":
    VALID_NICHES = ["finance", "entrepreneurship", "health", "tech", "mindset",
                    "productivity", "ai", "marketing", "relationships", "fitness"]
    # VALID_PLATFORMS imported from renderer.render — no local copy needed

    parser = argparse.ArgumentParser(description="VIDEO MAKER pipeline")
    parser.add_argument("--topic",    required=True, help="Video topic")
    parser.add_argument("--niche",    choices=VALID_NICHES,            default="finance",
                        help="Content niche (drives audience/tone/hooks)")
    parser.add_argument("--platform", choices=sorted(VALID_PLATFORMS), default="tiktok",
                        help="Primary platform for script style")
    parser.add_argument("--broll-source", choices=["pexels", "veo2"], default="pexels",
                        help="B-roll source: pexels (free, fast) or veo2 (AI-generated, slower)")
    args = parser.parse_args()
    run_pipeline(args.topic, args.platform, niche=args.niche, broll_source=args.broll_source)
