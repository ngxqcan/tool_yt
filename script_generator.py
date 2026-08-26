"""Script Generator Module.

Generates 100% original YouTube video scripts based on a given topic and optional
structural style template from competitor_analyzer.

Strict Guardrail:
When a style template is provided, the generator follows only its structural/pacing
blueprint (hook mechanism, beat count, tone, title formula, ending CTA).
It is strictly instructed never to copy or paraphrase competitor dialogue or storylines.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

LOGGER = logging.getLogger("script_generator")
LOGGER.setLevel(logging.INFO)
if not LOGGER.handlers:
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    LOGGER.addHandler(ch)


def get_project_root() -> Path:
    """Return the absolute path to the project root."""
    return Path(__file__).resolve().parent


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_style_template(template_path_or_dict: Any) -> Optional[Dict[str, Any]]:
    """Load and validate style template from file path or dictionary."""
    if not template_path_or_dict:
        return None

    if isinstance(template_path_or_dict, dict):
        return template_path_or_dict

    template_file = Path(template_path_or_dict)
    if not template_file.exists():
        LOGGER.warning(f"Style template file not found at: {template_path_or_dict}")
        return None

    try:
        with open(template_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as exc:
        LOGGER.warning(f"Could not load style template JSON ({exc})")
        return None


def generate_script(
    topic: str,
    target_audience: Optional[str] = None,
    style_template_source: Optional[Any] = None,
    gemini_api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    """Generate an original video script for a topic using Gemini.

    Injects the style template and strict anti-plagiarism guardrail when provided.
    """
    style_template = load_style_template(style_template_source)
    api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    audience_str = target_audience or "General interested audience looking for actionable, clear insights"

    system_instruction = (
        "You are an elite YouTube scriptwriter and content strategist. "
        "You produce highly engaging, professional, and retention-optimized video scripts. "
        "Every script must be 100% original, creative, factually sound, and formatted clearly with "
        "spoken voiceover lines and concrete visual/B-roll instructions."
    )

    if style_template:
        title_hints = style_template.get("title_thumbnail_pattern", {})
        title_hint_text = (
            f"- Title Formula: {style_template.get('title_formula', 'Engaging headline')}\n"
            f"- Title Casing Style: {title_hints.get('capitalization_style', 'Title Case')}\n"
            f"- Target Title Length: ~{title_hints.get('title_length_chars', 50)} chars\n"
            f"- Include Numbers/Brackets: Numbers={title_hints.get('has_numbers', False)}, Brackets={title_hints.get('has_brackets', False)}"
        )

        template_guidelines = f"""
================================================================================
CRITICAL GUARDRAIL & ETHICAL GUIDELINES:
Write a completely original script on the topic: {topic}.
Follow this structural pattern (hook style, pacing, tone, number of sections, ending style)
extracted from a reference video, but do NOT reuse any specific facts, phrases, stories,
or wording from that reference — this is a format guide only, the content must be 100%
original and independently researched/written.
================================================================================

STRUCTURAL BLUEPRINT TO MATCH:
- Tone: {style_template.get('tone', 'Educational and engaging')}
- Hook Style: {style_template.get('hook_style', 'High-impact opening challenge')}
- Number of Main Beats/Sections: {style_template.get('section_count', 4)}
- Pacing & Beat Descriptions:
{json.dumps(style_template.get('section_pacing', []), indent=2)}
- Average Section Length: ~{style_template.get('avg_section_length_seconds', 90)} seconds
- Ending Style / CTA: {style_template.get('ending_style', 'Actionable takeaway & subscribe CTA')}
- Estimated Video Duration: ~{style_template.get('estimated_total_length_seconds', 480)} seconds

TITLE & PACKAGING PATTERN HINTS:
{title_hint_text}
"""
    else:
        template_guidelines = f"""
Standard YouTube Scripting Blueprint:
- Write an engaging, high-retention script on the topic: {topic}.
- Target 4-5 structured sections with strong hook, visual B-roll notes, and clear CTA.
"""

    prompt = f"""Write a full YouTube video production script.

TOPIC: {topic}
TARGET AUDIENCE: {audience_str}

{template_guidelines}

Return a valid JSON object matching this structure:
{{
  "topic": "{topic}",
  "suggested_titles": [
    "Title Option 1 (following the title formula)",
    "Title Option 2",
    "Title Option 3"
  ],
  "estimated_duration_seconds": <integer>,
  "target_tone": "string describing tone",
  "hook": {{
    "duration_seconds": <integer, e.g. 20>,
    "spoken_dialogue": "Exact voiceover / spoken text for the opening hook...",
    "visual_b_roll_instructions": "On-screen visuals, sound effects, text pop-ups..."
  }},
  "sections": [
    {{
      "section_number": 1,
      "title": "Section Title / Beat Name",
      "duration_seconds": <integer>,
      "spoken_dialogue": "Detailed voiceover script for this section...",
      "visual_b_roll_instructions": "Visual directions, motion graphics, screen recordings..."
    }}
  ],
  "call_to_action_and_outro": {{
    "duration_seconds": <integer>,
    "spoken_dialogue": "Closing words and CTA...",
    "visual_b_roll_instructions": "End screen layout, cards, B-roll..."
  }},
  "seo_tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "description_blueprint": "2-3 paragraph YouTube video description ready for upload."
}}
"""

    script_result: Dict[str, Any] = {}

    if api_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            )
            raw_text = response.text.strip()
            script_result = json.loads(raw_text)
            LOGGER.info(f"Generated original script for topic '{topic}' via Gemini API.")
        except Exception as exc:
            LOGGER.warning(f"Gemini API call failed ({exc}). Falling back to algorithmic script generator.")
            script_result = _fallback_script_generation(topic, audience_str, style_template)
    else:
        LOGGER.info("No GEMINI_API_KEY provided. Generating script using fallback template engine.")
        script_result = _fallback_script_generation(topic, audience_str, style_template)

    # Attach generation metadata
    script_result["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    script_result["style_template_applied"] = bool(style_template)
    if style_template:
        script_result["template_source_video_id"] = style_template.get("source_video_id", "external")

    return script_result


def _fallback_script_generation(
    topic: str,
    audience: str,
    style_template: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Generates structured fallback script when API key is unavailable."""
    section_count = style_template.get("section_count", 4) if style_template else 4
    avg_sec = style_template.get("avg_section_length_seconds", 90) if style_template else 90
    tone = style_template.get("tone", "Authoritative, educational, and engaging") if style_template else "Educational and engaging"
    formula = style_template.get("title_formula", "[Topic]: The Complete Masterclass") if style_template else "How To Master [Topic]"
    hook_style = style_template.get("hook_style", "High-energy dilemma hook") if style_template else "High-energy hook"

    titles = [
        f"{topic}: The Definitive Breakdown for 2026",
        f"Why Everything You Knew About {topic} Is Changing",
        f"5 Proven Rules to Master {topic} (Step-by-Step)",
    ]

    sections = []
    beat_names = [
        "The Core Problem & Context",
        "The Breakthrough Mechanism",
        "Step-by-Step Implementation",
        "Common Pitfalls & Pro Fixes",
        "Future Outlook & Advanced Tips",
    ]

    for i in range(min(section_count, len(beat_names))):
        sections.append({
            "section_number": i + 1,
            "title": f"Beat {i+1}: {beat_names[i]}",
            "duration_seconds": avg_sec,
            "spoken_dialogue": (
                f"In this section we dive deep into {beat_names[i].lower()} regarding {topic}. "
                f"Understanding this foundational aspect gives {audience.lower()} the exact edge needed to execute effectively."
            ),
            "visual_b_roll_instructions": (
                f"Cut to clean animated diagram highlighting {topic} key points. "
                "Add subtle kinetic typography for emphasis."
            ),
        })

    return {
        "topic": topic,
        "suggested_titles": titles,
        "estimated_duration_seconds": (section_count * avg_sec) + 45,
        "target_tone": tone,
        "hook": {
            "duration_seconds": 25,
            "spoken_dialogue": (
                f"If you've been trying to navigate {topic}, you've likely hit the same roadblock almost everyone faces. "
                f"In this video, we break down the exact formula to solve it — no fluff, just actionable steps."
            ),
            "visual_b_roll_instructions": (
                f"Cold open: Fast kinetic text montage outlining {topic} challenges. "
                "Glitch sound effect transitions into host on-camera."
            ),
        },
        "sections": sections,
        "call_to_action_and_outro": {
            "duration_seconds": 20,
            "spoken_dialogue": (
                f"Which part of {topic} are you going to implement first? Let me know in the comments below, "
                "and hit subscribe for the next breakdown."
            ),
            "visual_b_roll_instructions": "Host wrap-up with animated subscribe button and related video end-screen cards.",
        },
        "seo_tags": [topic.lower(), f"{topic.lower()} tutorial", f"{topic.lower()} 2026", "strategy", "guide"],
        "description_blueprint": (
            f"Everything you need to know about {topic}. "
            f"We explore the proven strategies, common pitfalls, and exact steps to master this in 2026.\n\n"
            "Timestamps:\n0:00 - Introduction & Hook\n"
            + "\n".join([f"{(i*avg_sec + 25)//60:02d}:{(i*avg_sec + 25)%60:02d} - {s['title']}" for i, s in enumerate(sections)])
            + "\n\nSubscribe for more high-impact breakdowns!"
        ),
    }


def save_script_outputs(script_data: Dict[str, Any], output_path: Optional[str] = None) -> Path:
    """Save generated script as both JSON and readable Markdown."""
    topic_slug = "".join(c if c.isalnum() else "_" for c in script_data.get("topic", "untitled")).strip("_")[:50]
    output_dir = ensure_dir(get_project_root() / "output")

    if output_path:
        target_file = Path(output_path).resolve()
        ensure_dir(target_file.parent)
    else:
        target_file = output_dir / f"script_{topic_slug}.json"

    # Write JSON
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=2, ensure_ascii=False)

    # Write companion Markdown
    md_file = target_file.with_suffix(".md")
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(format_script_as_markdown(script_data))

    LOGGER.info(f"Saved script JSON: {target_file}")
    LOGGER.info(f"Saved script Markdown: {md_file}")
    return target_file


def format_script_as_markdown(script: Dict[str, Any]) -> str:
    """Render script dictionary into a readable Markdown document."""
    lines = [
        f"# Video Script: {script.get('topic')}",
        f"\n**Generated At:** {script.get('generated_at', 'N/A')}",
        f"**Estimated Total Duration:** ~{script.get('estimated_duration_seconds', 0)} seconds",
        f"**Tone:** {script.get('target_tone', 'N/A')}",
        f"**Style Template Applied:** {script.get('style_template_applied', False)}",
        "\n## 🎯 Suggested Titles",
    ]

    for title in script.get("suggested_titles", []):
        lines.append(f"- {title}")

    hook = script.get("hook", {})
    lines.extend([
        f"\n## 🎣 Hook ({hook.get('duration_seconds', 0)}s)",
        f"**Spoken Dialogue:**\n> {hook.get('spoken_dialogue', '')}\n",
        f"**Visual & B-Roll:**\n*{hook.get('visual_b_roll_instructions', '')}*",
        "\n## 🎬 Main Sections",
    ])

    for sec in script.get("sections", []):
        lines.extend([
            f"\n### {sec.get('title', f'Section {sec.get('section_number')}')} (~{sec.get('duration_seconds', 0)}s)",
            f"**Spoken Dialogue:**\n> {sec.get('spoken_dialogue', '')}\n",
            f"**Visual & B-Roll:**\n*{sec.get('visual_b_roll_instructions', '')}*",
        ])

    outro = script.get("call_to_action_and_outro", {})
    lines.extend([
        f"\n## 📣 Call to Action & Outro ({outro.get('duration_seconds', 0)}s)",
        f"**Spoken Dialogue:**\n> {outro.get('spoken_dialogue', '')}\n",
        f"**Visual & B-Roll:**\n*{outro.get('visual_b_roll_instructions', '')}*",
        "\n## 🏷️ SEO & Description Blueprint",
        f"**Tags:** {', '.join(script.get('seo_tags', []))}\n",
        "**Description:**",
        "```",
        script.get("description_blueprint", ""),
        "```",
    ])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate original YouTube scripts using style templates.")
    parser.add_argument("--topic", "-t", required=True, help="Video topic / premise.")
    parser.add_argument("--audience", "-a", default=None, help="Target audience.")
    parser.add_argument(
        "--style_template",
        "-s",
        default=None,
        help="Path to style_template.json produced by competitor_analyzer.",
    )
    parser.add_argument("--output", "-o", default=None, help="Custom output JSON path.")
    args = parser.parse_args()

    try:
        script = generate_script(
            topic=args.topic,
            target_audience=args.audience,
            style_template_source=args.style_template,
        )
        out_path = save_script_outputs(script, args.output)
        print(f"Script successfully generated at: {out_path}")
    except Exception as exc:
        LOGGER.error(f"Script generation failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
