"""Main Pipeline Runner.

Orchestrates batch topic processing with competitor style templates and script generation.

CLI Examples:
1. With pre-analyzed style template:
   python main.py --topics topics.csv --style_template cache/competitor/dQw4w9WgXcQ/style_template.json

2. Directly with competitor URL (runs analyzer first, then generates scripts):
   python main.py --topics topics.csv --competitor_url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import List, Dict, Optional

from competitor_analyzer import analyze_competitor_video
from script_generator import generate_script, save_script_outputs

LOGGER = logging.getLogger("main_pipeline")
LOGGER.setLevel(logging.INFO)
if not LOGGER.handlers:
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    LOGGER.addHandler(ch)


def parse_topics_csv(csv_path: str) -> List[Dict[str, str]]:
    """Parse topics CSV file into a list of topic dictionaries."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Topics CSV file not found at: {csv_path}")

    topics: List[Dict[str, str]] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = [fn.strip().lower() for fn in (reader.fieldnames or [])]
        
        # If headers exist and contain 'topic'
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
            # Fallback to simple line-by-line reading if no header
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
    output_dir: Optional[str] = None,
) -> List[Path]:
    """Execute the end-to-end video production pipeline."""
    # Step 1: Handle competitor video analysis if URL is provided
    active_style_template = style_template_path

    if competitor_url:
        LOGGER.info(f"Analyzing competitor URL: {competitor_url}")
        active_style_template = analyze_competitor_video(url_or_id=competitor_url)
        LOGGER.info(f"Using newly generated style template: {active_style_template}")

    # Step 2: Load topics
    topics = parse_topics_csv(topics_path)
    if not topics:
        LOGGER.warning("No topics found in CSV file.")
        return []

    # Step 3: Generate scripts for each topic
    generated_files: List[Path] = []
    for idx, item in enumerate(topics, 1):
        topic_title = item["topic"]
        audience = item.get("audience")
        LOGGER.info(f"\n[{idx}/{len(topics)}] Generating original script for: '{topic_title}'")

        script_data = generate_script(
            topic=topic_title,
            target_audience=audience,
            style_template_source=active_style_template,
        )

        custom_output = None
        if output_dir:
            topic_slug = "".join(c if c.isalnum() else "_" for c in topic_title).strip("_")[:50]
            custom_output = str(Path(output_dir) / f"script_{topic_slug}.json")

        saved_path = save_script_outputs(script_data, output_path=custom_output)
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
        help="YouTube URL of a competitor reference video to analyze on the fly.",
    )
    parser.add_argument(
        "--output_dir",
        "-o",
        default=None,
        help="Directory to save generated scripts (default: output/).",
    )
    args = parser.parse_args()

    try:
        run_pipeline(
            topics_path=args.topics,
            style_template_path=args.style_template,
            competitor_url=args.competitor_url,
            output_dir=args.output_dir,
        )
    except Exception as exc:
        LOGGER.error(f"Pipeline error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
