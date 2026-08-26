"""Data models and robust schema validation for full-scale YouTube AI Production Suite."""

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
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_json_object(raw_text: str) -> str:
    """Extract first valid JSON object block from text if wrapped in conversational filler."""
    cleaned = strip_markdown_fences(raw_text)
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned

    match = re.search(r"(\{[\s\S]*\})", cleaned)
    if match:
        return match.group(1)

    return cleaned


def parse_and_validate_json(raw_text: str, model_cls: Type[T]) -> T:
    """Robustly parse text into a validated Pydantic model."""
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
    section_count: int = Field(default=4, ge=1, le=20)
    section_pacing: List[str] = Field(
        default_factory=lambda: [
            "Beat 1: Hook and premise setup (~60s)",
            "Beat 2: Core mechanism explanation (~90s)",
            "Beat 3: Practical execution steps (~90s)",
            "Beat 4: Key takeaways and conclusion (~60s)",
        ]
    )
    tone: str = Field(default="Authoritative, educational, and engaging")
    title_formula: str = Field(default="[Topic]: The Essential Guide")
    avg_section_length_seconds: int = Field(default=90, ge=10)
    ending_style: str = Field(default="Concise summary followed by a targeted community question CTA")
    estimated_total_length_seconds: int = Field(default=480, ge=30)
    title_thumbnail_pattern: TitleThumbnailPatternModel = Field(default_factory=TitleThumbnailPatternModel)
    source_video_id: Optional[str] = Field(default=None)
    generated_at: Optional[str] = Field(default=None)
    guardrail_compliance: str = Field(
        default="Strict format DNA only. No verbatim competitor dialogue or proprietary content."
    )

    @field_validator("section_count", mode="before")
    @classmethod
    def ensure_section_count(cls, v: Any) -> int:
        try:
            return max(1, int(v))
        except Exception:
            return 4


# -----------------------------------------------------------------------------
# Generated Script Models
# -----------------------------------------------------------------------------

class HookModel(BaseModel):
    duration_seconds: int = Field(default=20, ge=5)
    spoken_dialogue: str = Field(..., description="Spoken voiceover script for opening hook")
    visual_b_roll_instructions: str = Field(
        default="Dynamic on-screen text and fast cut visuals.",
        description="Visual directions and B-roll notes",
    )


class SectionBeatModel(BaseModel):
    section_number: int = Field(default=1, ge=1)
    title: str = Field(default="Beat Overview")
    duration_seconds: int = Field(default=90, ge=10)
    spoken_dialogue: str = Field(..., description="Spoken voiceover lines")
    visual_b_roll_instructions: str = Field(
        default="Clean graphic overlay and relevant B-roll clips.",
        description="Visual instructions",
    )


class OutroModel(BaseModel):
    duration_seconds: int = Field(default=20, ge=5)
    spoken_dialogue: str = Field(..., description="Spoken voiceover for outro and CTA")
    visual_b_roll_instructions: str = Field(
        default="Host wrap-up with animated subscribe button and end screen video cards."
    )


class GeneratedScriptModel(BaseModel):
    topic: str = Field(..., description="Topic of the video")
    suggested_titles: List[str] = Field(default_factory=lambda: ["Untitled Video"])
    estimated_duration_seconds: int = Field(default=300)
    target_tone: str = Field(default="Educational and engaging")
    hook: HookModel = Field(..., description="Opening hook segment")
    sections: List[SectionBeatModel] = Field(default_factory=list)
    call_to_action_and_outro: OutroModel = Field(...)
    seo_tags: List[str] = Field(default_factory=list)
    description_blueprint: str = Field(default="")
    generated_at: Optional[str] = Field(default=None)
    style_template_applied: bool = Field(default=False)
    template_source_video_id: Optional[str] = Field(default=None)


# -----------------------------------------------------------------------------
# Outlier & Channel Intelligence Models
# -----------------------------------------------------------------------------

class OutlierVideoModel(BaseModel):
    video_id: str
    title: str
    url: str
    view_count: int
    published_at: str
    outlier_score: float = Field(
        description="Ratio of video view count over channel average views (e.g. 4.5x)"
    )
    like_count: int = 0
    duration_seconds: int = 0


class ChannelAnalysisModel(BaseModel):
    channel_id: str
    channel_title: str
    total_videos_analyzed: int
    average_view_count: float
    median_view_count: float
    outlier_videos: List[OutlierVideoModel] = Field(default_factory=list)
    dominant_title_keywords: List[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Comment Mining & Content Gap Models
# -----------------------------------------------------------------------------

class CommentGapModel(BaseModel):
    question_or_critique: str
    frequency_or_relevance: str = "High"
    suggested_script_angle: str


class CommentGapAnalysisModel(BaseModel):
    video_id: str
    total_comments_analyzed: int
    audience_sentiment: str = "Neutral / Inquisitive"
    top_liked_questions: List[str] = Field(default_factory=list)
    content_gaps: List[CommentGapModel] = Field(default_factory=list)
    recommended_talking_points: List[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Shorts & Repurposing Models
# -----------------------------------------------------------------------------

class ShortsBeatModel(BaseModel):
    duration_seconds: int = Field(default=10, ge=3)
    spoken_dialogue: str
    on_screen_text: str
    visual_action: str


class ShortsScriptModel(BaseModel):
    shorts_id: int
    title: str
    target_duration_seconds: int = 45
    hook: str
    beats: List[ShortsBeatModel] = Field(default_factory=list)
    call_to_action: str
    hashtags: List[str] = Field(default_factory=lambda: ["#shorts", "#viral", "#tech"])


class ShortsCollectionModel(BaseModel):
    parent_topic: str
    shorts: List[ShortsScriptModel] = Field(default_factory=list)
    generated_at: Optional[str] = Field(default=None)


# -----------------------------------------------------------------------------
# Thumbnail Designer Models
# -----------------------------------------------------------------------------

class ThumbnailPromptVariationModel(BaseModel):
    variation_name: str
    style_concept: str
    midjourney_prompt: str
    dalle_prompt: str
    imagen_prompt: str
    recommended_text_overlay: str
    color_palette_hex: List[str] = Field(default_factory=lambda: ["#FF0000", "#FFFFFF", "#000000"])


class ThumbnailDesignModel(BaseModel):
    video_topic: str
    core_visual_metaphor: str
    emotional_trigger: str
    prompts: List[ThumbnailPromptVariationModel] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Community Post & Newsletter Models
# -----------------------------------------------------------------------------

class CommunityPostModel(BaseModel):
    topic: str
    poll_question: str
    poll_options: List[str] = Field(default_factory=list)
    engagement_post_text: str
    newsletter_summary: str
