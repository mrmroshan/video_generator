"""
Phase 4: Renderer selector — Remotion (primary) or FFmpeg (fallback)
Decision is driven by job config, not hardcoded.
"""
import os
import subprocess

from pathlib import Path

_ROOT = Path(__file__).parent.parent
JOBS_DIR = os.getenv("JOBS_DIR", str(_ROOT / "data" / "jobs"))
MOCK_APIS = os.getenv("MOCK_APIS", "true").lower() == "true"


def render_job(job: dict) -> str:
    """
    Render the approved job into a final MP4.
    Returns path to output file.
    Raises if job is not in 'approved' state.
    """
    if job["status"] != "approved":
        raise ValueError(f"Job {job['job_id']} is not approved (status={job['status']}). Cannot render.")

    renderer = job.get("renderer", "remotion")
    job_dir = f"{JOBS_DIR}/{job['job_id']}"
    output_path = f"{job_dir}/output.mp4"

    if not MOCK_APIS:
        if renderer == "remotion":
            return _render_remotion(job, output_path)
        elif renderer == "ffmpeg":
            return _render_ffmpeg(job, output_path)
        else:
            raise ValueError(f"Unknown renderer: {renderer}")

    with open(output_path, "wb") as f:
        f.write(b"MOCK_OUTPUT_MP4")
    print(f"[MOCK] Rendered ({renderer}) → {output_path}")
    return output_path


def _render_remotion(job: dict, output_path: str) -> str:
    """Render via Remotion (npx remotion render ...)"""
    # TODO: pass job JSON to Remotion composition
    # npx remotion render src/index.tsx VideoComposition output.mp4 --props='...'
    raise NotImplementedError("Remotion renderer not yet wired")


def _render_ffmpeg(job: dict, output_path: str) -> str:
    """Render via FFmpeg — simple concatenation + audio"""
    # TODO: build ffmpeg filter_complex from scene broll_paths + audio_paths
    raise NotImplementedError("FFmpeg renderer not yet wired")
