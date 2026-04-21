"""Configuration loading helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
import os


@dataclass
class Settings:
    """Application settings aggregated from `.env` and YAML."""

    openai_api_key: str | None
    heygen_api_key: str | None
    heygen_avatar_id: str | None
    heygen_voice_id: str | None
    heygen_scene_fit: str | None
    heygen_use_avatar_iv_model: bool
    heygen_talking_photo_scale: float | None
    heygen_talking_photo_offset_x: float | None
    heygen_talking_photo_offset_y: float | None
    avatar_playback_speed: float
    capcut_api_workdir: Path
    capcut_draft_folder: Path | None
    capcut_api_url: str
    instagram_cookie_file: Path
    log_level: str
    video_width: int
    video_height: int
    subtitle_style: dict[str, Any]


def load_settings(project_root: Path | None = None) -> Settings:
    """Load configuration from `.env` and `config/settings.yaml`."""
    root = project_root or Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env", override=False)

    settings_path = root / "config" / "settings.yaml"
    if not settings_path.exists():
        raise FileNotFoundError(f"settings.yaml not found: {settings_path}")

    with settings_path.open("r", encoding="utf-8") as file_handle:
        yaml_config = yaml.safe_load(file_handle) or {}

    video_config = yaml_config.get("video", {})
    subtitle_style = yaml_config.get("subtitle_style", {})

    capcut_draft_folder = _optional_path(os.getenv("CAPCUT_DRAFT_FOLDER"))
    capcut_api_workdir = _optional_path(os.getenv("CAPCUT_API_WORKDIR")) or (root / "external" / "CapCutAPI")
    instagram_cookie_value = os.getenv("INSTAGRAM_COOKIE_FILE", "./config/instagram_cookies.txt")
    instagram_cookie_path = Path(instagram_cookie_value).expanduser()
    if not instagram_cookie_path.is_absolute():
        instagram_cookie_path = (root / instagram_cookie_path).resolve()
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        heygen_api_key=os.getenv("HEYGEN_API_KEY"),
        heygen_avatar_id=os.getenv("HEYGEN_AVATAR_ID"),
        heygen_voice_id=os.getenv("HEYGEN_VOICE_ID") or None,
        heygen_scene_fit=os.getenv("HEYGEN_SCENE_FIT") or None,
        heygen_use_avatar_iv_model=_optional_bool(os.getenv("HEYGEN_USE_AVATAR_IV_MODEL"), default=False),
        heygen_talking_photo_scale=_optional_float(os.getenv("HEYGEN_TALKING_PHOTO_SCALE")),
        heygen_talking_photo_offset_x=_optional_float(os.getenv("HEYGEN_TALKING_PHOTO_OFFSET_X")),
        heygen_talking_photo_offset_y=_optional_float(os.getenv("HEYGEN_TALKING_PHOTO_OFFSET_Y")),
        avatar_playback_speed=float(os.getenv("AVATAR_PLAYBACK_SPEED", "1.25")),
        capcut_api_workdir=capcut_api_workdir,
        capcut_draft_folder=capcut_draft_folder,
        capcut_api_url=os.getenv("CAPCUT_API_URL", "http://localhost:9001"),
        instagram_cookie_file=instagram_cookie_path,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        video_width=int(video_config.get("width", 1080)),
        video_height=int(video_config.get("height", 1920)),
        subtitle_style=subtitle_style,
    )


def _optional_path(raw_value: str | None) -> Path | None:
    """Convert an optional path string into a resolved `Path`."""
    if not raw_value:
        return None
    return Path(raw_value).expanduser().resolve()


def _optional_bool(raw_value: str | None, default: bool) -> bool:
    """Parse common truthy strings from environment variables."""
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_float(raw_value: str | None) -> float | None:
    """Parse optional float values from environment variables."""
    if raw_value is None or not raw_value.strip():
        return None
    return float(raw_value)
