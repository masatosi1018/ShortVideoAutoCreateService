"""HeyGen avatar video generation helpers."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests


def generate_avatar_video(
    api_key: str | None,
    avatar_id: str | None,
    voice_id: str | None,
    script: str,
    output_path: Path,
    width: int = 1080,
    height: int = 1920,
    scene_fit: str | None = None,
    use_avatar_iv_model: bool = False,
    talking_photo_scale: float | None = None,
    talking_photo_offset_x: float | None = None,
    talking_photo_offset_y: float | None = None,
    timeout: int = 600,
    poll_interval: int = 3,
    logger: logging.Logger | None = None,
) -> Path:
    """Generate a HeyGen avatar video and download it to disk."""
    if not api_key:
        raise ValueError("HEYGEN_API_KEY is not configured.")
    if not avatar_id:
        raise ValueError("HEYGEN_AVATAR_ID is not configured.")
    if not script.strip():
        raise ValueError("Script text is empty. Cannot request HeyGen video generation.")

    character, resolved_voice_id = _build_character_payload(
        api_key=api_key,
        avatar_id=avatar_id,
        voice_id=voice_id,
        talking_photo_scale=talking_photo_scale,
        talking_photo_offset_x=talking_photo_offset_x,
        talking_photo_offset_y=talking_photo_offset_y,
        logger=logger,
    )
    voice_payload = {
        "type": "text",
        "input_text": script,
    }
    if resolved_voice_id:
        voice_payload["voice_id"] = resolved_voice_id

    video_input = {
        "character": character,
        "voice": voice_payload,
    }
    if scene_fit:
        video_input["fit"] = scene_fit

    payload = {
        "video_inputs": [video_input],
        "dimension": {"width": width, "height": height},
    }
    if use_avatar_iv_model:
        payload["use_avatar_iv_model"] = True

    response = requests.post(
        "https://api.heygen.com/v2/video/generate",
        headers={"X-Api-Key": api_key},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()

    video_id = response.json()["data"]["video_id"]
    video_url = _poll_video_url(
        api_key=api_key,
        video_id=video_id,
        timeout=timeout,
        poll_interval=poll_interval,
        logger=logger,
    )

    download_response = requests.get(video_url, timeout=120)
    download_response.raise_for_status()
    output_path.write_bytes(download_response.content)
    return output_path


def _build_character_payload(
    api_key: str,
    avatar_id: str,
    voice_id: str | None,
    talking_photo_scale: float | None,
    talking_photo_offset_x: float | None,
    talking_photo_offset_y: float | None,
    logger: logging.Logger | None,
) -> tuple[dict[str, object], str | None]:
    """Resolve whether the provided ID is a public/avatar ID or a photo-avatar look ID."""
    photo_details = _get_photo_avatar_details(api_key=api_key, look_id=avatar_id)
    if photo_details is not None:
        resolved_voice_id = voice_id or photo_details.get("default_voice_id")
        if not resolved_voice_id:
            group_id = photo_details.get("group_id")
            if isinstance(group_id, str) and group_id:
                resolved_voice_id = _get_photo_avatar_group_default_voice_id(
                    api_key=api_key,
                    group_id=group_id,
                )
        if logger is not None:
            logger.info("Using HeyGen Photo Avatar look %s", avatar_id)
        if not resolved_voice_id:
            raise ValueError(
                "HEYGEN_VOICE_ID is required for Photo Avatar generation when no default voice is available."
            )
        character_payload: dict[str, object] = {
            "type": "talking_photo",
            "talking_photo_id": avatar_id,
        }
        if talking_photo_scale is not None:
            character_payload["scale"] = talking_photo_scale
        if talking_photo_offset_x is not None or talking_photo_offset_y is not None:
            character_payload["offset"] = {
                "x": talking_photo_offset_x or 0.0,
                "y": talking_photo_offset_y or 0.0,
            }
        return (character_payload, resolved_voice_id)

    if logger is not None:
        logger.info("Using HeyGen avatar ID %s", avatar_id)
    return (
        {
            "type": "avatar",
            "avatar_id": avatar_id,
            "avatar_style": "normal",
        },
        voice_id,
    )


def _get_photo_avatar_details(api_key: str, look_id: str) -> dict[str, str] | None:
    """Return photo avatar details when the ID belongs to a photo-avatar look."""
    response = requests.get(
        f"https://api.heygen.com/v2/photo_avatar/{look_id}",
        headers={"X-Api-Key": api_key},
        timeout=30,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    data = response.json().get("data", {})
    if not isinstance(data, dict):
        return None
    return data


def _get_photo_avatar_group_default_voice_id(api_key: str, group_id: str) -> str | None:
    """Resolve the default voice configured on the parent photo-avatar group."""
    response = requests.get(
        "https://api.heygen.com/v2/avatar_group.list",
        headers={"X-Api-Key": api_key},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json().get("data", {})
    groups = data.get("avatar_group_list", []) if isinstance(data, dict) else []
    for group in groups:
        if isinstance(group, dict) and group.get("id") == group_id:
            default_voice_id = group.get("default_voice_id")
            if isinstance(default_voice_id, str) and default_voice_id:
                return default_voice_id
            return None
    return None


def _poll_video_url(
    api_key: str,
    video_id: str,
    timeout: int,
    poll_interval: int,
    logger: logging.Logger | None,
) -> str:
    """Poll HeyGen until the generated video is ready and return its download URL."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        status_response = requests.get(
            f"https://api.heygen.com/v1/video_status.get?video_id={video_id}",
            headers={"X-Api-Key": api_key},
            timeout=30,
        )
        status_response.raise_for_status()
        data = status_response.json()["data"]
        status = data["status"]

        if status == "completed":
            return data["video_url"]
        if status == "failed":
            raise RuntimeError(f"HeyGen generation failed: {data.get('error', 'unknown error')}")

        if logger is not None:
            elapsed = int(time.time() - start_time)
            logger.info("Step 2/4: Polling... (%ss elapsed)", elapsed)
        time.sleep(poll_interval)

    raise TimeoutError(f"HeyGen generation timed out after {timeout} seconds.")
