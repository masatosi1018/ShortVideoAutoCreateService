"""Instagram downloader powered by yt-dlp."""

from __future__ import annotations

import logging
from pathlib import Path

import yt_dlp


class DownloadFailedError(RuntimeError):
    """Raised when yt-dlp cannot fetch the requested Instagram reel."""


def download_reel(
    url: str,
    output_dir: Path,
    cookie_file: Path,
    logger: logging.Logger | None = None,
) -> Path:
    """Download an Instagram reel into `output_dir/source_video.mp4`."""
    if not url:
        raise ValueError("Instagram URL is required.")
    if not cookie_file.exists():
        raise FileNotFoundError(
            f"Instagram cookie file not found: {cookie_file}. "
            "Create it by following scripts/export_instagram_cookies.md."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = output_dir / "source_video.%(ext)s"
    ydl_opts = {
        "outtmpl": str(output_template),
        "format": "best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "cookiefile": str(cookie_file),
        "sleep_interval": 2,
        "max_sleep_interval": 5,
        "retries": 3,
        "quiet": False,
        "no_warnings": False,
    }
    return _download_with_opts(
        url=url,
        output_dir=output_dir,
        ydl_opts=ydl_opts,
        logger=logger,
    )


def _download_with_opts(
    url: str,
    output_dir: Path,
    ydl_opts: dict[str, object],
    logger: logging.Logger | None = None,
) -> Path:
    """Run yt-dlp with the provided options and normalize the output filename."""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_path = Path(ydl.prepare_filename(info))
    except yt_dlp.utils.DownloadError as exc:
        raise DownloadFailedError(_build_download_error_message(exc)) from exc
    except Exception as exc:
        raise DownloadFailedError(_build_download_error_message(exc)) from exc

    candidate_path = _resolve_downloaded_path(downloaded_path, output_dir)
    final_path = output_dir / "source_video.mp4"
    if candidate_path != final_path:
        candidate_path.replace(final_path)

    if logger is not None:
        logger.info("Downloaded source video to %s", final_path)
    return final_path


def _resolve_downloaded_path(downloaded_path: Path, output_dir: Path) -> Path:
    """Find the file yt-dlp produced, even when post-processing changed its extension."""
    if downloaded_path.exists():
        return downloaded_path

    mp4_path = output_dir / "source_video.mp4"
    if mp4_path.exists():
        return mp4_path

    matches = sorted(output_dir.glob("source_video.*"))
    if not matches:
        raise FileNotFoundError("yt-dlp completed but the downloaded media file could not be found.")
    return matches[0]


def _build_download_error_message(error: Exception) -> str:
    """Convert a yt-dlp error into an operator-friendly message."""
    message = str(error).lower()
    if "login required" in message or "sign in" in message:
        return (
            "ダウンロード失敗: Instagram がログインを要求しました。\n"
            "対処法:\n"
            "1. 捨てアカウントが有効か確認\n"
            "2. config/instagram_cookies.txt を再取得する\n"
            "3. Instagram に再ログインしてから cookies.txt を作り直す"
        )
    if "rate-limit" in message or "too many requests" in message:
        return (
            "ダウンロード失敗: Instagram のレート制限に達した可能性があります。\n"
            "対処法:\n"
            "1. 1 時間以上待って再実行\n"
            "2. ダウンロード頻度を 1 日 30 本以内に抑える\n"
            "3. クッキーを差し替えて再試行する"
        )
    return f"Instagram ダウンロードに失敗しました: {error}"
