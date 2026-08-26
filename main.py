"""Main Pipeline Runner & Unified CLI.

Orchestrates batch topic processing, outlier detection, comment gap mining,
neural voiceover synthesis, shorts repurposing, and automated video assembly.
Includes batch checkpointing (--resume), interactive progress bars, and verbose logging.

CLI Examples:
1. Launch Streamlit Interactive Web App:
   python main.py --gui

2. Validate API keys:
   python main.py --validate-keys

3. Full automated pipeline with resume support:
   python main.py --topics topics.csv --resume --generate-tts --generate-shorts --design-thumbnails

4. Analyze video thumbnail with Gemini Vision:
   python main.py --analyze-thumbnail "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from tqdm import tqdm

from channel_crawler import crawl_channel_outliers
from comment_miner import mine_video_comments
from competitor_analyzer import analyze_competitor_video, analyze_multiple_competitors
from script_generator import generate_script, save_script_outputs
from shorts_generator import generate_shorts_from_topic_or_script, save_shorts_outputs
from thumbnail_analyzer import analyze_video_thumbnail
from thumbnail_designer import design_thumbnail_prompts, render_thumbnail_mockup
from tts_generator import generate_script_voiceover
from utils import RateLimiter, ensure_dir, get_project_root, setup_logging, validate_api_keys

LOGGER = setup_logging("main_pipeline")


def parse_topics_csv(csv_path: str) -> List[Dict[str, str]]:
    """Parse topics CSV file into a list of topic dictionaries."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Topics CSV file not found at: {csv_path}")

    topics: List[Dict[str, str]] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = [fn.strip().lower() for fn in (reader.fieldnames or [])]

        if "topic" in fieldnames:
            f.seek(0)
            dict_reader = csv.DictReader(f)
            for row in dict_reader:
                cleaned_row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
                topic = cleaned_row.get("topic", "")
                if topic:
                    topics.append({
                        "topic": topic,
                        "audience": cleaned_row.get("target_audience") or cleaned_row.get("audience", ""),
                        "notes": cleaned_row.get("notes", ""),
                    })
        else:
            f.seek(0)
            plain_reader = csv.reader(f)
            for row in plain_reader:
                if row and row[0].strip():
                    topics.append({
                        "topic": row[0].strip(),
                        "audience": row[1].strip() if len(row) > 1 else "",
                        "notes": row[2].strip() if len(row) > 2 else "",
                    })

    LOGGER.info(f"Loaded {len(topics)} topic(s) from {csv_path}")
    return topics


def load_batch_checkpoint() -> Dict[str, Any]:
    """Load previously completed topics from cache/batch_state.json."""
    state_file = get_project_root() / "cache" / "batch_state.json"
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"completed_topics": []}
    return {"completed_topics": []}


def save_batch_checkpoint(completed_topic: str) -> None:
    """Record completed topic in cache/batch_state.json."""
    state_file = ensure_dir(get_project_root() / "cache") / "batch_state.json"
    state = load_batch_checkpoint()
    if completed_topic not in state["completed_topics"]:
        state["completed_topics"].append(completed_topic)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def run_pipeline(
    topics_path: str,
    style_template_path: Optional[str] = None,
    competitor_url: Optional[str] = None,
    competitor_urls: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    model_name: Optional[str] = None,
    rate_limit_delay: float = 2.0,
    export_subtitles: bool = True,
    generate_tts: bool = False,
    generate_shorts: bool = False,
    design_thumbnails: bool = False,
    generate_ai_images: bool = False,
    assemble_video: bool = False,
    add_bgm: bool = True,
    bgm_genre: str = "lofi",
    force_refresh: bool = False,
    tts_voice: str = "vi-male",
    resume: bool = False,
) -> List[Path]:
    """Execute the end-to-end video production pipeline."""
    active_style_template = style_template_path

    # Step 1: Synthesize competitor templates if provided
    if competitor_urls:
        LOGGER.info(f"Synthesizing {len(competitor_urls)} competitor reference video(s)...")
        composite_path = analyze_multiple_competitors(
            urls_or_ids=competitor_urls,
            gemini_model=model_name,
            force_refresh=force_refresh,
        )
        active_style_template = str(composite_path)
    elif competitor_url:
        urls = [u.strip() for u in competitor_url.split(",") if u.strip()]
        if len(urls) > 1:
            composite_path = analyze_multiple_competitors(
                urls_or_ids=urls,
                gemini_model=model_name,
                force_refresh=force_refresh,
            )
            active_style_template = str(composite_path)
        else:
            LOGGER.info(f"Analyzing single competitor reference: {competitor_url}")
            active_style_template = analyze_competitor_video(
                url_or_id=competitor_url,
                gemini_model=model_name,
                force_refresh=force_refresh,
            )

    # Step 2: Load topics
    topics = parse_topics_csv(topics_path)
    if not topics:
        LOGGER.warning("No topics found in CSV file.")
        return []

    # Checkpoint resume support
    completed_topics = set()
    if resume:
        chk = load_batch_checkpoint()
        completed_topics = set(chk.get("completed_topics", []))
        if completed_topics:
            LOGGER.info(f"[RESUME ACTIVE] Found {len(completed_topics)} already completed topic(s). Skipping...")

    limiter = RateLimiter(min_interval_seconds=rate_limit_delay)
    generated_files: List[Path] = []

    progress_bar = tqdm(topics, desc="Processing Topics", unit="topic", dynamic_ncols=True)
    for item in progress_bar:
        topic_title = item["topic"]
        audience = item.get("audience")

        if resume and topic_title in completed_topics:
            progress_bar.set_postfix_str(f"Skipping: {topic_title[:20]}...")
            continue

        progress_bar.set_postfix_str(f"Generating: {topic_title[:20]}...")
        limiter.wait()

        # 1. Generate Main Script
        script_model = generate_script(
            topic=topic_title,
            target_audience=audience,
            style_template_source=active_style_template,
            gemini_model=model_name,
        )

        custom_output = None
        if output_dir:
            topic_slug = "".join(c if c.isalnum() else "_" for c in topic_title).strip("_")[:50]
            custom_output = str(Path(output_dir) / f"script_{topic_slug}.json")

        saved_path = save_script_outputs(
            script_data=script_model,
            output_path=custom_output,
            export_subtitles=export_subtitles,
        )
        generated_files.append(saved_path)

        voice_path = None
        # 2. TTS Voiceover Generation
        if generate_tts or assemble_video:
            try:
                voice_path = generate_script_voiceover(script_model, voice=tts_voice)
            except Exception as exc:
                LOGGER.warning(f"Voiceover generation failed for '{topic_title}': {exc}")

        # 3. 100% Free AI Scene Visuals
        if generate_ai_images or assemble_video:
            try:
                from image_generator import generate_images_for_script
                generate_images_for_script(script_model, force_refresh=force_refresh)
            except Exception as exc:
                LOGGER.warning(f"AI image generation failed for '{topic_title}': {exc}")

        # 4. Automated 1080p Video Assembly with Audio Ducking & Subtitles
        if assemble_video and voice_path and Path(voice_path).exists():
            try:
                from video_assembler import assemble_video_from_script
                assemble_video_from_script(
                    script_data=script_model,
                    voiceover_path=str(voice_path),
                    add_bgm=add_bgm,
                    bgm_genre=bgm_genre,
                )
            except Exception as exc:
                LOGGER.warning(f"Video assembly failed for '{topic_title}': {exc}")

        # 5. Shorts & Reels Repurposing
        if generate_shorts:
            try:
                shorts = generate_shorts_from_topic_or_script(topic_title, script_model, gemini_model=model_name)
                save_shorts_outputs(shorts)
            except Exception as exc:
                LOGGER.warning(f"Shorts generation failed for '{topic_title}': {exc}")

        # 6. Thumbnail Prompts & Mockup Card
        if design_thumbnails:
            try:
                t_model = design_thumbnail_prompts(topic_title, gemini_model=model_name)
                if t_model.prompts:
                    mock_text = t_model.prompts[0].recommended_text_overlay
                    topic_slug = "".join(c if c.isalnum() else "_" for c in topic_title).strip("_")[:40]
                    mock_out = ensure_dir(get_project_root() / "output" / "thumbnails") / f"mockup_{topic_slug}.png"
                    render_thumbnail_mockup(text_overlay=mock_text, subtitle=topic_title, output_path=str(mock_out))
            except Exception as exc:
                LOGGER.warning(f"Thumbnail design failed for '{topic_title}': {exc}")

        # Save checkpoint
        save_batch_checkpoint(topic_title)

    LOGGER.info(f"\nPipeline successfully completed! Generated {len(generated_files)} script package(s).")
    return generated_files


def launch_gui() -> None:
    """Launch Streamlit web dashboard."""
    app_path = get_project_root() / "app.py"
    LOGGER.info("Starting Streamlit Web Dashboard at http://localhost:8501...")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)])


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube AI Production Suite - End-to-End Content Engine.")
    parser.add_argument("--gui", action="store_true", help="Launch interactive Streamlit web dashboard.")
    parser.add_argument("--topics", "-t", default="topics.csv", help="Path to topics CSV file (default: topics.csv).")
    parser.add_argument(
        "--style_template",
        "-s",
        default=None,
        help="Path to style_template.json produced by competitor_analyzer.py.",
    )
    parser.add_argument("--auto-all-in-one", default=None, help="1-Click All-in-One Autopilot from a single competitor URL (runs DNA + Script + TTS + Shorts + Thumbnails + AI Visuals + 1080p Video).")
    parser.add_argument("--competitor_url", "-c", default=None, help="Competitor reference URL(s).")
    parser.add_argument("--competitor_urls", default=None, help="Comma-separated list of competitor URLs.")
    parser.add_argument("--channel", default=None, help="Crawl channel for viral outlier videos (@handle or ID).")
    parser.add_argument("--mine-comments", default=None, help="Mine viewer comment gaps for a video URL.")
    parser.add_argument("--analyze-thumbnail", default=None, help="Download and analyze actual video thumbnail via Gemini Vision.")
    parser.add_argument("--output_dir", "-o", default=None, help="Directory to save generated scripts.")
    parser.add_argument("--model", "-m", default=None, help="Gemini model name.")
    parser.add_argument("--rate-limit-delay", type=float, default=2.0, help="Delay between API calls in seconds.")
    parser.add_argument("--no-subtitles", action="store_true", help="Disable automatic SRT/VTT subtitle export.")
    parser.add_argument("--generate-tts", action="store_true", help="Automatically generate neural TTS voiceover MP3.")
    parser.add_argument("--voice", default="vi-male", help="Voice shortcut or neural voice name.")
    parser.add_argument("--generate-shorts", action="store_true", help="Automatically generate 3 viral Shorts scripts.")
    parser.add_argument("--design-thumbnails", action="store_true", help="Generate AI thumbnail prompts and mockup.")
    parser.add_argument("--generate-ai-images", action="store_true", help="Generate 100%% Free Full HD AI scene visuals via Pollinations FLUX.1.")
    parser.add_argument("--assemble-video", action="store_true", help="Assemble complete 1080p MP4 video with AI visuals, BGM ducking, and kinetic subtitles.")
    parser.add_argument("--no-bgm", action="store_true", help="Disable background music mixing.")
    parser.add_argument("--bgm-genre", default="lofi", choices=["lofi", "cinematic", "tech"], help="Background music genre.")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache for analysis.")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted batch run from checkpoint state.")
    parser.add_argument("--validate-keys", action="store_true", help="Run pre-flight API diagnostics.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose debug logging.")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        LOGGER.setLevel(logging.DEBUG)

    # GUI Mode
    if args.gui:
        launch_gui()
        return

    # API Validation
    if args.validate_keys:
        LOGGER.info("Running pre-flight API key diagnostics...")
        diag = validate_api_keys(model_name=args.model)
        print("\n--- API Key Diagnostic Results ---")
        print(f"Gemini API:   [{'OK' if diag['gemini']['valid'] else 'INFO'}] {diag['gemini']['message']}")
        print(f"YouTube API:  [{'OK' if diag['youtube']['valid'] else 'INFO'}] {diag['youtube']['message']}")
        print("----------------------------------\n")
        if not args.channel and not args.mine_comments and not args.competitor_url and not args.analyze_thumbnail:
            return

    # Visual Thumbnail Vision Mode
    if args.analyze_thumbnail:
        analyze_video_thumbnail(args.analyze_thumbnail, force_refresh=args.force_refresh)
        return

    # Channel Outliers Mode
    if args.channel:
        crawl_channel_outliers(args.channel)
        return

    # Comment Gap Mining Mode
    if args.mine_comments:
        mine_video_comments(args.mine_comments)
        return

    comp_url = args.competitor_url
    gen_tts = args.generate_tts
    gen_shorts = args.generate_shorts
    gen_thumbs = args.design_thumbnails
    gen_ai_imgs = args.generate_ai_images
    assemb_vid = args.assemble_video

    if args.auto_all_in_one:
        comp_url = args.auto_all_in_one
        gen_tts = True
        gen_shorts = True
        gen_thumbs = True
        gen_ai_imgs = True
        assemb_vid = True
        LOGGER.info(f"⚡ [All-in-One Autopilot] Activated for competitor URL: {comp_url}")

    competitor_url_list = None
    if args.competitor_urls:
        competitor_url_list = [u.strip() for u in args.competitor_urls.split(",") if u.strip()]

    try:
        run_pipeline(
            topics_path=args.topics,
            style_template_path=args.style_template,
            competitor_url=comp_url,
            competitor_urls=competitor_url_list,
            output_dir=args.output_dir,
            model_name=args.model,
            rate_limit_delay=args.rate_limit_delay,
            export_subtitles=not args.no_subtitles,
            generate_tts=gen_tts,
            generate_shorts=gen_shorts,
            design_thumbnails=gen_thumbs,
            generate_ai_images=gen_ai_imgs,
            assemble_video=assemb_vid,
            add_bgm=not args.no_bgm,
            bgm_genre=args.bgm_genre,
            force_refresh=args.force_refresh,
            tts_voice=args.voice,
            resume=args.resume,
        )
    except Exception as exc:
        LOGGER.error(f"Pipeline execution error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
