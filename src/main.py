"""CLI entry point for the short-video factory pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from openai import OpenAI

from pipeline.capcut_builder import build_capcut_project, copy_to_capcut_folder
from pipeline.downloader import download_reel
from pipeline.heygen_generator import generate_avatar_video
from pipeline.subtitle_postprocess import clamp_srt_to_duration, optimize_srt_file
from pipeline.transcribe import transcribe_to_srt, transcribe_to_text
from pipeline.video_edit import adjust_playback_speed
from utils.config import Settings, load_settings
from utils.cost_estimator import estimate_heygen_credits, get_video_duration
from utils.file_manager import (
    JobPaths,
    copy_source_video,
    create_job_paths,
    update_metadata,
)
from utils.logger import get_logger, setup_logging


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a spiritual short-video workflow from a local file or Instagram URL."
    )
    source_group = parser.add_mutually_exclusive_group(required=False)
    source_group.add_argument("--url", help="Instagram Reels URL to download and process.")
    source_group.add_argument("--input-file", help="Local video file to process.")
    parser.add_argument(
        "source",
        nargs="?",
        help="Instagram Reels URL or local video file path.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args()
    return normalize_source_args(args, parser)


def normalize_source_args(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser | None = None,
) -> argparse.Namespace:
    """Resolve the user's source from either flags or a single positional argument."""
    parser = parser or argparse.ArgumentParser(add_help=False)
    explicit_sources = [value for value in (args.url, args.input_file) if value]
    if args.source and explicit_sources:
        parser.error("Use either a positional source or --url / --input-file, not both.")

    if args.source:
        if looks_like_url(args.source):
            args.url = args.source
        else:
            args.input_file = args.source

    if not args.url and not args.input_file:
        parser.error("Provide an Instagram URL or a local video path.")
    return args


def looks_like_url(value: str) -> bool:
    """Return True when the given string appears to be an HTTP(S) URL."""
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def run() -> int:
    """Execute the configured pipeline."""
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    settings = load_settings(project_root)
    setup_logging(settings.log_level, verbose=args.verbose)
    logger = get_logger(__name__)

    job_paths = create_job_paths(project_root / "outputs")
    metadata = build_initial_metadata(args, job_paths)
    update_metadata(job_paths.metadata_file, metadata)

    try:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured. Please set it in .env before running Phase 1.")
        logger.info("Job started: %s", job_paths.job_id)
        source_video = prepare_source_video(args, job_paths, settings, logger)
        source_duration = get_video_duration(source_video)
        record_step(
            job_paths.metadata_file,
            "source",
            {
                "path": str(source_video),
                "duration_seconds": round(source_duration, 2),
            },
        )

        logger.info("Step 1/4: Transcribing source video...")
        transcribe_to_text(
            client=OpenAI(api_key=settings.openai_api_key),
            video_path=source_video,
            output_path=job_paths.script_file,
            logger=logger,
        )
        script = job_paths.script_file.read_text(encoding="utf-8")
        record_step(
            job_paths.metadata_file,
            "transcription",
            {
                "path": str(job_paths.script_file),
                "characters": len(script),
            },
        )
        logger.info("Step 1/4: Done. (%s: %s chars)", job_paths.script_file.name, len(script))

        if not has_heygen_config(settings):
            logger.warning(
                "HeyGen settings are not configured. Stopping after transcription so Phase 1 can be verified."
            )
            finalize_metadata(job_paths.metadata_file, status="partial", last_completed_phase="phase_1")
            return 0

        estimated_credits = estimate_heygen_credits(source_duration)
        logger.info("予想HeyGen消費: 約%.1fクレジット", estimated_credits)

        logger.info("Step 2/4: Generating HeyGen avatar video...")
        generate_avatar_video(
            api_key=settings.heygen_api_key,
            avatar_id=settings.heygen_avatar_id,
            voice_id=settings.heygen_voice_id,
            script=script,
            output_path=job_paths.avatar_video_raw,
            width=settings.video_width,
            height=settings.video_height,
            scene_fit=settings.heygen_scene_fit,
            use_avatar_iv_model=settings.heygen_use_avatar_iv_model,
            talking_photo_scale=settings.heygen_talking_photo_scale,
            talking_photo_offset_x=settings.heygen_talking_photo_offset_x,
            talking_photo_offset_y=settings.heygen_talking_photo_offset_y,
            logger=logger,
        )
        adjust_playback_speed(
            input_path=job_paths.avatar_video_raw,
            output_path=job_paths.avatar_video,
            speed=settings.avatar_playback_speed,
            logger=logger,
        )
        record_step(
            job_paths.metadata_file,
            "heygen",
            {
                "raw_path": str(job_paths.avatar_video_raw),
                "path": str(job_paths.avatar_video),
                "avatar_id": settings.heygen_avatar_id,
                "scene_fit": settings.heygen_scene_fit,
                "use_avatar_iv_model": settings.heygen_use_avatar_iv_model,
                "talking_photo_scale": settings.heygen_talking_photo_scale,
                "playback_speed": settings.avatar_playback_speed,
                "estimated_credits": round(estimated_credits, 2),
            },
        )
        logger.info("Step 2/4: Done. (%s)", job_paths.avatar_video.name)

        logger.info("Step 3/4: Generating SRT subtitle...")
        transcribe_to_srt(
            client=OpenAI(api_key=settings.openai_api_key),
            video_path=job_paths.avatar_video,
            output_path=job_paths.subtitle_file,
            logger=logger,
        )
        optimize_srt_file(
            input_path=job_paths.subtitle_file,
            logger=logger,
        )
        clamp_srt_to_duration(
            input_path=job_paths.subtitle_file,
            max_duration_ms=round(get_video_duration(job_paths.avatar_video) * 1000),
            logger=logger,
        )
        record_step(
            job_paths.metadata_file,
            "subtitle",
            {"path": str(job_paths.subtitle_file)},
        )
        logger.info("Step 3/4: Done. (%s)", job_paths.subtitle_file.name)

        if settings.capcut_draft_folder is None:
            logger.warning(
                "CAPCUT_DRAFT_FOLDER is not configured. Stopping after subtitle generation so Phase 3 can be verified."
            )
            finalize_metadata(job_paths.metadata_file, status="partial", last_completed_phase="phase_3")
            return 0

        logger.info("Step 4/4: Building CapCut project...")
        build_capcut_project(
            base_url=settings.capcut_api_url,
            video_path=job_paths.avatar_video,
            srt_path=job_paths.subtitle_file,
            output_dir=job_paths.capcut_project_dir,
            subtitle_style=settings.subtitle_style,
            api_workdir=settings.capcut_api_workdir,
            width=settings.video_width,
            height=settings.video_height,
            logger=logger,
        )
        copied_paths = copy_to_capcut_folder(
            draft_folder=job_paths.capcut_project_dir,
            capcut_folder=settings.capcut_draft_folder,
            logger=logger,
        )
        record_step(
            job_paths.metadata_file,
            "capcut",
            {
                "project_dir": str(job_paths.capcut_project_dir),
                "copied_drafts": [str(path) for path in copied_paths],
            },
        )
        finalize_metadata(job_paths.metadata_file, status="completed", last_completed_phase="phase_7")
        logger.info("Step 4/4: Done. Open CapCut to see the new project.")
        logger.info("ジョブ情報: %s", job_paths.metadata_file)
        return 0
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        finalize_metadata(
            job_paths.metadata_file,
            status="failed",
            error=str(exc),
        )
        return 1


def build_initial_metadata(args: argparse.Namespace, job_paths: JobPaths) -> dict[str, Any]:
    """Create initial metadata structure for a new job."""
    input_mode = "url" if args.url else "input_file"
    input_value = args.url or args.input_file
    return {
        "job_id": job_paths.job_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "started",
        "input": {
            "mode": input_mode,
            "value": input_value,
        },
        "steps": {},
    }


def record_step(metadata_path: Path, name: str, payload: dict[str, Any]) -> None:
    """Store per-step metadata without overwriting other steps."""
    update_metadata(metadata_path, {"steps": {name: payload}})


def finalize_metadata(
    metadata_path: Path,
    status: str,
    last_completed_phase: str | None = None,
    error: str | None = None,
) -> None:
    """Mark the job as finished."""
    payload: dict[str, Any] = {
        "status": status,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if last_completed_phase is not None:
        payload["last_completed_phase"] = last_completed_phase
    if error is not None:
        payload["error"] = error
    update_metadata(metadata_path, payload)


def prepare_source_video(
    args: argparse.Namespace,
    job_paths: JobPaths,
    settings: Settings,
    logger: logging.Logger,
) -> Path:
    """Prepare the input video in the job output directory."""
    if args.input_file:
        logger.info("Step 0/4: Copying local input file...")
        source_path = copy_source_video(Path(args.input_file), job_paths.source_video)
        logger.info("Step 0/4: Done. (%s)", source_path.name)
        return source_path

    logger.info("Step 0/4: Downloading from Instagram...")
    source_path = download_reel(
        url=args.url,
        output_dir=job_paths.job_dir,
        cookie_file=settings.instagram_cookie_file,
        logger=logger,
    )
    logger.info("Step 0/4: Done. (%s)", source_path.name)
    return source_path


def has_heygen_config(settings: Settings) -> bool:
    """Return True when the minimum HeyGen configuration is present."""
    return bool(settings.heygen_api_key and settings.heygen_avatar_id)


if __name__ == "__main__":
    sys.exit(run())
