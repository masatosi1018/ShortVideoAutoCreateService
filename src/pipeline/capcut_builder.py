"""CapCut draft builder helpers."""

from __future__ import annotations

import math
import logging
import shutil
from pathlib import Path
from typing import Any

import requests

from pipeline.subtitle_postprocess import analyze_srt_layout
from utils.cost_estimator import get_video_duration


def build_capcut_project(
    base_url: str,
    video_path: Path,
    srt_path: Path,
    output_dir: Path,
    subtitle_style: dict[str, Any],
    api_workdir: Path | None = None,
    width: int = 1080,
    height: int = 1920,
    logger: logging.Logger | None = None,
) -> Path:
    """Build a CapCut draft using the CapCutAPI HTTP endpoints."""
    if not video_path.exists():
        raise FileNotFoundError(f"Avatar video not found: {video_path}")
    if not srt_path.exists():
        raise FileNotFoundError(f"Subtitle file not found: {srt_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    draft_id = _create_draft(base_url, width, height)
    duration = get_video_duration(video_path)
    subtitle_payload = _normalize_subtitle_style(subtitle_style, srt_path)

    _post_json(
        f"{base_url}/add_video",
        {
            "draft_id": draft_id,
            "draft_folder": str(output_dir.resolve()),
            "video_url": str(video_path.resolve()),
            "start": 0,
            "end": duration,
            "width": width,
            "height": height,
        },
    )
    if logger is not None:
        logger.info("CapCut draft created: %s", draft_id)

    _post_json(
        f"{base_url}/add_subtitle",
        {
            "draft_id": draft_id,
            "draft_folder": str(output_dir.resolve()),
            "srt": str(srt_path.resolve()),
            "width": width,
            "height": height,
            **subtitle_payload,
        },
    )

    _post_json(
        f"{base_url}/save_draft",
        {
            "draft_id": draft_id,
            "draft_folder": str(output_dir.resolve()),
        },
    )
    _collect_capcutapi_draft(
        draft_id=draft_id,
        output_dir=output_dir,
        api_workdir=api_workdir,
    )
    _tune_subtitle_layout(output_dir / draft_id, width=width)
    return output_dir


def copy_to_capcut_folder(
    draft_folder: Path,
    capcut_folder: Path,
    logger: logging.Logger | None = None,
) -> list[Path]:
    """Copy `dfd_*` draft folders into the user's CapCut draft directory."""
    if not draft_folder.exists():
        raise FileNotFoundError(f"CapCut draft folder not found: {draft_folder}")
    if not capcut_folder.exists():
        raise FileNotFoundError(
            f"CAPCUT_DRAFT_FOLDER does not exist: {capcut_folder}. Please verify the path in .env."
        )

    copied_paths: list[Path] = []
    dfd_folders = sorted(path for path in draft_folder.iterdir() if path.is_dir() and path.name.startswith("dfd_"))
    if not dfd_folders:
        raise RuntimeError("No dfd_* folders were created by CapCutAPI.")

    for draft in dfd_folders:
        destination = capcut_folder / draft.name
        if destination.exists():
            raise FileExistsError(f"CapCut draft already exists: {destination}")
        shutil.copytree(draft, destination)
        _rewrite_draft_paths(draft, destination)
        copied_paths.append(destination)
        if logger is not None:
            logger.info("Copied CapCut draft: %s", destination)

    return copied_paths


def _collect_capcutapi_draft(draft_id: str, output_dir: Path, api_workdir: Path | None) -> None:
    """Mirror the generated CapCut draft from the CapCutAPI workdir into the job output folder."""
    if api_workdir is None:
        return
    source_dir = api_workdir / draft_id
    if not source_dir.exists():
        return
    destination = output_dir / draft_id
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source_dir, destination)


def _create_draft(base_url: str, width: int, height: int) -> str:
    """Create a new CapCut draft and return its ID."""
    response = _post_json(f"{base_url}/create_draft", {"width": width, "height": height})
    if "draft_id" not in response:
        raise RuntimeError("CapCutAPI response did not include draft_id.")
    return str(response["draft_id"])


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send a JSON POST request and return the parsed JSON payload."""
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and data.get("success") is False:
        error = data.get("error") or f"CapCutAPI request failed: {url}"
        raise RuntimeError(str(error))
    if isinstance(data, dict) and isinstance(data.get("output"), dict):
        return data["output"]
    return data


def _normalize_subtitle_style(subtitle_style: dict[str, Any], srt_path: Path) -> dict[str, Any]:
    """Translate repo-level subtitle settings into CapCutAPI-compatible fields."""
    style = dict(subtitle_style)
    position_y = style.pop("position_y", None)
    font_size = _resolve_uniform_font_size(
        base_font_size=float(style.pop("font_size", 8.0)),
        srt_path=srt_path,
    )
    shadow_enabled = bool(style.pop("shadow_enabled", False))
    shadow_color = style.pop("shadow_color", "#000000")

    payload: dict[str, Any] = {
        "font_size": round(font_size / 2.4, 2) if font_size > 20 else font_size,
        "font_color": style.pop("font_color", "#FFFFFF"),
        "vertical": False,
        "track_name": "subtitle",
        "alpha": 1.0,
        "scale_x": 1.0,
        "scale_y": 1.0,
    }
    if isinstance(position_y, (int, float)):
        payload["transform_y"] = round(-(float(position_y) - 0.5) * 2, 3)
    if "background_alpha" in style:
        payload["background_alpha"] = style.pop("background_alpha")
    if "background_color" in style:
        payload["background_color"] = style.pop("background_color")
    if "background_style" in style:
        payload["background_style"] = style.pop("background_style")
    if shadow_enabled:
        payload["border_color"] = style.pop("border_color", shadow_color)
        payload["border_width"] = style.pop("border_width", 12.0)
        payload["border_alpha"] = style.pop("border_alpha", 1.0)
    elif "border_width" in style:
        payload["border_width"] = style.pop("border_width")
        payload["border_color"] = style.pop("border_color", "#000000")
        payload["border_alpha"] = style.pop("border_alpha", 1.0)
    payload.update(style)
    return payload


def _resolve_uniform_font_size(base_font_size: float, srt_path: Path) -> float:
    """Estimate one font size for all captions from the longest processed subtitle line."""
    metrics = analyze_srt_layout(srt_path)
    max_caption_chars = max(metrics.get("max_caption_chars", 0), 1)
    scale_factor = 12.0 / max_caption_chars
    scale_factor = min(max(scale_factor, 0.58), 0.9)
    return round(base_font_size * scale_factor, 1)


def _tune_subtitle_layout(draft_dir: Path, width: int) -> None:
    """Widen subtitle text boxes so centered captions do not reflow into 3 lines."""
    draft_info = draft_dir / "draft_info.json"
    if not draft_info.exists():
        return

    import json

    payload = json.loads(draft_info.read_text(encoding="utf-8"))
    text_materials = payload.get("materials", {}).get("texts", [])
    target_width = int(width * 0.64)
    target_line_max_width = 0.80

    for material in text_materials:
        material["fixed_width"] = target_width
        material["line_max_width"] = target_line_max_width
        material["force_apply_line_max_width"] = True

    draft_info.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _rewrite_draft_paths(source_draft: Path, destination_draft: Path) -> None:
    """Rewrite absolute asset paths inside copied CapCut draft JSON files."""
    source_root = str(source_draft.resolve())
    destination_root = str(destination_draft.resolve())
    for json_path in destination_draft.rglob("*.json"):
        try:
            original = json_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = original.replace(source_root, destination_root)
        if updated != original:
            json_path.write_text(updated, encoding="utf-8")
