"""Main Pipeline Runner.

Orchestrates batch topic processing with competitor style templates, rate limiting, and script generation.

CLI Examples:
1. Validate API keys before running:
   python main.py --validate-keys

2. With pre-analyzed style template:
   python main.py --topics topics.csv --style_template cache/competitor/dQw4w9WgXcQ/style_template.json

3. Synthesize multiple competitor URLs on the fly:
   python main.py --topics topics.csv --competitor_urls "https://www.youtube.com/watch?v=VID1,https://www.youtube.com/watch?v=VID2"
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from competitor_analyzer import analyze_competitor_video, analyze_multiple_competitors
from script_generator import generate_script, save_script_outputs
from utils import RateLimiter, setup_logging, validate_api_keys

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
    force_refresh: bool = False,
) -> List[Path]:
    """Execute the end-to-end video production pipeline with rate limiting and retry resilience."""
    active_style_template = style_template_path

    # Step 1: Synthesize multiple competitor URLs if provided
    if competitor_urls:
        LOGGER.info(f"Synthesizing {len(competitor_urls)} competitor reference video(s)...")
        composite_path = analyze_multiple_competitors(
            urls_or_ids=competitor_urls,
            gemini_model=model_name,
            force_refresh=force_refresh,
        )
        active_style_template = str(composite_path)
    elif competitor_url:
        # Check if comma-separated
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

    # Step 3: Initialize Rate Limiter
    limiter = RateLimiter(min_interval_seconds=rate_limit_delay)

    # Step 4: Batch generate scripts
    generated_files: List[Path] = []
    for idx, item in enumerate(topics, 1):
        topic_title = item["topic"]
        audience = item.get("audience")
        LOGGER.info(f"\n[{idx}/{len(topics)}] Processing Topic: '{topic_title}'")

        # Rate throttle
        limiter.wait()

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

    LOGGER.info(f"\nPipeline successfully completed! Generated {len(generated_files)} script(s).")
    return generated_files


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube Video Script Pipeline with Competitor DNA Analysis.")
    parser.add_argument("--topics", "-t", default="topics.csv", help="Path to topics CSV file (default: topics.csv).")
    parser.add_argument(
        "--style_template",
        "-s",
        default=None,
        help="Path to style_template.json produced by competitor_analyzer.py.",
    )
    parser.add_argument(
        "--competitor_url",
        "-c",
        default=None,
        help="Single or comma-separated YouTube reference URLs.",
    )
    parser.add_argument(
        "--competitor_urls",
        default=None,
        help="Comma-separated list of competitor YouTube URLs to synthesize.",
    )
    parser.add_argument(
        "--output_dir",
        "-o",
        default=None,
        help="Directory to save generated scripts (default: output/).",
    )
    parser.add_argument("--model", "-m", default=None, help="Gemini model (default: GEMINI_MODEL or gemini-2.5-flash).")
    parser.add_argument("--rate-limit-delay", type=float, default=2.0, help="Delay in seconds between Gemini calls (default: 2.0s).")
    parser.add_argument("--no-subtitles", action="store_true", help="Disable automatic SRT/VTT subtitle export.")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache for competitor analysis.")
    parser.add_argument("--validate-keys", action="store_true", help="Run pre-flight check on configured API keys.")
    args = parser.parse_args()

    # Pre-flight API Key Validation
    if args.validate_keys:
        LOGGER.info("Running pre-flight API key diagnostics...")
        diag = validate_api_keys(model_name=args.model)
        print("\n--- API Key Diagnostic Results ---")
        print(f"Gemini API:   [{'OK' if diag['gemini']['valid'] else 'INFO'}] {diag['gemini']['message']}")
        print(f"YouTube API:  [{'OK' if diag['youtube']['valid'] else 'INFO'}] {diag['youtube']['message']}")
        print("----------------------------------\n")
        if not args.topics and not args.competitor_url and not args.style_template:
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
            force_refresh=args.force_refresh,
        )
    except Exception as exc:
        LOGGER.error(f"Pipeline error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
