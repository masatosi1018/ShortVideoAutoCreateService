"""Helpers for job directories and metadata files."""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class JobPaths:
    """Concrete file paths for a single pipeline job."""

    job_id: str
    job_dir: Path
    source_video: Path
    script_file: Path
    avatar_video_raw: Path
    avatar_video: Path
    subtitle_file: Path
    capcut_project_dir: Path
    metadata_file: Path


def create_job_paths(outputs_dir: Path) -> JobPaths:
    """Create and return the standard output paths for a new job."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    job_id = uuid.uuid4().hex[:6]
    job_dir = outputs_dir / f"{timestamp}_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=False)

    return JobPaths(
        job_id=job_id,
        job_dir=job_dir,
        source_video=job_dir / "source_video.mp4",
        script_file=job_dir / "script.txt",
        avatar_video_raw=job_dir / "avatar_video_raw.mp4",
        avatar_video=job_dir / "avatar_video.mp4",
        subtitle_file=job_dir / "subtitle.srt",
        capcut_project_dir=job_dir / "capcut_project",
        metadata_file=job_dir / "metadata.json",
    )


def copy_source_video(input_path: Path, destination: Path) -> Path:
    """Copy a local source video into the job directory."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, destination)
    return destination


def update_metadata(metadata_path: Path, payload: dict[str, Any]) -> Path:
    """Merge metadata payloads into a single JSON file."""
    existing = {}
    if metadata_path.exists():
        existing = json.loads(metadata_path.read_text(encoding="utf-8"))
    merged = _deep_merge(existing, payload)
    metadata_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata_path


def _deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge dictionaries without mutating the inputs."""
    merged = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
