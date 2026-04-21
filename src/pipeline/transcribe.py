"""Whisper transcription helpers."""

from __future__ import annotations

import contextlib
import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Iterator

from openai import OpenAI

OPENAI_AUDIO_UPLOAD_LIMIT_BYTES = 25 * 1024 * 1024


def transcribe_to_text(
    client: OpenAI,
    video_path: Path,
    output_path: Path,
    language: str = "ja",
    retries: int = 3,
    logger: logging.Logger | None = None,
) -> Path:
    """Transcribe a media file into plain text and save it."""
    text = _transcribe(
        client=client,
        video_path=video_path,
        response_format="text",
        language=language,
        retries=retries,
        logger=logger,
    )
    output_path.write_text(text, encoding="utf-8")
    return output_path


def transcribe_to_srt(
    client: OpenAI,
    video_path: Path,
    output_path: Path,
    language: str = "ja",
    retries: int = 3,
    logger: logging.Logger | None = None,
) -> Path:
    """Transcribe a media file into SRT format and save it."""
    srt = _transcribe(
        client=client,
        video_path=video_path,
        response_format="srt",
        language=language,
        retries=retries,
        logger=logger,
    )
    output_path.write_text(srt, encoding="utf-8")
    return output_path


def _transcribe(
    client: OpenAI,
    video_path: Path,
    response_format: str,
    language: str,
    retries: int,
    logger: logging.Logger | None,
) -> str:
    """Submit a Whisper transcription request with basic retries."""
    if not video_path.exists():
        raise FileNotFoundError(f"Input media file not found: {video_path}")

    attempt = 0
    while True:
        attempt += 1
        try:
            with _prepare_transcription_input(video_path, logger) as transcription_input:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=(transcription_input.name, transcription_input.read_bytes()),
                    language=language,
                    response_format=response_format,
                )
            return _coerce_transcription_response(response)
        except Exception:
            if attempt >= retries:
                raise
            if logger is not None:
                logger.warning(
                    "Whisper request failed for %s (attempt %s/%s). Retrying...",
                    video_path.name,
                    attempt,
                    retries,
                )
            time.sleep(attempt)


@contextlib.contextmanager
def _prepare_transcription_input(
    media_path: Path,
    logger: logging.Logger | None,
) -> Iterator[Path]:
    """Yield an input file small enough for OpenAI audio upload limits."""
    if media_path.stat().st_size <= OPENAI_AUDIO_UPLOAD_LIMIT_BYTES:
        yield media_path
        return

    ffmpeg_path = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
    if not Path(ffmpeg_path).exists():
        raise FileNotFoundError(
            "ffmpeg is required to compress media files larger than 25MB before transcription."
        )

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        if logger is not None:
            logger.info(
                "Input media exceeds 25MB; extracting lightweight audio for transcription: %s",
                media_path.name,
            )
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                str(media_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                "64k",
                str(temp_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        yield temp_path
    finally:
        temp_path.unlink(missing_ok=True)


def _coerce_transcription_response(response: object) -> str:
    """Normalize OpenAI SDK response objects into a plain string."""
    if isinstance(response, str):
        return response
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    return str(response)
