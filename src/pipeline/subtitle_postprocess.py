"""Subtitle post-processing helpers for shorter, phrase-friendly captions."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
import re
from pathlib import Path


@dataclass
class SubtitleEntry:
    """Simple in-memory representation of one SRT caption block."""

    index: int
    start_ms: int
    end_ms: int
    text: str


def optimize_srt_file(
    input_path: Path,
    output_path: Path | None = None,
    *,
    max_chars_per_caption: int = 18,
    max_chars_per_line: int | None = None,
    min_caption_duration_ms: int = 800,
    logger: logging.Logger | None = None,
) -> Path:
    """Rewrite an SRT file into shorter, centered-caption-friendly chunks."""
    entries = _parse_srt(input_path.read_text(encoding="utf-8"))
    split_entries: list[tuple[SubtitleEntry, list[str]]] = []
    all_chunks: list[str] = []
    for entry in entries:
        chunks = _split_caption_text(entry.text, max_chars=max_chars_per_caption)
        if not chunks:
            continue
        split_entries.append((entry, chunks))
        all_chunks.extend(chunks)

    wrap_chars = max_chars_per_line or _derive_wrap_chars(all_chunks)
    optimized: list[SubtitleEntry] = []
    for entry, chunks in split_entries:
        optimized.extend(
            _allocate_timings(
                chunks=chunks,
                start_ms=entry.start_ms,
                end_ms=entry.end_ms,
                min_caption_duration_ms=min_caption_duration_ms,
                max_chars_per_line=wrap_chars,
            )
        )

    for index, entry in enumerate(optimized, start=1):
        entry.index = index

    destination = output_path or input_path
    destination.write_text(_serialize_srt(optimized), encoding="utf-8")
    if logger is not None:
        logger.info(
            "Optimized subtitles into %s shorter captions (%s -> %s).",
            destination.name,
            len(entries),
            len(optimized),
        )
    return destination


def analyze_srt_layout(srt_path: Path) -> dict[str, int]:
    """Return simple layout metrics for a processed SRT file."""
    entries = _parse_srt(srt_path.read_text(encoding="utf-8"))
    max_caption_chars = 0
    max_line_chars = 0
    for entry in entries:
        lines = entry.text.splitlines() or [entry.text]
        max_caption_chars = max(max_caption_chars, _visible_length(entry.text))
        max_line_chars = max(max_line_chars, max(_visible_length(line) for line in lines))
    return {
        "max_caption_chars": max_caption_chars,
        "max_line_chars": max_line_chars,
        "entry_count": len(entries),
    }


def clamp_srt_to_duration(
    input_path: Path,
    max_duration_ms: int,
    output_path: Path | None = None,
    logger: logging.Logger | None = None,
) -> Path:
    """Trim subtitle entries so they never exceed the video duration."""
    entries = _parse_srt(input_path.read_text(encoding="utf-8"))
    clamped: list[SubtitleEntry] = []

    for entry in entries:
        if entry.start_ms >= max_duration_ms:
            continue
        clamped.append(
            SubtitleEntry(
                index=entry.index,
                start_ms=entry.start_ms,
                end_ms=min(entry.end_ms, max_duration_ms),
                text=entry.text,
            )
        )

    for index, entry in enumerate(clamped, start=1):
        entry.index = index

    destination = output_path or input_path
    destination.write_text(_serialize_srt(clamped), encoding="utf-8")
    if logger is not None and entries:
        logger.info(
            "Clamped subtitles to video duration %.3fs (%s -> %s entries).",
            max_duration_ms / 1000,
            len(entries),
            len(clamped),
        )
    return destination


def _parse_srt(raw_text: str) -> list[SubtitleEntry]:
    """Parse a minimal SRT payload into entries."""
    blocks = re.split(r"\n\s*\n", raw_text.strip(), flags=re.MULTILINE)
    entries: list[SubtitleEntry] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0])
        except ValueError:
            index = len(entries) + 1
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->")]
        text = " ".join(lines[2:])
        entries.append(
            SubtitleEntry(
                index=index,
                start_ms=_parse_timestamp(start_raw),
                end_ms=_parse_timestamp(end_raw),
                text=_normalize_text(text),
            )
        )
    return entries


def _serialize_srt(entries: list[SubtitleEntry]) -> str:
    """Serialize subtitle entries back into SRT format."""
    blocks: list[str] = []
    for entry in entries:
        blocks.append(
            "\n".join(
                [
                    str(entry.index),
                    f"{_format_timestamp(entry.start_ms)} --> {_format_timestamp(entry.end_ms)}",
                    entry.text,
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"


def _split_caption_text(text: str, max_chars: int) -> list[str]:
    """Split text into shorter caption chunks while preferring phrase boundaries."""
    if not text:
        return []

    sentences = [segment for segment in re.split(r"(?<=[。！？!?])\s*", text) if segment]
    chunks: list[str] = []
    for sentence in sentences:
        phrases = [part for part in sentence.split(" ") if part]
        current = ""
        for phrase in phrases:
            if not current:
                if _visible_length(phrase) <= max_chars:
                    current = phrase
                else:
                    chunks.extend(_split_long_phrase(phrase, max_chars))
            else:
                if _is_strong_phrase_stop(current):
                    chunks.append(current)
                    if _visible_length(phrase) <= max_chars:
                        current = phrase
                    else:
                        chunks.extend(_split_long_phrase(phrase, max_chars))
                        current = ""
                    continue
                candidate = f"{current} {phrase}"
                if _visible_length(candidate) <= max_chars:
                    current = candidate
                else:
                    chunks.append(current)
                    if _visible_length(phrase) <= max_chars:
                        current = phrase
                    else:
                        chunks.extend(_split_long_phrase(phrase, max_chars))
                        current = ""
        if current:
            chunks.append(current)
    merged = _merge_short_chunks(chunks, max_chars=max_chars)
    return [_normalize_text(chunk) for chunk in merged if chunk.strip()]


def _split_long_phrase(text: str, max_chars: int) -> list[str]:
    """Fallback splitter for long phrases without helpful spaces."""
    remaining = text.strip()
    chunks: list[str] = []
    while _visible_length(remaining) > max_chars:
        split_at = _find_split_index(remaining, target=max_chars)
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _find_split_index(text: str, target: int) -> int:
    """Find a natural-looking split point near the target width."""
    search_end = min(len(text) - 1, target)
    search_start = max(1, min(8, target // 2))
    best_score: tuple[int, int] | None = None
    best_index = target if target < len(text) else max(1, len(text) - 1)

    for index in range(search_start, search_end + 1):
        score = _boundary_score(text[:index], text[index:])
        if score <= -999:
            continue
        weighted_score = score - abs(target - index) * 4
        candidate = (weighted_score, index)
        if best_score is None or candidate > best_score:
            best_score = candidate
            best_index = index

    return best_index


def _boundary_score(left: str, right: str) -> int:
    """Score candidate boundaries. Higher means a more natural phrase break."""
    if not left or not right:
        return -999

    if left.endswith(("。", "！", "？", "!", "?")):
        return 100
    if left.endswith(("ます", "でした", "です", "なさい", "ないの", "わよ", "だよ", "なの", "するの")):
        return 90
    if left.endswith(("から", "けど", "ので", "のに", "でも")):
        return 75
    if left.endswith(("よ", "ね", "ぞ")):
        return 55
    if left.endswith(("った", "いた", "えて", "いて", "れる", "せる", "する", "した")):
        return 50
    if left.endswith(("を", "が", "に", "で", "と", "は", "も", "へ")):
        return 35
    if left.endswith(("て", "で", "し")):
        return 45
    if left.endswith(("い", "る", "た")):
        return 30
    if left.endswith(("っ", "ゃ", "ゅ", "ょ", "ん")):
        return -999
    return 0


def _allocate_timings(
    *,
    chunks: list[str],
    start_ms: int,
    end_ms: int,
    min_caption_duration_ms: int,
    max_chars_per_line: int,
) -> list[SubtitleEntry]:
    """Distribute one caption's duration across newly split chunks."""
    duration = max(end_ms - start_ms, len(chunks) * min_caption_duration_ms)
    weights = [_visible_length(chunk) for chunk in chunks]
    total_weight = max(sum(weights), 1)

    entries: list[SubtitleEntry] = []
    cursor = start_ms
    for index, chunk in enumerate(chunks):
        if index == len(chunks) - 1:
            chunk_end = end_ms
        else:
            proportional = round(duration * (weights[index] / total_weight))
            chunk_end = min(end_ms, cursor + max(min_caption_duration_ms, proportional))
        if chunk_end <= cursor:
            chunk_end = min(end_ms, cursor + min_caption_duration_ms)
        wrapped = _wrap_text(chunk, max_chars_per_line)
        entries.append(SubtitleEntry(index=0, start_ms=cursor, end_ms=chunk_end, text=wrapped))
        cursor = chunk_end

    if entries:
        entries[-1].end_ms = end_ms
    return entries


def _wrap_text(text: str, max_chars_per_line: int) -> str:
    """Wrap a caption into at most two readable lines."""
    if _visible_length(text) <= max_chars_per_line:
        return text

    split_at = _find_split_index(text, target=max_chars_per_line)
    left = text[:split_at].strip()
    right = text[split_at:].strip()
    if not left or not right:
        return text
    if right.startswith(("て", "で", "た", "だ", "の", "は", "も", "を", "に", "へ", "と", "う", "き")):
        return text
    if left.endswith(("し", "も", "う", "き")):
        return text
    return f"{left}\n{right}"


def _is_strong_phrase_stop(text: str) -> bool:
    """Return True when a phrase should usually stand on its own caption."""
    return _boundary_score(text, "次") >= 75


def _merge_short_chunks(chunks: list[str], max_chars: int) -> list[str]:
    """Merge tiny continuation chunks back into the previous phrase when possible."""
    merged: list[str] = []
    for chunk in chunks:
        normalized = _normalize_text(chunk)
        if (
            merged
            and (
                _visible_length(normalized) <= 4
                or normalized.startswith(("う", "い", "の", "よ", "ね", "なさい", "ました", "ます"))
            )
        ):
            previous = merged[-1]
            if _visible_length(previous + normalized) <= max_chars + 4:
                merged[-1] = previous + normalized
                continue
        merged.append(normalized)
    return merged


def _derive_wrap_chars(chunks: list[str]) -> int:
    """Pick a uniform line width so the longest caption lands at roughly two lines."""
    if not chunks:
        return 14
    longest = max(_visible_length(chunk) for chunk in chunks)
    return max(12, math.ceil(longest / 2))


def _normalize_text(text: str) -> str:
    """Collapse extra whitespace while preserving intentional Japanese text."""
    return re.sub(r"\s+", " ", text).strip()


def _visible_length(text: str) -> int:
    """Measure caption length without counting spaces or line breaks."""
    return len(text.replace(" ", "").replace("\n", ""))


def _parse_timestamp(value: str) -> int:
    """Parse `HH:MM:SS,mmm` into milliseconds."""
    hours, minutes, seconds = value.split(":")
    whole_seconds, milliseconds = seconds.split(",")
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(whole_seconds) * 1_000
        + int(milliseconds)
    )


def _format_timestamp(value_ms: int) -> str:
    """Format milliseconds as `HH:MM:SS,mmm`."""
    hours, remainder = divmod(value_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"
