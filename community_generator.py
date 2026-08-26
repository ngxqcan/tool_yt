"""YouTube Community Posts & Newsletter Generator Module.

Creates high-engagement YouTube Community Tab Polls, discussion questions,
and email newsletter summaries for multi-channel audience growth.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

from models import CommunityPostModel, parse_and_validate_json
from utils import ensure_dir, get_project_root, setup_logging

load_dotenv()
LOGGER = setup_logging("community_generator")


def generate_community_content(
    topic: str,
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
) -> CommunityPostModel:
    """Generate interactive YouTube Community Polls and newsletter digests."""
    raw_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    api_key = raw_api_key if raw_api_key and not raw_api_key.lower().startswith("your_") else None
    model_name = gemini_model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    prompt = f"""You are a community manager for a top-tier YouTube channel.
Generate high-engagement audience content for this video topic:

TOPIC: {topic}

Deliver:
1. An interactive YouTube Community Poll with 4 clickable options.
2. A compelling discussion text post for the YouTube Community tab asking for opinions.
3. A concise 3-paragraph email newsletter summary highlighting the core takeaways.

Return valid JSON matching this schema:
{{
  "topic": "{topic}",
  "poll_question": "string question",
  "poll_options": ["Option A", "Option B", "Option C", "Option D"],
  "engagement_post_text": "string text post with emojis",
  "newsletter_summary": "3-paragraph email digest"
}}
"""

    if api_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            )
            model = parse_and_validate_json(response.text or "", CommunityPostModel)
            LOGGER.info(f"Generated community content for topic: '{topic}'")
            return model
        except Exception as exc:
            LOGGER.warning(f"Gemini community generation failed ({exc}). Using fallback.")

    return CommunityPostModel(
        topic=topic,
        poll_question=f"When it comes to {topic}, what is your #1 biggest challenge right now?",
        poll_options=[
            "Getting started & setup",
            "Scaling and maintenance",
            "High costs & pricing",
            "Security & reliability",
        ],
        engagement_post_text=(
            f"🚨 New breakdown dropping soon on {topic}!\n\n"
            "We've been testing this extensively over the past month and the results were unexpected. "
            "Drop your questions below and we'll answer the top ones in the video comments!"
        ),
        newsletter_summary=(
            f"Hey everyone,\n\nIn this week's edition, we take a deep dive into {topic}. "
            "Rather than chasing surface-level hype, we unpack the exact architectural shifts and practical steps required for real results in 2026.\n\n"
            "Key Takeaway: Simplicity and robust automation always beat bloated tools. Make sure to check out our latest breakdown on YouTube!"
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate YouTube community polls and newsletter posts.")
    parser.add_argument("--topic", "-t", required=True, help="Topic name.")
    args = parser.parse_args()

    try:
        content = generate_community_content(args.topic)
        print("\n================ YOUTUBE COMMUNITY TAB POST ================")
        print(f"📊 Poll Question: {content.poll_question}")
        for opt in content.poll_options:
            print(f"  [ ] {opt}")
        print(f"\n💬 Discussion Post:\n{content.engagement_post_text}")
        print(f"\n📧 Newsletter Digest:\n{content.newsletter_summary}")
        print("============================================================\n")
    except Exception as exc:
        LOGGER.error(f"Community post generation failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
