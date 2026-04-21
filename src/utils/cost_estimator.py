"""Helpers for duration inspection and credit estimation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def get_video_duration(video_path: Path) -> float:
    """Return video duration in seconds using ffprobe."""
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe is required but was not found. Please install ffmpeg.")

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def estimate_heygen_credits(duration_seconds: float) -> float:
    """Estimate HeyGen credits from video duration."""
    return duration_seconds / 10.0

