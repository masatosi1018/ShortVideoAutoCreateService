"""Video post-processing helpers."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path


def adjust_playback_speed(
    input_path: Path,
    output_path: Path,
    speed: float,
    logger: logging.Logger | None = None,
) -> Path:
    """Create a playback-speed-adjusted MP4 while keeping audio in sync."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input video not found: {input_path}")
    if speed <= 0:
        raise ValueError("Playback speed must be greater than 0.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if abs(speed - 1.0) < 1e-6:
        shutil.copy2(input_path, output_path)
        return output_path

    ffmpeg_path = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
    if not Path(ffmpeg_path).exists():
        raise FileNotFoundError("ffmpeg is required to adjust playback speed.")

    if logger is not None:
        logger.info("Adjusting avatar playback speed to %.2fx", speed)

    subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-i",
            str(input_path),
            "-filter:v",
            f"setpts=PTS/{speed}",
            "-filter:a",
            _build_atempo_filter(speed),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def _build_atempo_filter(speed: float) -> str:
    """Build an ffmpeg atempo chain for arbitrary positive speeds."""
    remaining = speed
    filters: list[str] = []
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.6f}")
    return ",".join(filters)
