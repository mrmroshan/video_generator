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
