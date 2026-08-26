"""Competitor Video Analyzer Module.

Extracts structural/format DNA (hook style, section beats, pacing, tone, title formula,
thumbnail/title cues) from a YouTube video URL and outputs a style template.

Strict Guardrail:
This module extracts META-PATTERNS only (structure, pacing, tone, format).
It never reproduces or quotes the competitor's script, dialogue, or footage.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import requests
from dotenv import load_dotenv

from models import StyleTemplateModel, TitleThumbnailPatternModel, parse_and_validate_json
from utils import (
    ensure_dir,
    get_cache_dir,
    get_log_dir,
    get_output_dir,
    get_project_root,
    retry_with_backoff,
    setup_logging,
)

load_dotenv()

LOGGER = setup_logging("competitor_analyzer")

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None  # type: ignore


def extract_video_id(url_or_id: str) -> str:
    """Extract standard 11-character YouTube video ID from various URL formats or raw ID.

    Supports:
    - https://www.youtube.com/watch?v=dQw4w9WgXcQ
    - https://youtu.be/dQw4w9WgXcQ
    - https://www.youtube.com/shorts/dQw4w9WgXcQ
    - https://www.youtube.com/embed/dQw4w9WgXcQ
    - dQw4w9WgXcQ
    """
    if not url_or_id:
        raise ValueError("URL or Video ID cannot be empty.")

    clean_input = url_or_id.strip()

    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", clean_input):
        return clean_input

    parsed = urllib.parse.urlparse(clean_input)
    if "youtube.com" in parsed.netloc:
        if parsed.path == "/watch":
            qs = urllib.parse.parse_qs(parsed.query)
            if "v" in qs and qs["v"]:
                return qs["v"][0]
        elif parsed.path.startswith("/shorts/"):
            return parsed.path.split("/shorts/")[1].split("/")[0].split("?")[0]
        elif parsed.path.startswith("/embed/"):
            return parsed.path.split("/embed/")[1].split("/")[0].split("?")[0]
    elif "youtu.be" in parsed.netloc:
        path = parsed.path.lstrip("/")
        if path:
            return path.split("/")[0].split("?")[0]

    match = re.search(r"(?:v=|\/shorts\/|\/embed\/|youtu\.be\/)([a-zA-Z0-9_-]{11})", clean_input)
    if match:
        return match.group(1)

    raise ValueError(f"Could not extract a valid YouTube video ID from: {url_or_id}")


def log_audit_trail(video_id: str, action: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Log an audit entry to logs/competitor_analysis.log.

    Ensures a clear, immutable compliance record showing only structural analysis was performed.
    """
    logs_dir = get_log_dir()
    log_file = logs_dir / "competitor_analysis.log"
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    audit_entry = {
        "timestamp": timestamp,
        "video_id": video_id,
        "action": action,
        "guardrail_status": "COMPLIANT_STRUCTURAL_ONLY",
        "details": details or {},
    }

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        LOGGER.warning(f"Could not write to audit log file: {exc}")


@retry_with_backoff(max_retries=3, initial_delay=1.0, retryable_exceptions=(requests.RequestException,))
def _call_youtube_data_api(url: str, params: Dict[str, Any]) -> requests.Response:
    """Execute HTTP request to YouTube Data API with exponential backoff."""
    return requests.get(url, params=params, timeout=10)


def fetch_public_metadata(
    video_id: str,
    api_key: Optional[str] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Step 1: Pull public video metadata using YouTube Data API v3 (with oEmbed fallback).

    Saves raw metadata to cache/competitor/{video_id}/metadata.json
    """
    api_key = api_key or os.getenv("YOUTUBE_API_KEY")
    cache_dir = ensure_dir(get_cache_dir() / "competitor" / video_id)
    metadata_file = cache_dir / "metadata.json"

    # Check cache if not forcing refresh
    if not force_refresh and metadata_file.exists():
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            if cached_data.get("title"):
                LOGGER.info(f"[CACHE HIT] Loaded metadata from cache for video: {video_id}")
                return cached_data
        except Exception as exc:
            LOGGER.warning(f"Cache read error for {video_id} metadata: {exc}")

    metadata: Dict[str, Any] = {
        "video_id": video_id,
        "title": "",
        "description": "",
        "tags": [],
        "duration": "",
        "viewCount": "0",
        "likeCount": "0",
        "publishedAt": "",
        "categoryId": "",
        "channelTitle": "",
    }

    if api_key:
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "id": video_id,
            "part": "snippet,contentDetails,statistics",
            "key": api_key,
        }
        try:
            resp = _call_youtube_data_api(url, params)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if items:
                    item = items[0]
                    snippet = item.get("snippet", {})
                    content_details = item.get("contentDetails", {})
                    stats = item.get("statistics", {})

                    metadata.update({
                        "title": snippet.get("title", ""),
                        "description": snippet.get("description", ""),
                        "tags": snippet.get("tags", []),
                        "publishedAt": snippet.get("publishedAt", ""),
                        "categoryId": snippet.get("categoryId", ""),
                        "channelTitle": snippet.get("channelTitle", ""),
                        "duration": content_details.get("duration", ""),
                        "viewCount": stats.get("viewCount", "0"),
                        "likeCount": stats.get("likeCount", "0"),
                        "source": "youtube_data_api_v3",
                    })
                    LOGGER.info(f"Successfully retrieved metadata via YouTube Data API for: {video_id}")
                else:
                    LOGGER.warning(f"Video {video_id} not found in YouTube Data API.")
            else:
                LOGGER.warning(f"YouTube Data API returned {resp.status_code}: {resp.text[:100]}")
        except Exception as exc:
            LOGGER.warning(f"Error calling YouTube Data API ({exc}). Trying fallback...")

    # Fallback to oEmbed
    if not metadata["title"]:
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            oembed_resp = requests.get(oembed_url, timeout=10)
            if oembed_resp.status_code == 200:
                oembed_data = oembed_resp.json()
                metadata["title"] = oembed_data.get("title", "")
                metadata["channelTitle"] = oembed_data.get("author_name", "")
                metadata["source"] = "oembed_fallback"
                LOGGER.info(f"Retrieved title metadata via oEmbed for {video_id}")
        except Exception as exc:
            LOGGER.warning(f"oEmbed fallback failed: {exc}")

    # Save to cache
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    log_audit_trail(video_id, "METADATA_EXTRACTED", {
        "title": metadata.get("title"),
        "channel": metadata.get("channelTitle"),
        "has_tags": len(metadata.get("tags", [])) > 0,
    })

    return metadata


def fetch_transcript(
    video_id: str,
    preferred_languages: Optional[Sequence[str]] = None,
    force_refresh: bool = False,
) -> Optional[Dict[str, Any]]:
    """Step 2: Pull timestamped transcript with multi-language & fallback discovery support.

    Saves to cache/competitor/{video_id}/transcript.json marked as 'reference-only, do not quote'.
    """
    cache_dir = ensure_dir(get_cache_dir() / "competitor" / video_id)
    transcript_file = cache_dir / "transcript.json"

    if not force_refresh and transcript_file.exists():
        try:
            with open(transcript_file, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            if cached_data.get("entries"):
                LOGGER.info(f"[CACHE HIT] Loaded transcript from cache for video: {video_id}")
                return cached_data
        except Exception as exc:
            LOGGER.warning(f"Cache read error for {video_id} transcript: {exc}")

    if YouTubeTranscriptApi is None:
        LOGGER.warning("youtube-transcript-api is not installed. Skipping transcript fetch.")
        return None

    langs = list(preferred_languages) if preferred_languages else ["vi", "en", "auto"]

    try:
        raw_entries = None
        
        # 1. Try class-level or instance-level fetch with specified languages
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            try:
                raw_entries = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
            except Exception:
                # Fallback to any transcript available
                raw_entries = YouTubeTranscriptApi.get_transcript(video_id)
        elif hasattr(YouTubeTranscriptApi, "fetch"):
            api_instance = YouTubeTranscriptApi() if hasattr(YouTubeTranscriptApi, "__call__") else YouTubeTranscriptApi
            try:
                fetched = api_instance.fetch(video_id, languages=langs)
            except Exception:
                fetched = api_instance.fetch(video_id)
            
            if hasattr(fetched, "to_raw_data"):
                raw_entries = fetched.to_raw_data()
            elif hasattr(fetched, "fetch"):
                raw_entries = fetched.fetch()
            else:
                raw_entries = list(fetched)
        else:
            # Try list_transcripts to discover any language
            api_instance = YouTubeTranscriptApi()
            transcript_list = api_instance.list(video_id) if hasattr(api_instance, "list") else YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(langs)
            raw_entries = transcript.fetch()

        formatted_entries = []
        for entry in (raw_entries or []):
            if isinstance(entry, dict):
                formatted_entries.append({
                    "start": float(entry.get("start", 0.0)),
                    "duration": float(entry.get("duration", 0.0)),
                    "text": str(entry.get("text", "")),
                })

        total_duration = 0.0
        if formatted_entries:
            last_entry = formatted_entries[-1]
            total_duration = last_entry.get("start", 0.0) + last_entry.get("duration", 0.0)

        transcript_data = {
            "_guardrail_notice": "REFERENCE-ONLY, DO NOT QUOTE. Extracted strictly for structural/pacing analysis.",
            "video_id": video_id,
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "entry_count": len(formatted_entries),
            "estimated_duration_seconds": round(total_duration, 2),
            "entries": formatted_entries,
        }

        with open(transcript_file, "w", encoding="utf-8") as f:
            json.dump(transcript_data, f, indent=2, ensure_ascii=False)

        LOGGER.info(f"Successfully fetched transcript ({len(formatted_entries)} entries) for {video_id}")
        log_audit_trail(video_id, "TRANSCRIPT_EXTRACTED", {
            "entry_count": len(formatted_entries),
            "duration_seconds": round(total_duration, 2),
            "notice": "reference-only, do not quote",
        })
        return transcript_data

    except Exception as exc:
        LOGGER.warning(f"No available transcript/captions for {video_id} ({exc}). Falling back to metadata-only analysis.")
        log_audit_trail(video_id, "TRANSCRIPT_FETCH_FAILED_FALLBACK_TO_METADATA", {"error": str(exc)})
        return None


def extract_title_thumbnail_pattern(metadata: Dict[str, Any]) -> TitleThumbnailPatternModel:
    """Step 5: Extract packaging cues from title, description, and tags."""
    title = metadata.get("title", "")
    has_numbers = bool(re.search(r"\d+", title))
    has_brackets = bool(re.search(r"[\[\]\(\)\{\}]", title))
    has_emojis = bool(re.search(r"[\U00010000-\U0010ffff]", title))

    if title.isupper() and len(title) > 3:
        caps_style = "ALL_CAPS"
    elif title.istitle():
        caps_style = "Title Case"
    elif title.islower():
        caps_style = "lowercase"
    else:
        caps_style = "Mixed Case / Standard"

    tags = metadata.get("tags", [])
    tag_themes = tags[:8] if tags else []

    return TitleThumbnailPatternModel(
        title_length_chars=len(title),
        title_word_count=len(title.split()),
        capitalization_style=caps_style,
        has_numbers=has_numbers,
        has_brackets=has_brackets,
        has_emojis=has_emojis,
        tag_themes=tag_themes,
    )


def parse_iso8601_duration(duration_str: str) -> int:
    """Convert ISO 8601 duration string (e.g., PT12M30S) to seconds."""
    if not duration_str:
        return 0
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


@retry_with_backoff(max_retries=3, initial_delay=2.0)
def _generate_content_with_gemini(client: Any, model_name: str, prompt: str, system_instruction: str) -> str:
    """Call Gemini API with retry and backoff."""
    from google.genai import types
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    return response.text or ""


def analyze_structure_with_gemini(
    metadata: Dict[str, Any],
    transcript_data: Optional[Dict[str, Any]],
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
) -> StyleTemplateModel:
    """Step 3: Analyze structural and format DNA with Gemini and validate with Pydantic.

    Strict guardrail: Prompt explicitly forbids copying or summarizing specific content.
    """
    video_id = metadata.get("video_id", "unknown")
    api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model_name = gemini_model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    title_pattern = extract_title_thumbnail_pattern(metadata)

    # Condense transcript sample for structure
    transcript_summary_for_prompt = ""
    if transcript_data and transcript_data.get("entries"):
        entries = transcript_data["entries"]
        sample_size = min(len(entries), 100)
        step = max(1, len(entries) // sample_size)
        sampled = entries[::step]

        lines = []
        for e in sampled:
            start_m = int(e.get("start", 0) // 60)
            start_s = int(e.get("start", 0) % 60)
            short_text = e.get("text", "").replace("\n", " ").strip()[:60]
            lines.append(f"[{start_m:02d}:{start_s:02d}] {short_text}...")
        transcript_summary_for_prompt = "\n".join(lines)
    else:
        transcript_summary_for_prompt = "(No captions available. Analyze video format based on metadata only.)"

    raw_duration_sec = parse_iso8601_duration(metadata.get("duration", ""))
    if raw_duration_sec == 0 and transcript_data:
        raw_duration_sec = int(transcript_data.get("estimated_duration_seconds", 0))

    system_instruction = (
        "You are an expert YouTube video strategist and format analyst. "
        "Your task is to analyze ONLY the STRUCTURAL, FORMAT, and PACING DNA of a video, NOT its specific content. "
        "CRITICAL GUARDRAIL: Do NOT summarize, reproduce, or quote the competitor's actual storyline, facts, dialogue, or script. "
        "Describe structural patterns in abstract, reusable terms only."
    )

    prompt = f"""You are analyzing the STRUCTURE and FORMAT of this YouTube video, not its specific content.

Identify:
(1) The hook style used in the first 15-30 seconds.
(2) How many main sections/beats the video has and roughly how long each is.
(3) The pacing pattern (fast cuts vs. long explanations).
(4) The overall tone (authoritative, educational, dramatic, casual, urgent).
(5) The title formula pattern (e.g. 'number + superlative + topic', 'question hook').
(6) What type of call-to-action or ending it uses.

Do NOT summarize or reproduce the actual content/story — only describe the structural pattern in abstract terms.

VIDEO METADATA (Reference only):
- Title: {metadata.get('title')}
- Description excerpt: {metadata.get('description', '')[:200]}...
- Tags: {', '.join(metadata.get('tags', [])[:10])}
- Known Duration: ~{raw_duration_sec} seconds
- Title Pattern: {title_pattern.model_dump_json()}

TIMESTAMPS & PACING SAMPLES (Structure reference only):
{transcript_summary_for_prompt}

Return ONLY valid JSON matching this schema:
{{
  "hook_style": "string",
  "section_count": <int>,
  "section_pacing": ["Beat 1...", "Beat 2..."],
  "tone": "string",
  "title_formula": "string",
  "avg_section_length_seconds": <int>,
  "ending_style": "string",
  "estimated_total_length_seconds": <int>
}}
"""

    template_model: Optional[StyleTemplateModel] = None

    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            raw_response_text = _generate_content_with_gemini(client, model_name, prompt, system_instruction)
            template_model = parse_and_validate_json(raw_response_text, StyleTemplateModel)
            LOGGER.info("Successfully parsed and validated style template via Gemini API & Pydantic.")
        except Exception as exc:
            LOGGER.warning(f"Gemini API / parsing failed ({exc}). Falling back to heuristic format engine.")

    if template_model is None:
        LOGGER.info("Using built-in deterministic format heuristics for style template.")
        template_model = _heuristic_style_template(metadata, title_pattern, raw_duration_sec)

    template_model.title_thumbnail_pattern = title_pattern
    template_model.source_video_id = video_id
    template_model.generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Cache result
    cache_dir = ensure_dir(get_cache_dir() / "competitor" / video_id)
    template_file = cache_dir / "style_template.json"
    with open(template_file, "w", encoding="utf-8") as f:
        f.write(template_model.model_dump_json(indent=2))

    log_audit_trail(video_id, "STYLE_TEMPLATE_GENERATED", {
        "hook_style": template_model.hook_style,
        "section_count": template_model.section_count,
        "tone": template_model.tone,
        "title_formula": template_model.title_formula,
    })

    return template_model


def _heuristic_style_template(
    metadata: Dict[str, Any],
    title_pattern: TitleThumbnailPatternModel,
    duration_sec: int,
) -> StyleTemplateModel:
    """Deterministic fallback format template generator."""
    title = metadata.get("title", "")
    if re.search(r"^\d+", title):
        formula = "[Number] [Adjective/Superlative] [Topic] That [Outcome]"
    elif re.search(r"^(how to|how i|how we)", title, re.IGNORECASE):
        formula = "How To [Achieve Goal] in [Timeframe/Condition]"
    elif "?" in title:
        formula = "Is [Topic] [Provocative Question]? [The Truth / Analysis]"
    else:
        formula = "[Topic]: [Key Trend / Warning / Essential Guide]"

    total_sec = duration_sec if duration_sec > 0 else 480
    section_count = max(3, min(6, total_sec // 90))
    avg_len = total_sec // section_count

    return StyleTemplateModel(
        hook_style="High-impact opening question posing the central challenge within 15 seconds.",
        section_count=section_count,
        section_pacing=[
            f"Beat {i+1}: {'Context & Problem Setup' if i==0 else ('Key Strategic Insight' if i < section_count-1 else 'Actionable Conclusion & Next Steps')} (~{avg_len}s)"
            for i in range(section_count)
        ],
        tone="Authoritative, educational, and engaging with concise explanations.",
        title_formula=formula,
        avg_section_length_seconds=avg_len,
        ending_style="Key takeaway summary followed by a targeted call-to-action question.",
        estimated_total_length_seconds=total_sec,
        title_thumbnail_pattern=title_pattern,
    )


def analyze_multiple_competitors(
    urls_or_ids: List[str],
    youtube_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
    force_refresh: bool = False,
) -> Path:
    """Analyze multiple competitor videos and synthesize an aggregated style template."""
    LOGGER.info(f"Analyzing and synthesizing format patterns across {len(urls_or_ids)} competitor video(s)...")
    templates: List[StyleTemplateModel] = []
    video_ids: List[str] = []

    for item in urls_or_ids:
        vid = extract_video_id(item)
        video_ids.append(vid)
        meta = fetch_public_metadata(vid, api_key=youtube_api_key, force_refresh=force_refresh)
        transcript = fetch_transcript(vid, force_refresh=force_refresh)
        template = analyze_structure_with_gemini(
            metadata=meta,
            transcript_data=transcript,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
        )
        templates.append(template)

    if len(templates) == 1:
        composite = templates[0]
    else:
        # Blend multiple competitor patterns
        avg_sec_count = max(3, round(sum(t.section_count for t in templates) / len(templates)))
        avg_sec_len = round(sum(t.avg_section_length_seconds for t in templates) / len(templates))
        avg_total_dur = round(sum(t.estimated_total_length_seconds for t in templates) / len(templates))

        all_tag_themes = []
        for t in templates:
            all_tag_themes.extend(t.title_thumbnail_pattern.tag_themes)
        unique_tags = list(dict.fromkeys(all_tag_themes))[:10]

        composite = StyleTemplateModel(
            hook_style=f"Synthesized Hook: {templates[0].hook_style} (Cross-referenced with {len(templates)} top videos)",
            section_count=avg_sec_count,
            section_pacing=templates[0].section_pacing[:avg_sec_count],
            tone=templates[0].tone,
            title_formula=templates[0].title_formula,
            avg_section_length_seconds=avg_sec_len,
            ending_style=templates[0].ending_style,
            estimated_total_length_seconds=avg_total_dur,
            title_thumbnail_pattern=TitleThumbnailPatternModel(
                title_length_chars=round(sum(t.title_thumbnail_pattern.title_length_chars for t in templates) / len(templates)),
                capitalization_style=templates[0].title_thumbnail_pattern.capitalization_style,
                has_numbers=any(t.title_thumbnail_pattern.has_numbers for t in templates),
                has_brackets=any(t.title_thumbnail_pattern.has_brackets for t in templates),
                tag_themes=unique_tags,
            ),
            source_video_id=",".join(video_ids),
            generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    # Save synthesized template
    composite_dir = ensure_dir(get_cache_dir() / "competitor" / "composite")
    composite_file = composite_dir / "style_template.json"
    with open(composite_file, "w", encoding="utf-8") as f:
        f.write(composite.model_dump_json(indent=2))

    LOGGER.info(f"Synthesized style template saved to: {composite_file}")
    return composite_file


def analyze_competitor_video(
    url_or_id: str,
    youtube_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
    output_path: Optional[str] = None,
    force_refresh: bool = False,
    preferred_languages: Optional[Sequence[str]] = None,
) -> str:
    """End-to-end competitor video analysis. Returns absolute path to style_template.json."""
    video_id = extract_video_id(url_or_id)
    LOGGER.info(f"Starting competitor format analysis for video ID: {video_id}")

    metadata = fetch_public_metadata(video_id, api_key=youtube_api_key, force_refresh=force_refresh)
    transcript_data = fetch_transcript(video_id, preferred_languages=preferred_languages, force_refresh=force_refresh)

    style_template_model = analyze_structure_with_gemini(
        metadata=metadata,
        transcript_data=transcript_data,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
    )

    if output_path:
        out_file = Path(output_path).resolve()
        ensure_dir(out_file.parent)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(style_template_model.model_dump_json(indent=2))
        target_path = str(out_file)
    else:
        target_path = str(get_cache_dir() / "competitor" / video_id / "style_template.json")

    LOGGER.info(f"Style template successfully generated: {target_path}")
    return target_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze YouTube video structural DNA and output a reusable style template."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", "-u", help="Single YouTube video URL or 11-char Video ID.")
    group.add_argument("--urls", help="Comma-separated list of competitor YouTube URLs to synthesize.")

    parser.add_argument("--output", "-o", default=None, help="Optional custom output path for style_template.json.")
    parser.add_argument("--model", "-m", default=None, help="Gemini model name (default: GEMINI_MODEL or gemini-2.5-flash).")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache and force refetching metadata/transcript.")
    parser.add_argument("--languages", default="vi,en", help="Preferred subtitle languages, comma-separated (e.g. 'vi,en').")
    args = parser.parse_args()

    try:
        lang_list = [l.strip() for l in args.languages.split(",") if l.strip()]
        if args.urls:
            urls_list = [u.strip() for u in args.urls.split(",") if u.strip()]
            template_path = str(analyze_multiple_competitors(
                urls_or_ids=urls_list,
                gemini_model=args.model,
                force_refresh=args.force_refresh,
            ))
        else:
            template_path = analyze_competitor_video(
                url_or_id=args.url,
                output_path=args.output,
                gemini_model=args.model,
                force_refresh=args.force_refresh,
                preferred_languages=lang_list,
            )
        print(template_path)
    except Exception as exc:
        LOGGER.error(f"Analysis failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
