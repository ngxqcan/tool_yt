"""Unit and integration tests for Competitor Video Analyzer, Script Generator, and Utilities."""

import json
import os
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
    analyze_multiple_competitors,
    log_audit_trail,
    get_project_root,
)
from models import (
    GeneratedScriptModel,
    HookModel,
    OutroModel,
    SectionBeatModel,
    StyleTemplateModel,
    extract_json_object,
    parse_and_validate_json,
    strip_markdown_fences,
)
from script_generator import (
    load_style_template,
    generate_script,
    format_script_as_markdown,
    save_script_outputs,
)
from main import parse_topics_csv, run_pipeline
from utils import generate_subtitles, validate_api_keys


class TestModelsAndJsonCleaning(unittest.TestCase):
    """Test suite for models.py and robust JSON extraction."""

    def test_strip_markdown_fences(self):
        fenced = "```json\n{\"hook_style\": \"test\"}\n```"
        self.assertEqual(strip_markdown_fences(fenced), "{\"hook_style\": \"test\"}")

        fenced_plain = "```\n{\"hook_style\": \"test\"}\n```"
        self.assertEqual(strip_markdown_fences(fenced_plain), "{\"hook_style\": \"test\"}")

    def test_extract_json_object(self):
        noisy_text = "Here is the JSON response you requested:\n```json\n{\"topic\": \"AI 2026\"}\n```\nHope this helps!"
        extracted = extract_json_object(noisy_text)
        self.assertIn("{\"topic\": \"AI 2026\"}", extracted)

    def test_parse_and_validate_json_style_template(self):
        raw = """```json
        {
          "hook_style": "Dramatic dilemma",
          "section_count": 4,
          "section_pacing": ["Beat 1", "Beat 2", "Beat 3", "Beat 4"],
          "tone": "Urgent",
          "title_formula": "Why [Topic] Is Dangerous",
          "avg_section_length_seconds": 60,
          "ending_style": "Call to action",
          "estimated_total_length_seconds": 240
        }
        ```"""
        model = parse_and_validate_json(raw, StyleTemplateModel)
        self.assertEqual(model.hook_style, "Dramatic dilemma")
        self.assertEqual(model.section_count, 4)
        self.assertEqual(model.avg_section_length_seconds, 60)


class TestSubtitlesAndUtilities(unittest.TestCase):
    """Test suite for subtitle generation and utils."""

    def test_generate_subtitles_srt_and_vtt(self):
        script_dict = {
            "hook": {"duration_seconds": 15, "spoken_dialogue": "This is the hook line."},
            "sections": [
                {"duration_seconds": 45, "spoken_dialogue": "First main section dialogue."},
                {"duration_seconds": 60, "spoken_dialogue": "Second main section dialogue."},
            ],
            "call_to_action_and_outro": {"duration_seconds": 20, "spoken_dialogue": "Subscribe now!"},
        }

        srt, vtt = generate_subtitles(script_dict)

        # Check SRT format
        self.assertIn("00:00:00,000 --> 00:00:15,000", srt)
        self.assertIn("This is the hook line.", srt)
        self.assertIn("00:01:00,000 --> 00:02:00,000", srt)
        self.assertIn("Subscribe now!", srt)

        # Check VTT format
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("00:00:00.000 --> 00:00:15.000", vtt)

    def test_validate_api_keys_diagnostics(self):
        res = validate_api_keys(gemini_key=None, youtube_key=None)
        self.assertIn("gemini", res)
        self.assertIn("youtube", res)
        self.assertFalse(res["gemini"]["valid"])


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
        self.assertTrue(pattern.has_numbers)
        self.assertTrue(pattern.has_brackets)
        self.assertEqual(pattern.capitalization_style, "Mixed Case / Standard")
        self.assertEqual(pattern.tag_themes, ["ai", "productivity", "tech"])
        self.assertGreater(pattern.title_length_chars, 20)

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

            meta = fetch_public_metadata(video_id, force_refresh=True)
            self.assertEqual(meta["video_id"], video_id)
            self.assertEqual(meta["title"], "Test Title Video")

            cache_file = get_project_root() / "cache" / "competitor" / video_id / "metadata.json"
            self.assertTrue(cache_file.exists())

    def test_transcript_guardrail_notice(self):
        video_id = "test_transcript_vid"
        mock_transcript = [
            {"start": 0.0, "duration": 3.5, "text": "Hello world"},
            {"start": 3.5, "duration": 4.0, "text": "Welcome to this breakdown"},
        ]

        with patch("competitor_analyzer.YouTubeTranscriptApi") as mock_api:
            mock_api.get_transcript.return_value = mock_transcript
            result = fetch_transcript(video_id, force_refresh=True)
            self.assertIsNotNone(result)
            self.assertIn("REFERENCE-ONLY, DO NOT QUOTE", result["_guardrail_notice"])
            self.assertEqual(result["entry_count"], 2)
            self.assertEqual(result["video_id"], video_id)

    def test_missing_transcript_fallback(self):
        video_id = "no_transcript_vid"
        with patch("competitor_analyzer.YouTubeTranscriptApi") as mock_api:
            mock_api.get_transcript.side_effect = Exception("No captions available.")
            mock_api.fetch.side_effect = Exception("No captions available.")
            result = fetch_transcript(video_id, force_refresh=True)
            self.assertIsNone(result)

            log_file = get_project_root() / "logs" / "competitor_analysis.log"
            self.assertTrue(log_file.exists())

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
        self.assertIsInstance(template, StyleTemplateModel)
        self.assertEqual(template.section_count, 5)
        self.assertGreater(len(template.section_pacing), 0)

    def test_analyze_multiple_competitors(self):
        urls = ["dQw4w9WgXcQ", "dQw4w9WgXcQ"]
        composite_path = analyze_multiple_competitors(urls)
        self.assertTrue(composite_path.exists())

        with open(composite_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("hook_style", data)
        self.assertIn("section_count", data)


class TestScriptGenerator(unittest.TestCase):
    """Test suite for script_generator.py."""

    def test_load_style_template_dict_and_path(self):
        sample_dict = {"hook_style": "Cold open question", "section_count": 3}
        loaded = load_style_template(sample_dict)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.section_count, 3)
        self.assertIsNone(load_style_template("non_existent_file.json"))

    def test_generate_script_with_style_template_and_subtitles(self):
        style_template = StyleTemplateModel(
            hook_style="Dramatic dilemma teaser",
            section_count=3,
            section_pacing=["Beat 1: The Trap", "Beat 2: The Shift", "Beat 3: Execution"],
            tone="Fast-paced, urgent, and insightful",
            title_formula="Why [Topic] is Collapsing (And What to Do)",
            avg_section_length_seconds=80,
            ending_style="Hard cliffhanger and playlist link",
            estimated_total_length_seconds=300,
        )

        script = generate_script(
            topic="Next-Gen Web Frameworks",
            style_template_source=style_template,
        )

        self.assertEqual(script.topic, "Next-Gen Web Frameworks")
        self.assertTrue(script.style_template_applied)
        self.assertTrue(len(script.sections) > 0)

        # Subtitle check
        srt, vtt = generate_subtitles(script.model_dump())
        self.assertTrue(len(srt) > 0)
        self.assertTrue(vtt.startswith("WEBVTT"))


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
                rate_limit_delay=0.1,
                export_subtitles=True,
            )
            self.assertEqual(len(out_files), 1)
            self.assertTrue(out_files[0].exists())
            # Verify companion markdown, srt, and vtt were generated
            self.assertTrue(out_files[0].with_suffix(".md").exists())
            self.assertTrue(out_files[0].with_suffix(".srt").exists())
            self.assertTrue(out_files[0].with_suffix(".vtt").exists())


if __name__ == "__main__":
    unittest.main()
