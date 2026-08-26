"""Unit and integration tests for Competitor Video Analyzer and Script Generator."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from competitor_analyzer import (
    extract_video_id,
    extract_title_thumbnail_pattern,
    parse_iso8601_duration,
    fetch_public_metadata,
    fetch_transcript,
    analyze_structure_with_gemini,
    analyze_competitor_video,
    log_audit_trail,
    get_project_root,
)
from script_generator import (
    load_style_template,
    generate_script,
    format_script_as_markdown,
    save_script_outputs,
)
from main import parse_topics_csv, run_pipeline


class TestCompetitorAnalyzer(unittest.TestCase):
    """Test suite for competitor_analyzer.py."""

    def test_extract_video_id_various_formats(self):
        cases = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s&ab_channel=Rick", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ?t=5", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ?feature=share", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(extract_video_id(url), expected)

    def test_extract_video_id_invalid(self):
        with self.assertRaises(ValueError):
            extract_video_id("")
        with self.assertRaises(ValueError):
            extract_video_id("https://example.com/not-a-video")

    def test_parse_iso8601_duration(self):
        self.assertEqual(parse_iso8601_duration("PT12M30S"), 750)
        self.assertEqual(parse_iso8601_duration("PT1H2M3S"), 3723)
        self.assertEqual(parse_iso8601_duration("PT45S"), 45)
        self.assertEqual(parse_iso8601_duration(""), 0)

    def test_extract_title_thumbnail_pattern(self):
        meta = {
            "title": "5 TOP Tools That Will Change Everything! (2026)",
            "tags": ["ai", "productivity", "tech"],
        }
        pattern = extract_title_thumbnail_pattern(meta)
        self.assertTrue(pattern["has_numbers"])
        self.assertTrue(pattern["has_brackets"])
        self.assertEqual(pattern["capitalization_style"], "Mixed Case / Standard")
        self.assertEqual(pattern["tag_themes"], ["ai", "productivity", "tech"])
        self.assertGreater(pattern["title_length_chars"], 20)

    def test_metadata_caching_and_extraction(self):
        video_id = "test_vid_123"
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "title": "Test Title Video",
                "author_name": "Test Creator",
            }
            mock_get.return_value = mock_resp

            meta = fetch_public_metadata(video_id)
            self.assertEqual(meta["video_id"], video_id)
            self.assertEqual(meta["title"], "Test Title Video")

            # Check cache file was created
            cache_file = get_project_root() / "cache" / "competitor" / video_id / "metadata.json"
            self.assertTrue(cache_file.exists())

    def test_transcript_guardrail_notice(self):
        video_id = "test_transcript_vid"
        mock_transcript = [
            {"start": 0.0, "duration": 3.5, "text": "Hello world"},
            {"start": 3.5, "duration": 4.0, "text": "Welcome to this breakdown"},
        ]

        with patch("competitor_analyzer.YouTubeTranscriptApi") as mock_api:
            # Mock get_transcript or fetch
            mock_api.get_transcript.return_value = mock_transcript
            result = fetch_transcript(video_id)
            self.assertIsNotNone(result)
            self.assertIn("REFERENCE-ONLY, DO NOT QUOTE", result["_guardrail_notice"])
            self.assertEqual(result["entry_count"], 2)
            self.assertEqual(result["video_id"], video_id)

    def test_missing_transcript_fallback(self):
        video_id = "no_transcript_vid"
        with patch("competitor_analyzer.YouTubeTranscriptApi") as mock_api:
            mock_api.get_transcript.side_effect = Exception("No captions available for this video.")
            mock_api.fetch.side_effect = Exception("No captions available for this video.")
            result = fetch_transcript(video_id)
            self.assertIsNone(result)

            # Check audit log recorded fallback
            log_file = get_project_root() / "logs" / "competitor_analysis.log"
            self.assertTrue(log_file.exists())
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                last_entry = json.loads(lines[-1])
                self.assertEqual(last_entry["action"], "TRANSCRIPT_FETCH_FAILED_FALLBACK_TO_METADATA")

    def test_audit_log_generation(self):
        log_audit_trail("test_audit_video", "TEST_ACTION", {"note": "unit test entry"})
        log_file = get_project_root() / "logs" / "competitor_analysis.log"
        self.assertTrue(log_file.exists())

        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.assertTrue(len(lines) > 0)
            last_entry = json.loads(lines[-1])
            self.assertEqual(last_entry["guardrail_status"], "COMPLIANT_STRUCTURAL_ONLY")

    def test_style_template_schema_compliance(self):
        metadata = {
            "video_id": "test_schema_vid",
            "title": "7 Secrets of High Performance Coders [2026]",
            "tags": ["coding", "habits"],
            "duration": "PT8M00S",
        }
        transcript_data = {
            "estimated_duration_seconds": 480,
            "entries": [{"start": i * 30, "duration": 25, "text": f"Point {i}"} for i in range(16)],
        }

        template = analyze_structure_with_gemini(metadata, transcript_data)
        
        # Verify required keys
        required_keys = [
            "hook_style",
            "section_count",
            "section_pacing",
            "tone",
            "title_formula",
            "avg_section_length_seconds",
            "ending_style",
            "estimated_total_length_seconds",
            "title_thumbnail_pattern",
        ]
        for key in required_keys:
            self.assertIn(key, template, f"Missing required key in style template: {key}")

        self.assertIsInstance(template["section_count"], int)
        self.assertIsInstance(template["section_pacing"], list)
        self.assertIsInstance(template["avg_section_length_seconds"], int)
        self.assertIsInstance(template["estimated_total_length_seconds"], int)


class TestScriptGenerator(unittest.TestCase):
    """Test suite for script_generator.py."""

    def test_load_style_template_dict_and_path(self):
        sample_dict = {"hook_style": "Cold open question", "section_count": 3}
        self.assertEqual(load_style_template(sample_dict), sample_dict)
        self.assertIsNone(load_style_template("non_existent_file.json"))

    def test_generate_script_with_style_template(self):
        style_template = {
            "hook_style": "Dramatic dilemma teaser",
            "section_count": 3,
            "section_pacing": ["Beat 1: The Trap", "Beat 2: The Shift", "Beat 3: Execution"],
            "tone": "Fast-paced, urgent, and insightful",
            "title_formula": "Why [Topic] is Collapsing (And What to Do)",
            "avg_section_length_seconds": 80,
            "ending_style": "Hard cliffhanger and playlist link",
            "estimated_total_length_seconds": 300,
            "title_thumbnail_pattern": {
                "capitalization_style": "Title Case",
                "title_length_chars": 45,
                "has_numbers": False,
                "has_brackets": True,
            },
        }

        script = generate_script(
            topic="Next-Gen Web Frameworks",
            style_template_source=style_template,
        )

        self.assertEqual(script["topic"], "Next-Gen Web Frameworks")
        self.assertTrue(script["style_template_applied"])
        self.assertIn("suggested_titles", script)
        self.assertIn("hook", script)
        self.assertIn("sections", script)
        self.assertIn("call_to_action_and_outro", script)
        self.assertTrue(len(script["sections"]) > 0)

        # Markdown formatting check
        md_text = format_script_as_markdown(script)
        self.assertIn("# Video Script: Next-Gen Web Frameworks", md_text)
        self.assertIn("## 🎣 Hook", md_text)
        self.assertIn("## 🎬 Main Sections", md_text)


class TestMainPipeline(unittest.TestCase):
    """Test suite for main.py."""

    def test_parse_topics_csv(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("topic,target_audience,notes\nTopic 1,Developers,Test note\nTopic 2,Designers,\n")
            temp_csv = f.name

        try:
            parsed = parse_topics_csv(temp_csv)
            self.assertEqual(len(parsed), 2)
            self.assertEqual(parsed[0]["topic"], "Topic 1")
            self.assertEqual(parsed[0]["audience"], "Developers")
            self.assertEqual(parsed[1]["topic"], "Topic 2")
        finally:
            os.remove(temp_csv)

    def test_run_pipeline_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test_topics.csv"
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("topic\nMicro-SaaS Architecture in 2026\n")

            out_files = run_pipeline(
                topics_path=str(csv_path),
                output_dir=tmpdir,
            )
            self.assertEqual(len(out_files), 1)
            self.assertTrue(out_files[0].exists())


if __name__ == "__main__":
    unittest.main()
