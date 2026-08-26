"""Main Pipeline Runner & Unified CLI.

Orchestrates batch topic processing, outlier detection, comment gap mining,
neural voiceover synthesis, shorts repurposing, and automated video assembly.

CLI Examples:
1. Launch Streamlit Interactive Web App:
   python main.py --gui

2. Validate API keys:
   python main.py --validate-keys

3. Full automated pipeline for topics CSV:
   python main.py --topics topics.csv --generate-tts --generate-shorts --design-thumbnails

4. Crawl channel for viral outliers:
   python main.py --channel "@mkbhd" --min-outlier-score 2.5
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from channel_crawler import crawl_channel_outliers
from comment_miner import mine_video_comments
from competitor_analyzer import analyze_competitor_video, analyze_multiple_competitors
from script_generator import generate_script, save_script_outputs
from shorts_generator import generate_shorts_from_topic_or_script, save_shorts_outputs
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
    force_refresh: bool = False,
    tts_voice: str = "vi-male",
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

    limiter = RateLimiter(min_interval_seconds=rate_limit_delay)
    generated_files: List[Path] = []

    for idx, item in enumerate(topics, 1):
        topic_title = item["topic"]
        audience = item.get("audience")
        LOGGER.info(f"\n=======================================================")
        LOGGER.info(f"[{idx}/{len(topics)}] Processing Topic: '{topic_title}'")
        LOGGER.info(f"=======================================================")

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

        # 2. TTS Voiceover Generation
        if generate_tts:
            LOGGER.info(f"Generating studio neural voiceover ({tts_voice})...")
            try:
                generate_script_voiceover(script_model, voice=tts_voice)
            except Exception as exc:
                LOGGER.warning(f"Voiceover generation failed ({exc})")

        # 3. Shorts & Reels Repurposing
        if generate_shorts:
            LOGGER.info("Generating 3 companion vertical Shorts scripts...")
            try:
                shorts = generate_shorts_from_topic_or_script(topic_title, script_model, gemini_model=model_name)
                save_shorts_outputs(shorts)
            except Exception as exc:
                LOGGER.warning(f"Shorts generation failed ({exc})")

        # 4. Thumbnail Prompts & Mockup Card
        if design_thumbnails:
            LOGGER.info("Generating AI thumbnail prompts & mockup graphic...")
            try:
                t_model = design_thumbnail_prompts(topic_title, gemini_model=model_name)
                if t_model.prompts:
                    mock_text = t_model.prompts[0].recommended_text_overlay
                    topic_slug = "".join(c if c.isalnum() else "_" for c in topic_title).strip("_")[:40]
                    mock_out = ensure_dir(get_project_root() / "output" / "thumbnails") / f"mockup_{topic_slug}.png"
                    render_thumbnail_mockup(text_overlay=mock_text, subtitle=topic_title, output_path=str(mock_out))
            except Exception as exc:
                LOGGER.warning(f"Thumbnail design failed ({exc})")

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
    parser.add_argument("--competitor_url", "-c", default=None, help="Competitor reference URL(s).")
    parser.add_argument("--competitor_urls", default=None, help="Comma-separated list of competitor URLs.")
    parser.add_argument("--channel", default=None, help="Crawl channel for viral outlier videos (@handle or ID).")
    parser.add_argument("--mine-comments", default=None, help="Mine viewer comment gaps for a video URL.")
    parser.add_argument("--output_dir", "-o", default=None, help="Directory to save generated scripts.")
    parser.add_argument("--model", "-m", default=None, help="Gemini model name.")
    parser.add_argument("--rate-limit-delay", type=float, default=2.0, help="Delay between API calls in seconds.")
    parser.add_argument("--no-subtitles", action="store_true", help="Disable automatic SRT/VTT subtitle export.")
    parser.add_argument("--generate-tts", action="store_true", help="Automatically generate neural TTS voiceover MP3.")
    parser.add_argument("--voice", default="vi-male", help="Voice shortcut or neural voice name.")
    parser.add_argument("--generate-shorts", action="store_true", help="Automatically generate 3 viral Shorts scripts.")
    parser.add_argument("--design-thumbnails", action="store_true", help="Generate AI thumbnail prompts and mockup.")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache for analysis.")
    parser.add_argument("--validate-keys", action="store_true", help="Run pre-flight API diagnostics.")
    args = parser.parse_args()

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
        if not args.channel and not args.mine_comments and not args.competitor_url:
            return

    # Channel Outliers Mode
    if args.channel:
        crawl_channel_outliers(args.channel)
        return

    # Comment Gap Mining Mode
    if args.mine_comments:
        mine_video_comments(args.mine_comments)
        return

    competitor_url_list = None
    if args.competitor_urls:
        competitor_url_list = [u.strip() for u in args.competitor_urls.split(",") if u.strip()]

    try:
        run_pipeline(
            topics_path=args.topics,
            style_template_path=args.style_template,
            competitor_url=args.competitor_url,
            competitor_urls=competitor_url_list,
            output_dir=args.output_dir,
            model_name=args.model,
            rate_limit_delay=args.rate_limit_delay,
            export_subtitles=not args.no_subtitles,
            generate_tts=args.generate_tts,
            generate_shorts=args.generate_shorts,
            design_thumbnails=args.design_thumbnails,
            force_refresh=args.force_refresh,
            tts_voice=args.voice,
        )
    except Exception as exc:
        LOGGER.error(f"Pipeline execution error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
