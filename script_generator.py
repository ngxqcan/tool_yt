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
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from models import (
    GeneratedScriptModel,
    HookModel,
    OutroModel,
    SectionBeatModel,
    StyleTemplateModel,
    parse_and_validate_json,
)
from utils import (
    ensure_dir,
    generate_subtitles,
    get_cache_dir,
    get_output_dir,
    get_project_root,
    retry_with_backoff,
    setup_logging,
)

load_dotenv()

LOGGER = setup_logging("script_generator")


def load_style_template(template_path_or_dict: Any) -> Optional[StyleTemplateModel]:
    """Load and validate style template from file path or dictionary."""
    if not template_path_or_dict:
        return None

    if isinstance(template_path_or_dict, StyleTemplateModel):
        return template_path_or_dict

    if isinstance(template_path_or_dict, dict):
        try:
            return StyleTemplateModel.model_validate(template_path_or_dict)
        except Exception as exc:
            LOGGER.warning(f"Failed to validate style template dict ({exc})")
            return None

    template_file = Path(template_path_or_dict)
    if not template_file.exists():
        LOGGER.warning(f"Style template file not found at: {template_path_or_dict}")
        return None

    try:
        with open(template_file, "r", encoding="utf-8") as f:
            raw_text = f.read()
        return parse_and_validate_json(raw_text, StyleTemplateModel)
    except Exception as exc:
        LOGGER.warning(f"Could not load/validate style template JSON ({exc})")
        return None


@retry_with_backoff(max_retries=3, initial_delay=2.0)
def _call_gemini_for_script(client: Any, model_name: str, prompt: str, system_instruction: str) -> str:
    """Execute Gemini script generation with retry backoff."""
    from google.genai import types
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )
    return response.text or ""


def load_comment_gaps(gaps_path_or_dict: Any) -> Optional[Dict[str, Any]]:
    """Load and validate comment gaps from file path or dictionary."""
    if not gaps_path_or_dict:
        return None
    if isinstance(gaps_path_or_dict, dict):
        return gaps_path_or_dict
    path = Path(gaps_path_or_dict)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def generate_script(
    topic: str,
    target_audience: Optional[str] = None,
    style_template_source: Optional[Any] = None,
    comment_gaps_source: Optional[Any] = None,
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
) -> GeneratedScriptModel:
    """Generate an original video script for a topic using Gemini.

    Injects the style template and strict anti-plagiarism guardrail when provided.
    """
    style_template = load_style_template(style_template_source)
    comment_gaps = load_comment_gaps(comment_gaps_source)
    raw_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    api_key = raw_api_key if raw_api_key and not raw_api_key.lower().startswith("your_") else None
    model_name = gemini_model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    audience_str = target_audience or "General interested audience looking for actionable, clear insights"

    system_instruction = (
        "You are an elite YouTube scriptwriter and content strategist. "
        "You produce highly engaging, professional, and retention-optimized video scripts. "
        "Every script must be 100% original, creative, factually sound, and formatted clearly with "
        "spoken voiceover lines and concrete visual/B-roll instructions."
    )

    gaps_instruction = ""
    if comment_gaps:
        gaps_list = comment_gaps.get("content_gaps", [])
        gaps_text = "\n".join([f"- Gap: {g.get('question_or_critique')} -> Action: {g.get('suggested_script_angle')}" for g in gaps_list])
        pts_text = "\n".join([f"- {p}" for p in comment_gaps.get("recommended_talking_points", [])])
        gaps_instruction = f"""
AUDIENCE CONTENT GAPS (Competitor missed these — ensure our video provides 10x more value by covering them):
{gaps_text}

Recommended Value Talking Points:
{pts_text}
"""

    if style_template:
        title_hints = style_template.title_thumbnail_pattern
        title_hint_text = (
            f"- Title Formula: {style_template.title_formula}\n"
            f"- Title Casing Style: {title_hints.capitalization_style}\n"
            f"- Target Title Length: ~{title_hints.title_length_chars} chars\n"
            f"- Include Numbers/Brackets: Numbers={title_hints.has_numbers}, Brackets={title_hints.has_brackets}"
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
- Tone: {style_template.tone}
- Hook Style: {style_template.hook_style}
- Number of Main Beats/Sections: {style_template.section_count}
- Pacing & Beat Descriptions:
{json.dumps(style_template.section_pacing, indent=2)}
- Average Section Length: ~{style_template.avg_section_length_seconds} seconds
- Ending Style / CTA: {style_template.ending_style}
- Estimated Video Duration: ~{style_template.estimated_total_length_seconds} seconds

TITLE & PACKAGING PATTERN HINTS:
{title_hint_text}
{gaps_instruction}
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

Return a valid JSON object matching this schema:
{{
  "topic": "{topic}",
  "suggested_titles": [
    "Title Option 1",
    "Title Option 2",
    "Title Option 3"
  ],
  "estimated_duration_seconds": <int>,
  "target_tone": "string",
  "hook": {{
    "duration_seconds": <int>,
    "spoken_dialogue": "Exact voiceover / spoken text for opening hook...",
    "visual_b_roll_instructions": "On-screen visuals, sound effects, text pop-ups..."
  }},
  "sections": [
    {{
      "section_number": 1,
      "title": "Section Title / Beat Name",
      "duration_seconds": <int>,
      "spoken_dialogue": "Detailed voiceover script...",
      "visual_b_roll_instructions": "Visual directions, motion graphics..."
    }}
  ],
  "call_to_action_and_outro": {{
    "duration_seconds": <int>,
    "spoken_dialogue": "Closing words and CTA...",
    "visual_b_roll_instructions": "End screen layout..."
  }},
  "seo_tags": ["tag1", "tag2", "tag3"],
  "description_blueprint": "2-3 paragraph YouTube video description ready for upload."
}}
"""

    script_model: Optional[GeneratedScriptModel] = None

    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            raw_text = _call_gemini_for_script(client, model_name, prompt, system_instruction)
            script_model = parse_and_validate_json(raw_text, GeneratedScriptModel)
            LOGGER.info(f"Generated original script for topic '{topic}' via Gemini API ({model_name}).")
        except Exception as exc:
            LOGGER.warning(f"Gemini API / parsing failed ({exc}). Falling back to fallback script engine.")

    if script_model is None:
        LOGGER.info(f"Using fallback script engine for topic: '{topic}'")
        script_model = _fallback_script_generation(topic, audience_str, style_template)

    script_model.generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    script_model.style_template_applied = bool(style_template)
    if style_template and style_template.source_video_id:
        script_model.template_source_video_id = style_template.source_video_id

    return script_model


def _fallback_script_generation(
    topic: str,
    audience: str,
    style_template: Optional[StyleTemplateModel],
) -> GeneratedScriptModel:
    """Generates structured fallback script when API key is unavailable."""
    section_count = style_template.section_count if style_template else 4
    avg_sec = style_template.avg_section_length_seconds if style_template else 90
    tone = style_template.tone if style_template else "Educational and engaging"

    titles = [
        f"{topic}: The Definitive Breakdown for 2026",
        f"Why Everything You Knew About {topic} Is Changing",
        f"5 Proven Rules to Master {topic} (Step-by-Step)",
    ]

    beat_names = [
        "The Core Problem & Context",
        "The Breakthrough Mechanism",
        "Step-by-Step Implementation",
        "Common Pitfalls & Pro Fixes",
        "Future Outlook & Advanced Tips",
    ]

    sections: List[SectionBeatModel] = []
    for i in range(min(section_count, len(beat_names))):
        sections.append(SectionBeatModel(
            section_number=i + 1,
            title=f"Beat {i+1}: {beat_names[i]}",
            duration_seconds=avg_sec,
            spoken_dialogue=(
                f"In this section we dive deep into {beat_names[i].lower()} regarding {topic}. "
                f"Understanding this foundational aspect gives {audience.lower()} the exact edge needed to execute effectively."
            ),
            visual_b_roll_instructions=(
                f"Cut to clean animated diagram highlighting {topic} key points. "
                "Add subtle kinetic typography for emphasis."
            ),
        ))

    return GeneratedScriptModel(
        topic=topic,
        suggested_titles=titles,
        estimated_duration_seconds=(section_count * avg_sec) + 45,
        target_tone=tone,
        hook=HookModel(
            duration_seconds=25,
            spoken_dialogue=(
                f"If you've been trying to navigate {topic}, you've likely hit the same roadblock almost everyone faces. "
                f"In this video, we break down the exact formula to solve it — no fluff, just actionable steps."
            ),
            visual_b_roll_instructions=(
                f"Cold open: Fast kinetic text montage outlining {topic} challenges. "
                "Glitch sound effect transitions into host on-camera."
            ),
        ),
        sections=sections,
        call_to_action_and_outro=OutroModel(
            duration_seconds=20,
            spoken_dialogue=(
                f"Which part of {topic} are you going to implement first? Let me know in the comments below, "
                "and hit subscribe for the next breakdown."
            ),
            visual_b_roll_instructions="Host wrap-up with animated subscribe button and related video end-screen cards.",
        ),
        seo_tags=[topic.lower(), f"{topic.lower()} tutorial", f"{topic.lower()} 2026", "strategy", "guide"],
        description_blueprint=(
            f"Everything you need to know about {topic}. "
            f"We explore the proven strategies, common pitfalls, and exact steps to master this in 2026.\n\n"
            "Timestamps:\n0:00 - Introduction & Hook\n"
            + "\n".join([f"{(i*avg_sec + 25)//60:02d}:{(i*avg_sec + 25)%60:02d} - {s.title}" for i, s in enumerate(sections)])
            + "\n\nSubscribe for more high-impact breakdowns!"
        ),
    )


def save_script_outputs(
    script_data: GeneratedScriptModel | Dict[str, Any],
    output_path: Optional[str] = None,
    export_subtitles: bool = True,
) -> Path:
    """Save generated script as JSON, Markdown, and optional SRT/VTT subtitle files."""
    if isinstance(script_data, dict):
        model = GeneratedScriptModel.model_validate(script_data)
    else:
        model = script_data

    topic_slug = "".join(c if c.isalnum() else "_" for c in model.topic).strip("_")[:50]
    output_dir = ensure_dir(get_output_dir())

    if output_path:
        target_file = Path(output_path).resolve()
        ensure_dir(target_file.parent)
    else:
        target_file = output_dir / f"script_{topic_slug}.json"

    # Write JSON
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(model.model_dump_json(indent=2))

    # Write Markdown
    md_file = target_file.with_suffix(".md")
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(format_script_as_markdown(model))

    # Write SRT & VTT Subtitles
    if export_subtitles:
        srt_content, vtt_content = generate_subtitles(model.model_dump())
        srt_file = target_file.with_suffix(".srt")
        vtt_file = target_file.with_suffix(".vtt")

        with open(srt_file, "w", encoding="utf-8") as f:
            f.write(srt_content)
        with open(vtt_file, "w", encoding="utf-8") as f:
            f.write(vtt_content)

        LOGGER.info(f"Exported Subtitles: {srt_file} and {vtt_file}")

    LOGGER.info(f"Saved script JSON: {target_file}")
    LOGGER.info(f"Saved script Markdown: {md_file}")
    return target_file


def format_script_as_markdown(script: GeneratedScriptModel | Dict[str, Any]) -> str:
    """Render script into a readable Markdown document."""
    if isinstance(script, dict):
        model = GeneratedScriptModel.model_validate(script)
    else:
        model = script

    lines = [
        f"# Video Script: {model.topic}",
        f"\n**Generated At:** {model.generated_at or 'N/A'}",
        f"**Estimated Total Duration:** ~{model.estimated_duration_seconds} seconds",
        f"**Tone:** {model.target_tone}",
        f"**Style Template Applied:** {model.style_template_applied}",
        "\n## 🎯 Suggested Titles",
    ]

    for title in model.suggested_titles:
        lines.append(f"- {title}")

    hook = model.hook
    lines.extend([
        f"\n## 🎣 Hook ({hook.duration_seconds}s)",
        f"**Spoken Dialogue:**\n> {hook.spoken_dialogue}\n",
        f"**Visual & B-Roll:**\n*{hook.visual_b_roll_instructions}*",
        "\n## 🎬 Main Sections",
    ])

    for sec in model.sections:
        lines.extend([
            f"\n### {sec.title} (~{sec.duration_seconds}s)",
            f"**Spoken Dialogue:**\n> {sec.spoken_dialogue}\n",
            f"**Visual & B-Roll:**\n*{sec.visual_b_roll_instructions}*",
        ])

    outro = model.call_to_action_and_outro
    lines.extend([
        f"\n## 📣 Call to Action & Outro ({outro.duration_seconds}s)",
        f"**Spoken Dialogue:**\n> {outro.spoken_dialogue}\n",
        f"**Visual & B-Roll:**\n*{outro.visual_b_roll_instructions}*",
        "\n## 🏷️ SEO & Description Blueprint",
        f"**Tags:** {', '.join(model.seo_tags)}\n",
        "**Description:**",
        "```",
        model.description_blueprint,
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
    parser.add_argument(
        "--comment_gaps",
        "-g",
        default=None,
        help="Path to comment_gaps.json produced by comment_miner.",
    )
    parser.add_argument("--model", "-m", default=None, help="Gemini model (default: GEMINI_MODEL or gemini-3.6-flash).")
    parser.add_argument("--output", "-o", default=None, help="Custom output JSON path.")
    parser.add_argument("--no-subtitles", action="store_true", help="Disable automatic SRT/VTT subtitle export.")
    args = parser.parse_args()

    try:
        script = generate_script(
            topic=args.topic,
            target_audience=args.audience,
            style_template_source=args.style_template,
            comment_gaps_source=args.comment_gaps,
            gemini_model=args.model,
        )
        out_path = save_script_outputs(script, args.output, export_subtitles=not args.no_subtitles)
        print(f"Script successfully generated at: {out_path}")
    except Exception as exc:
        LOGGER.error(f"Script generation failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
