"""Comprehensive Unit and Integration Test Suite for YouTube AI Production Suite."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from broll_finder import search_pexels_videos
from channel_crawler import crawl_channel_outliers
from comment_miner import analyze_comment_gaps, fetch_top_comments
from community_generator import generate_community_content
from competitor_analyzer import (
    analyze_multiple_competitors,
    analyze_structure_with_gemini,
    extract_title_thumbnail_pattern,
    extract_video_id,
    fetch_public_metadata,
    fetch_transcript,
    get_project_root,
    log_audit_trail,
    parse_iso8601_duration,
)
from main import parse_topics_csv, run_pipeline
from models import (
    ChannelAnalysisModel,
    CommentGapAnalysisModel,
    GeneratedScriptModel,
    ShortsCollectionModel,
    StyleTemplateModel,
    ThumbnailDesignModel,
    extract_json_object,
    parse_and_validate_json,
    strip_markdown_fences,
)
from script_generator import generate_script, load_style_template
from shorts_generator import generate_shorts_from_topic_or_script, save_shorts_outputs
from thumbnail_designer import design_thumbnail_prompts, render_thumbnail_mockup
from tts_generator import list_available_voices
from utils import generate_subtitles, validate_api_keys
from video_assembler import render_kinetic_subtitle_frame


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
        self.assertIn("00:00:00,000 --> 00:00:15,000", srt)
        self.assertIn("This is the hook line.", srt)
        self.assertTrue(vtt.startswith("WEBVTT"))

    def test_validate_api_keys_diagnostics(self):
        res = validate_api_keys(gemini_key="", youtube_key="")
        self.assertIn("gemini", res)
        self.assertIn("youtube", res)
        self.assertFalse(res["gemini"]["valid"])


class TestCompetitorAnalyzer(unittest.TestCase):
    """Test suite for competitor_analyzer.py."""

    def test_extract_video_id_various_formats(self):
        cases = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(extract_video_id(url), expected)

    def test_parse_iso8601_duration(self):
        self.assertEqual(parse_iso8601_duration("PT12M30S"), 750)
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
        self.assertEqual(pattern.tag_themes, ["ai", "productivity", "tech"])

    def test_transcript_guardrail_notice(self):
        video_id = "test_transcript_vid"
        mock_transcript = [
            {"start": 0.0, "duration": 3.5, "text": "Hello world"},
        ]
        with patch("competitor_analyzer.YouTubeTranscriptApi") as mock_api:
            mock_api.get_transcript.return_value = mock_transcript
            result = fetch_transcript(video_id, force_refresh=True)
            self.assertIsNotNone(result)
            self.assertIn("REFERENCE-ONLY, DO NOT QUOTE", result["_guardrail_notice"])

    def test_audit_log_generation(self):
        log_audit_trail("test_audit_video", "TEST_ACTION", {"note": "unit test entry"})
        log_file = get_project_root() / "logs" / "competitor_analysis.log"
        self.assertTrue(log_file.exists())


class TestIntelligenceModules(unittest.TestCase):
    """Test suite for Channel Crawler, Comment Miner, and Thumbnail Designer."""

    def test_crawl_channel_outliers_fallback(self):
        res = crawl_channel_outliers("@test_creator")
        self.assertIsInstance(res, ChannelAnalysisModel)
        self.assertTrue(len(res.outlier_videos) > 0)
        self.assertGreaterEqual(res.outlier_videos[0].outlier_score, 2.0)

    def test_mine_video_comments_fallback(self):
        res = analyze_comment_gaps("dQw4w9WgXcQ", comments=[])
        self.assertIsInstance(res, CommentGapAnalysisModel)
        self.assertTrue(len(res.content_gaps) > 0)
        self.assertTrue(len(res.recommended_talking_points) > 0)

    def test_design_thumbnail_prompts(self):
        res = design_thumbnail_prompts("Quantum Computing Breakthrough")
        self.assertIsInstance(res, ThumbnailDesignModel)
        self.assertTrue(len(res.prompts) > 0)
        self.assertIn("midjourney_prompt", res.prompts[0].model_dump())

    def test_thumbnail_vision_analysis_fallback(self):
        from thumbnail_analyzer import analyze_thumbnail_with_gemini_vision
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp_jpg = Path(f.name)
        try:
            from PIL import Image
            img = Image.new("RGB", (100, 100), color="blue")
            img.save(str(tmp_jpg))

            res = analyze_thumbnail_with_gemini_vision("test_vid_vision", tmp_jpg, "http://example.com/thumb.jpg")
            self.assertEqual(res.video_id, "test_vid_vision")
            self.assertTrue(res.has_face)
            self.assertTrue(len(res.ctr_strengths) > 0)
        finally:
            if tmp_jpg.exists():
                os.remove(tmp_jpg)

    def test_batch_checkpoint_saving_and_loading(self):
        from main import load_batch_checkpoint, save_batch_checkpoint
        save_batch_checkpoint("Test Topic Checkpoint 1")
        chk = load_batch_checkpoint()
        self.assertIn("Test Topic Checkpoint 1", chk.get("completed_topics", []))

    def test_render_thumbnail_mockup(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_png = f.name
        try:
            out_path = render_thumbnail_mockup(
                text_overlay="BREAKTHROUGH",
                subtitle="The Complete Guide",
                output_path=tmp_png,
            )
            self.assertTrue(Path(out_path).exists())
            self.assertGreater(os.path.getsize(out_path), 5000)
        finally:
            if os.path.exists(tmp_png):
                os.remove(tmp_png)


class TestShortsAndCommunity(unittest.TestCase):
    """Test suite for Shorts, Community posts, B-roll, and TTS."""

    def test_generate_shorts_and_save(self):
        shorts_coll = generate_shorts_from_topic_or_script("AI Micro-SaaS 2026")
        self.assertIsInstance(shorts_coll, ShortsCollectionModel)
        self.assertGreaterEqual(len(shorts_coll.shorts), 2)

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = save_shorts_outputs(shorts_coll, output_dir=tmpdir)
            self.assertTrue(json_path.exists())
            # Check individual vertical SRT files exist
            srt_file = Path(tmpdir) / f"shorts_AI_Micro_SaaS_2026_1.srt"
            self.assertTrue(srt_file.exists())

    def test_generate_community_content(self):
        post = generate_community_content("Next-Gen Web Frameworks")
        self.assertEqual(len(post.poll_options), 4)
        self.assertTrue(len(post.newsletter_summary) > 50)

    def test_broll_search(self):
        clips = search_pexels_videos("server room")
        self.assertTrue(len(clips) > 0)
        self.assertIn("video_url", clips[0])

    def test_tts_voice_list(self):
        voices = list_available_voices()
        self.assertIn("vi-male", voices)
        self.assertIn("en-male", voices)

    def test_image_generator_fallback(self):
        from image_generator import generate_offline_fallback_image
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp_img = Path(f.name)
        try:
            res = generate_offline_fallback_image("Prompt Test", tmp_img, 1280, 720)
            self.assertTrue(res.exists())
            self.assertGreater(res.stat().st_size, 1000)
        finally:
            if tmp_img.exists():
                os.remove(tmp_img)

    def test_audio_mixer_procedural_sfx_and_bgm(self):
        from audio_mixer import create_procedural_bgm, create_procedural_sfx
        with tempfile.TemporaryDirectory() as tmpdir:
            sfx_p = create_procedural_sfx("whoosh", Path(tmpdir) / "whoosh.wav")
            self.assertTrue(sfx_p.exists())

            bgm_p = create_procedural_bgm("lofi", duration_seconds=1.5, output_path=Path(tmpdir) / "bgm.wav")
            self.assertTrue(bgm_p.exists())
            self.assertGreater(bgm_p.stat().st_size, 10000)

    def test_render_kinetic_subtitle_frame(self):
        from video_assembler import render_kinetic_subtitle_frame
        with tempfile.TemporaryDirectory() as tmpdir:
            base_img = Path(tmpdir) / "base.jpg"
            from PIL import Image
            Image.new("RGB", (640, 360), color="gray").save(str(base_img))

            out_frame = Path(tmpdir) / "frame_out.jpg"
            res = render_kinetic_subtitle_frame(base_img, "This is a MrBeast style kinetic subtitle test", out_frame, 640, 360)
            self.assertTrue(res.exists())
            self.assertGreater(res.stat().st_size, 1000)


class TestMainPipeline(unittest.TestCase):
    """Test suite for main.py."""

    def test_parse_topics_csv(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("topic,target_audience,notes\nTopic 1,Developers,Test note\n")
            temp_csv = f.name
        try:
            parsed = parse_topics_csv(temp_csv)
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0]["topic"], "Topic 1")
        finally:
            os.remove(temp_csv)

    def test_run_pipeline_with_all_features(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test_topics.csv"
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("topic\nMicro-SaaS Architecture in 2026\n")

            out_files = run_pipeline(
                topics_path=str(csv_path),
                output_dir=tmpdir,
                rate_limit_delay=0.05,
                export_subtitles=True,
                generate_tts=False,
                generate_shorts=True,
                design_thumbnails=True,
                generate_ai_images=False,
                assemble_video=False,
            )
            self.assertEqual(len(out_files), 1)
            self.assertTrue(out_files[0].exists())


if __name__ == "__main__":
    unittest.main()

