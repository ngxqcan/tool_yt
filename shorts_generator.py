"""YouTube Shorts, TikTok & Reels Repurposing Module.

Automatically derives 3 high-impact vertical short-form scripts (<60s) from a long-form topic or script.
Includes on-screen caption cues, fast-cut visual actions, and companion vertical 9:16 subtitles.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from models import (
    GeneratedScriptModel,
    ShortsBeatModel,
    ShortsCollectionModel,
    ShortsScriptModel,
    parse_and_validate_json,
)
from utils import ensure_dir, format_seconds_to_srt_time, get_project_root, setup_logging

load_dotenv()
LOGGER = setup_logging("shorts_generator")


def generate_shorts_from_topic_or_script(
    topic: str,
    long_script: Optional[GeneratedScriptModel | Dict[str, Any]] = None,
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
) -> ShortsCollectionModel:
    """Generate 3 viral YouTube Shorts / TikTok / Reels scripts (<60s) derived from the main content."""
    raw_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    api_key = raw_api_key if raw_api_key and not raw_api_key.lower().startswith("your_") else None
    model_name = gemini_model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    long_script_context = ""
    if long_script:
        if isinstance(long_script, dict):
            long_script_context = f"\nLong Script Summary:\n- Hook: {long_script.get('hook', {}).get('spoken_dialogue', '')}\n- Sections: {len(long_script.get('sections', []))} beats"
        else:
            long_script_context = f"\nLong Script Summary:\n- Hook: {long_script.hook.spoken_dialogue}\n- Sections: {len(long_script.sections)} beats"

    prompt = f"""You are a master short-form viral video creator (YouTube Shorts, TikTok, Reels).
Generate 3 distinct, high-retention vertical short-form video scripts (each 30-50 seconds) on this topic:

TOPIC: {topic}
{long_script_context}

RULES FOR SHORTS RETENTION:
1. First 3 seconds MUST have a pattern interrupt hook with bold on-screen text.
2. Fast delivery pacing (150-170 words per minute).
3. Clear 3-step or 3-point rapid insight.
4. Closing CTA driving viewers to subscribe or watch the full video breakdown.

Return valid JSON matching this schema:
{{
  "parent_topic": "{topic}",
  "shorts": [
    {{
      "shorts_id": 1,
      "title": "Shorts Title Option 1 (Punchy & Viral)",
      "target_duration_seconds": 45,
      "hook": "Opening 3-second spoken sentence...",
      "beats": [
        {{
          "duration_seconds": 12,
          "spoken_dialogue": "Point 1 rapid explanation...",
          "on_screen_text": "KEYWORD 1",
          "visual_action": "Zoom in on host / dynamic text overlay"
        }},
        {{
          "duration_seconds": 12,
          "spoken_dialogue": "Point 2 rapid explanation...",
          "on_screen_text": "KEYWORD 2",
          "visual_action": "B-roll cut / graphic pop"
        }},
        {{
          "duration_seconds": 10,
          "spoken_dialogue": "Point 3 rapid explanation...",
          "on_screen_text": "KEYWORD 3",
          "visual_action": "Screen split comparison"
        }}
      ],
      "call_to_action": "Subscribe for more or watch the full breakdown on my channel!",
      "hashtags": ["#shorts", "#tech", "#viral"]
    }}
  ]
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
            model = parse_and_validate_json(response.text or "", ShortsCollectionModel)
            model.generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            LOGGER.info(f"Generated {len(model.shorts)} YouTube Shorts for topic: '{topic}'")
            return model
        except Exception as exc:
            LOGGER.warning(f"Gemini Shorts generation failed ({exc}). Using fallback engine.")

    # Fallback
    return _fallback_shorts_collection(topic)


def _fallback_shorts_collection(topic: str) -> ShortsCollectionModel:
    return ShortsCollectionModel(
        parent_topic=topic,
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        shorts=[
            ShortsScriptModel(
                shorts_id=1,
                title=f"The 1 Big Mistake Everyone Makes With {topic}",
                target_duration_seconds=40,
                hook=f"Stop doing {topic} the old way — you're wasting 80% of your time.",
                beats=[
                    ShortsBeatModel(
                        duration_seconds=10,
                        spoken_dialogue="Most people think you need complex tools, but the real secret is foundational workflow.",
                        on_screen_text="THE TRAP ❌",
                        visual_action="Host close-up with red X graphics",
                    ),
                    ShortsBeatModel(
                        duration_seconds=12,
                        spoken_dialogue="Instead, switch to automated async systems that cut your overhead in half.",
                        on_screen_text="THE FIX ⚡",
                        visual_action="Screen recording diagram transition",
                    ),
                    ShortsBeatModel(
                        duration_seconds=10,
                        spoken_dialogue="Try this formula for 7 days and watch your results multiply.",
                        on_screen_text="PROVEN FORMULA 🚀",
                        visual_action="Speed ramp text animation",
                    ),
                ],
                call_to_action="Watch the full breakdown on my channel for step-by-step code!",
                hashtags=["#shorts", "#productivity", "#tech2026"],
            ),
            ShortsScriptModel(
                shorts_id=2,
                title=f"3 Mindblowing Facts About {topic} You Didn't Know",
                target_duration_seconds=45,
                hook=f"Here are 3 crazy things happening right now with {topic}.",
                beats=[
                    ShortsBeatModel(
                        duration_seconds=12,
                        spoken_dialogue="Number 1: Over 70% of companies are adopting this silently.",
                        on_screen_text="FACT #1 📈",
                        visual_action="Stat chart graphic pop-up",
                    ),
                    ShortsBeatModel(
                        duration_seconds=12,
                        spoken_dialogue="Number 2: It eliminates the biggest security bottleneck in modern tech.",
                        on_screen_text="FACT #2 🔒",
                        visual_action="Lock animation with green checkmark",
                    ),
                    ShortsBeatModel(
                        duration_seconds=10,
                        spoken_dialogue="Number 3: It takes less than 15 minutes to configure if you know the framework.",
                        on_screen_text="FACT #3 ⏱️",
                        visual_action="Timer countdown graphic",
                    ),
                ],
                call_to_action="Drop your thoughts in the comments and hit subscribe!",
                hashtags=["#shorts", "#facts", "#tech"],
            ),
        ],
    )


def save_shorts_outputs(collection: ShortsCollectionModel, output_dir: Optional[str] = None) -> Path:
    """Save Shorts scripts as JSON, Markdown, and individual .srt subtitle files."""
    slug = "".join(c if c.isalnum() else "_" for c in collection.parent_topic).strip("_")[:40]
    out_dir = ensure_dir(Path(output_dir) if output_dir else get_project_root() / "output" / "shorts")
    json_path = out_dir / f"shorts_{slug}.json"
    md_path = out_dir / f"shorts_{slug}.md"

    # Save JSON
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(collection.model_dump_json(indent=2))

    # Save Markdown and individual SRTs
    md_lines = [f"# YouTube Shorts & Reels Collection: {collection.parent_topic}\n"]
    for s in collection.shorts:
        md_lines.extend([
            f"## 📱 Shorts #{s.shorts_id}: {s.title}",
            f"**Target Runtime:** ~{s.target_duration_seconds}s",
            f"**Hook (0-3s):**\n> {s.hook}\n",
            "**Beats & On-Screen Visuals:**",
        ])
        for b in s.beats:
            md_lines.append(f"- **[{b.on_screen_text}]** *(Visual: {b.visual_action})*\n  > \"{b.spoken_dialogue}\"")
        md_lines.extend([
            f"\n**Call to Action:** {s.call_to_action}",
            f"**Hashtags:** {' '.join(s.hashtags)}\n",
            "---\n",
        ])

        # Generate individual Shorts SRT
        srt_lines = []
        curr = 0.0
        # Hook
        srt_lines.append("1\n00:00:00,000 --> 00:00:03,000\n" + s.hook + "\n")
        curr += 3.0
        for b_idx, b in enumerate(s.beats, 2):
            end = curr + b.duration_seconds
            srt_lines.append(f"{b_idx}\n{format_seconds_to_srt_time(curr)} --> {format_seconds_to_srt_time(end)}\n{b.spoken_dialogue}\n")
            curr = end
        # CTA
        srt_lines.append(f"{len(s.beats)+2}\n{format_seconds_to_srt_time(curr)} --> {format_seconds_to_srt_time(curr+4.0)}\n{s.call_to_action}\n")

        srt_file = out_dir / f"shorts_{slug}_{s.shorts_id}.srt"
        with open(srt_file, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_lines))

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    LOGGER.info(f"Saved Shorts package: {json_path} and {md_path}")
    return json_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate viral YouTube Shorts & Reels derived from topic.")
    parser.add_argument("--topic", "-t", required=True, help="Video topic.")
    args = parser.parse_args()

    try:
        shorts = generate_shorts_from_topic_or_script(args.topic)
        out = save_shorts_outputs(shorts)
        print(f"\nSuccessfully generated {len(shorts.shorts)} Shorts at: {out}")
    except Exception as exc:
        LOGGER.error(f"Shorts generation failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
