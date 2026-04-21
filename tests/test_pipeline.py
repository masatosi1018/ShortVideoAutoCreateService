"""Basic tests for utility helpers."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from main import looks_like_url, normalize_source_args
from utils.cost_estimator import estimate_heygen_credits
from utils.file_manager import create_job_paths, update_metadata
from pipeline.subtitle_postprocess import analyze_srt_layout, clamp_srt_to_duration, optimize_srt_file


class PipelineUtilityTests(unittest.TestCase):
    """Exercise small utility functions that do not need external services."""

    def test_estimate_heygen_credits(self) -> None:
        """Credits should scale linearly with duration."""
        self.assertEqual(estimate_heygen_credits(28.0), 2.8)

    def test_metadata_updates_merge_nested_values(self) -> None:
        """Metadata updates should merge step payloads rather than replace them."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            metadata_path = Path(tmp_dir) / "metadata.json"
            update_metadata(metadata_path, {"steps": {"source": {"path": "a.mp4"}}})
            update_metadata(metadata_path, {"steps": {"transcription": {"path": "script.txt"}}})
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["steps"]["source"]["path"], "a.mp4")
            self.assertEqual(payload["steps"]["transcription"]["path"], "script.txt")

    def test_create_job_paths_creates_job_directory(self) -> None:
        """A job directory should be created with the expected file layout."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            job_paths = create_job_paths(Path(tmp_dir))
            self.assertTrue(job_paths.job_dir.exists())
            self.assertEqual(job_paths.source_video.name, "source_video.mp4")

    def test_optimize_srt_file_splits_on_phrase_boundaries(self) -> None:
        """Long captions should be broken into shorter phrase-friendly entries."""
        raw_srt = """1
00:00:00,000 --> 00:00:05,360
この誕生日の方は金運が動き出します おめでとう
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            subtitle_path = Path(tmp_dir) / "sample.srt"
            subtitle_path.write_text(raw_srt, encoding="utf-8")

            optimize_srt_file(subtitle_path)
            optimized = subtitle_path.read_text(encoding="utf-8")

        blocks = [block for block in optimized.strip().split("\n\n") if block]
        self.assertEqual(len(blocks), 2)
        self.assertIn("動き出します", blocks[0])
        self.assertNotIn("おめでとう", blocks[0])
        self.assertIn("おめでとう", blocks[1])

    def test_optimize_srt_file_splits_long_phrase_without_spaces(self) -> None:
        """Very long single phrases should still split into multiple readable captions."""
        raw_srt = """1
00:00:00,000 --> 00:00:06,000
働いても豊かさが遠いそんな思いをずっと抱えてきたんじゃないの
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            subtitle_path = Path(tmp_dir) / "sample.srt"
            subtitle_path.write_text(raw_srt, encoding="utf-8")

            optimize_srt_file(subtitle_path)
            optimized = subtitle_path.read_text(encoding="utf-8")

        blocks = [block for block in optimized.strip().split("\n\n") if block]
        self.assertGreaterEqual(len(blocks), 2)
        for block in blocks:
            lines = block.splitlines()
            self.assertGreaterEqual(len(lines), 3)
            text = "".join(lines[2:])
            self.assertLessEqual(len(text.replace(" ", "")), 18)

    def test_analyze_srt_layout_reports_longest_line(self) -> None:
        """Processed subtitles should expose simple size metrics for font estimation."""
        raw_srt = """1
00:00:00,000 --> 00:00:05,360
この誕生日の方は金運が動き出します おめでとう
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            subtitle_path = Path(tmp_dir) / "sample.srt"
            subtitle_path.write_text(raw_srt, encoding="utf-8")

            optimize_srt_file(subtitle_path)
            metrics = analyze_srt_layout(subtitle_path)

        self.assertGreater(metrics["entry_count"], 0)
        self.assertGreater(metrics["max_caption_chars"], 0)
        self.assertGreater(metrics["max_line_chars"], 0)

    def test_clamp_srt_to_duration_trims_overhang(self) -> None:
        """Subtitle end times should not exceed the provided video duration."""
        raw_srt = """1
00:00:00,000 --> 00:00:02,000
はじめ

2
00:00:02,000 --> 00:00:05,000
おわり
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            subtitle_path = Path(tmp_dir) / "sample.srt"
            subtitle_path.write_text(raw_srt, encoding="utf-8")

            clamp_srt_to_duration(subtitle_path, max_duration_ms=3500)
            optimized = subtitle_path.read_text(encoding="utf-8")

        self.assertIn("00:00:02,000 --> 00:00:03,500", optimized)
        self.assertNotIn("00:00:05,000", optimized)

    def test_normalize_source_args_maps_positional_url(self) -> None:
        """A positional URL should be treated as the URL input mode."""
        args = argparse.Namespace(url=None, input_file=None, source="https://example.com/reel/abc", verbose=False)
        normalized = normalize_source_args(args)
        self.assertEqual(normalized.url, "https://example.com/reel/abc")
        self.assertIsNone(normalized.input_file)

    def test_normalize_source_args_maps_positional_file(self) -> None:
        """A positional non-URL should be treated as a local file path."""
        args = argparse.Namespace(url=None, input_file=None, source="inputs/sample.mp4", verbose=False)
        normalized = normalize_source_args(args)
        self.assertEqual(normalized.input_file, "inputs/sample.mp4")
        self.assertIsNone(normalized.url)

    def test_looks_like_url_requires_http_scheme(self) -> None:
        """Only HTTP(S) values should be interpreted as URLs."""
        self.assertTrue(looks_like_url("https://www.instagram.com/reel/test"))
        self.assertFalse(looks_like_url("instagram.com/reel/test"))


if __name__ == "__main__":
    unittest.main()
