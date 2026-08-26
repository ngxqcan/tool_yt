"""Data models and robust schema validation for Competitor Video Analyzer and Script Generator."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel, Field, field_validator

LOGGER = logging.getLogger("models")
T = TypeVar("T", bound=BaseModel)


def strip_markdown_fences(raw_text: str) -> str:
    """Clean markdown code fences (e.g. ```json ... ``` or ``` ... ```) and whitespace."""
    if not raw_text:
        return ""
    text = raw_text.strip()
    
    # Remove leading ```json or ```
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    # Remove trailing ```
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_json_object(raw_text: str) -> str:
    """Extract first valid JSON object block from text if wrapped in conversational filler."""
    cleaned = strip_markdown_fences(raw_text)
    
    # Check if directly parsable
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned

    # Search for outer braces
    match = re.search(r"(\{[\s\S]*\})", cleaned)
    if match:
        return match.group(1)
    
    return cleaned


def parse_and_validate_json(raw_text: str, model_cls: Type[T]) -> T:
    """Robustly parse text into a validated Pydantic model.

    Handles markdown fences, regex fallback extraction, and Pydantic validation.
    """
    clean_json_str = extract_json_object(raw_text)
    try:
        data = json.loads(clean_json_str)
    except json.JSONDecodeError as exc:
        LOGGER.error(f"JSON decode failed on extracted text: {clean_json_str[:200]}... Error: {exc}")
        raise ValueError(f"Failed to decode JSON from model response: {exc}") from exc

    return model_cls.model_validate(data)


# -----------------------------------------------------------------------------
# Style Template Models
# -----------------------------------------------------------------------------

class TitleThumbnailPatternModel(BaseModel):
    title_length_chars: int = Field(default=50, description="Character count of title")
    title_word_count: int = Field(default=8, description="Word count of title")
    capitalization_style: str = Field(default="Title Case", description="Casing pattern")
    has_numbers: bool = Field(default=False, description="Whether title contains numbers")
    has_brackets: bool = Field(default=False, description="Whether title contains brackets/parentheses")
    has_emojis: bool = Field(default=False, description="Whether title contains emojis")
    tag_themes: List[str] = Field(default_factory=list, description="Extracted tag topics/themes")


class StyleTemplateModel(BaseModel):
    hook_style: str = Field(
        default="High-impact problem statement or opening dilemma",
        description="Abstract mechanism used in the opening 15-30s",
    )
    section_count: int = Field(
        default=4,
        ge=1,
        le=20,
        description="Total number of main sections/beats",
    )
    section_pacing: List[str] = Field(
        default_factory=lambda: [
            "Beat 1: Hook and premise setup (~60s)",
            "Beat 2: Core mechanism explanation (~90s)",
            "Beat 3: Practical execution steps (~90s)",
            "Beat 4: Key takeaways and conclusion (~60s)",
        ],
        description="Descriptions of each structural beat and pacing cadence",
    )
    tone: str = Field(
        default="Authoritative, educational, and engaging",
        description="Delivery tone and vocal pacing",
    )
    title_formula: str = Field(
        default="[Topic]: The Essential Guide",
        description="Formulaic headline pattern extracted from reference",
    )
    avg_section_length_seconds: int = Field(
        default=90,
        ge=10,
        description="Average length of each content beat",
    )
    ending_style: str = Field(
        default="Concise summary followed by a targeted community question CTA",
        description="Closing mechanism and call-to-action style",
    )
    estimated_total_length_seconds: int = Field(
        default=480,
        ge=30,
        description="Total estimated video duration in seconds",
    )
    title_thumbnail_pattern: TitleThumbnailPatternModel = Field(
        default_factory=TitleThumbnailPatternModel,
        description="Packaging and thumbnail styling cues",
    )
    source_video_id: Optional[str] = Field(default=None, description="Reference video ID(s)")
    generated_at: Optional[str] = Field(default=None, description="Timestamp of generation")
    guardrail_compliance: str = Field(
        default="Strict format DNA only. No verbatim competitor dialogue or proprietary content.",
        description="Guardrail verification statement",
    )

    @field_validator("section_count", mode="before")
    @classmethod
    def ensure_section_count(cls, v: Any) -> int:
        try:
            val = int(v)
            return max(1, val)
        except Exception:
            return 4


# -----------------------------------------------------------------------------
# Generated Script Models
# -----------------------------------------------------------------------------

class HookModel(BaseModel):
    duration_seconds: int = Field(default=20, ge=5, description="Hook duration in seconds")
    spoken_dialogue: str = Field(..., description="Spoken voiceover script for the opening hook")
    visual_b_roll_instructions: str = Field(
        default="Dynamic on-screen text and fast cut visuals.",
        description="Visual directions and B-roll notes",
    )


class SectionBeatModel(BaseModel):
    section_number: int = Field(default=1, ge=1)
    title: str = Field(default="Beat Overview", description="Section title or theme")
    duration_seconds: int = Field(default=90, ge=10, description="Section duration in seconds")
    spoken_dialogue: str = Field(..., description="Spoken voiceover lines for this section")
    visual_b_roll_instructions: str = Field(
        default="Clean graphic overlay and relevant B-roll clips.",
        description="Visual instructions and screen actions",
    )


class OutroModel(BaseModel):
    duration_seconds: int = Field(default=20, ge=5, description="Outro duration in seconds")
    spoken_dialogue: str = Field(..., description="Spoken voiceover script for the outro and CTA")
    visual_b_roll_instructions: str = Field(
        default="Host wrap-up with animated subscribe button and end screen video cards.",
        description="Visual directions for end screen",
    )


class GeneratedScriptModel(BaseModel):
    topic: str = Field(..., description="Topic of the video")
    suggested_titles: List[str] = Field(
        default_factory=lambda: ["Untitled Video"],
        description="List of title options matching the pattern",
    )
    estimated_duration_seconds: int = Field(default=300, description="Estimated total runtime")
    target_tone: str = Field(default="Educational and engaging", description="Intended tone")
    hook: HookModel = Field(..., description="Opening hook segment")
    sections: List[SectionBeatModel] = Field(default_factory=list, description="Main content beats")
    call_to_action_and_outro: OutroModel = Field(..., description="Closing CTA outro segment")
    seo_tags: List[str] = Field(default_factory=list, description="YouTube SEO tags")
    description_blueprint: str = Field(default="", description="YouTube description ready for upload")
    generated_at: Optional[str] = Field(default=None)
    style_template_applied: bool = Field(default=False)
    template_source_video_id: Optional[str] = Field(default=None)
