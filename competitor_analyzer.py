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
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.parse
import requests
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Setup module logger
LOGGER = logging.getLogger("competitor_analyzer")
LOGGER.setLevel(logging.INFO)
if not LOGGER.handlers:
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    LOGGER.addHandler(ch)


try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None  # type: ignore


def get_project_root() -> Path:
    """Return the absolute path to the project root."""
    return Path(__file__).resolve().parent


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


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

    # Raw 11-char ID
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", clean_input):
        return clean_input

    # Parse URL
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

    # Regex fallback search
    match = re.search(r"(?:v=|\/shorts\/|\/embed\/|youtu\.be\/)([a-zA-Z0-9_-]{11})", clean_input)
    if match:
        return match.group(1)

    raise ValueError(f"Could not extract a valid YouTube video ID from: {url_or_id}")


def log_audit_trail(video_id: str, action: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Log an audit entry to logs/competitor_analysis.log.

    Ensures a clear, immutable compliance record showing only structural analysis was performed.
    """
    logs_dir = ensure_dir(get_project_root() / "logs")
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


def fetch_public_metadata(video_id: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """Step 1: Pull public video metadata using YouTube Data API v3 (or fallback).

    Saves raw metadata to cache/competitor/{video_id}/metadata.json
    """
    api_key = api_key or os.getenv("YOUTUBE_API_KEY")
    cache_dir = ensure_dir(get_project_root() / "cache" / "competitor" / video_id)
    metadata_file = cache_dir / "metadata.json"

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
            resp = requests.get(url, params=params, timeout=10)
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
                    LOGGER.info(f"Successfully retrieved metadata via YouTube Data API for video: {video_id}")
                else:
                    LOGGER.warning(f"Video {video_id} not found in YouTube Data API response.")
            else:
                LOGGER.warning(f"YouTube Data API returned status {resp.status_code}: {resp.text}")
        except Exception as exc:
            LOGGER.warning(f"Error calling YouTube Data API: {exc}")

    # Fallback to oEmbed and video page parsing if metadata title is empty
    if not metadata["title"]:
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            oembed_resp = requests.get(oembed_url, timeout=10)
            if oembed_resp.status_code == 200:
                oembed_data = oembed_resp.json()
                metadata["title"] = oembed_data.get("title", "")
                metadata["channelTitle"] = oembed_data.get("author_name", "")
                metadata["source"] = "oembed_fallback"
                LOGGER.info(f"Retrieved basic title metadata via oEmbed for {video_id}")
        except Exception as exc:
            LOGGER.warning(f"oEmbed metadata fallback failed: {exc}")

    # Save to cache
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    log_audit_trail(video_id, "METADATA_EXTRACTED", {
        "title": metadata.get("title"),
        "channel": metadata.get("channelTitle"),
        "has_tags": len(metadata.get("tags", [])) > 0,
    })

    return metadata


def fetch_transcript(video_id: str) -> Optional[Dict[str, Any]]:
    """Step 2: Pull timestamped transcript using youtube-transcript-api.

    Saves to cache/competitor/{video_id}/transcript.json marked as 'reference-only, do not quote'.
    Returns transcript data dict or None if unavailable.
    """
    cache_dir = ensure_dir(get_project_root() / "cache" / "competitor" / video_id)
    transcript_file = cache_dir / "transcript.json"

    transcript_data: Optional[Dict[str, Any]] = None

    if YouTubeTranscriptApi is None:
        LOGGER.warning("youtube-transcript-api is not installed. Skipping transcript fetch.")
        return None

    try:
        raw_entries = None
        
        # Check if get_transcript exists (v0.6+)
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            raw_entries = YouTubeTranscriptApi.get_transcript(video_id)
        elif hasattr(YouTubeTranscriptApi, "fetch"):
            # v1.0+ class or instance method
            try:
                fetched = YouTubeTranscriptApi().fetch(video_id)
            except TypeError:
                fetched = YouTubeTranscriptApi.fetch(video_id)
            if hasattr(fetched, "to_raw_data"):
                raw_entries = fetched.to_raw_data()
            elif hasattr(fetched, "fetch"):
                raw_entries = fetched.fetch()
            else:
                raw_entries = list(fetched)
        else:
            api_instance = YouTubeTranscriptApi()
            fetched = api_instance.fetch(video_id)
            raw_entries = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else list(fetched)

        # Standardize entry structure
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

        LOGGER.info(f"Successfully fetched transcript with {len(formatted_entries)} entries for video {video_id}")
        log_audit_trail(video_id, "TRANSCRIPT_EXTRACTED", {
            "entry_count": len(formatted_entries),
            "duration_seconds": round(total_duration, 2),
            "notice": "reference-only, do not quote",
        })

    except Exception as exc:
        LOGGER.warning(f"No available transcript/captions for video {video_id} ({exc}). Falling back to metadata-only analysis.")
        log_audit_trail(video_id, "TRANSCRIPT_FETCH_FAILED_FALLBACK_TO_METADATA", {
            "error": str(exc)
        })
        transcript_data = None

    return transcript_data


def extract_title_thumbnail_pattern(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Step 5: Extract light style hints from title, description, and tags."""
    title = metadata.get("title", "")
    has_numbers = bool(re.search(r"\d+", title))
    has_brackets = bool(re.search(r"[\[\]\(\)\{\}]", title))
    has_emojis = bool(re.search(r"[\U00010000-\U0010ffff]", title))

    # Capitalization style
    if title.isupper() and len(title) > 3:
        caps_style = "ALL_CAPS"
    elif title.istitle():
        caps_style = "Title Case"
    elif title.islower():
        caps_style = "lowercase"
    else:
        caps_style = "Mixed Case / Standard"

    # Tag themes
    tags = metadata.get("tags", [])
    tag_themes = tags[:8] if tags else []

    return {
        "title_length_chars": len(title),
        "title_word_count": len(title.split()),
        "capitalization_style": caps_style,
        "has_numbers": has_numbers,
        "has_brackets": has_brackets,
        "has_emojis": has_emojis,
        "tag_themes": tag_themes,
    }


def parse_iso8601_duration(duration_str: str) -> int:
    """Convert ISO 8601 duration (e.g., PT12M30S) to seconds."""
    if not duration_str:
        return 0
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def analyze_structure_with_gemini(
    metadata: Dict[str, Any],
    transcript_data: Optional[Dict[str, Any]],
    gemini_api_key: Optional[str] = None,
    gemini_model: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    """Step 3: Analyze structural and format DNA with Gemini.

    Strict guardrail: Prompt explicitly forbids copying or summarizing specific content.
    """
    video_id = metadata.get("video_id", "unknown")
    api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    title_pattern_hints = extract_title_thumbnail_pattern(metadata)

    # Prepare condensed transcript representation for structure analysis
    transcript_summary_for_prompt = ""
    if transcript_data and transcript_data.get("entries"):
        entries = transcript_data["entries"]
        total_duration = transcript_data.get("estimated_duration_seconds", 0)
        
        # Sample or summarize timestamps to show pacing without overwhelming tokens
        sample_size = min(len(entries), 100)
        step = max(1, len(entries) // sample_size)
        sampled = entries[::step]
        
        lines = []
        for e in sampled:
            start_m = int(e.get("start", 0) // 60)
            start_s = int(e.get("start", 0) % 60)
            text_snippet = e.get("text", "").replace("\n", " ").strip()
            # Keep snippets concise to emphasize timing/cadence rather than full text
            short_text = text_snippet[:60]
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
(1) The hook style used in the first 15-30 seconds (e.g. bold claim, cold open question, high-energy teaser, relatable dilemma).
(2) How many main sections/beats the video has and roughly how long each is.
(3) The pacing pattern (e.g. fast rapid-fire cuts, structured step-by-step, deep-dive narrative, escalating tension).
(4) The overall tone (e.g. authoritative & educational, dramatic & cinematic, casual & conversational, urgent).
(5) The title formula pattern (e.g. 'Number + Superlative + Topic', 'Why X is Failing', 'How to X in Y Steps').
(6) What type of call-to-action or ending style it uses (e.g. soft community question, hard subscribe cliffhanger, resource download).

Do NOT summarize or reproduce the actual content/story — only describe the structural pattern in abstract terms.

VIDEO METADATA (Reference only):
- Title: {metadata.get('title')}
- Description excerpt: {metadata.get('description', '')[:200]}...
- Tags: {', '.join(metadata.get('tags', [])[:10])}
- Known Duration: ~{raw_duration_sec} seconds
- Title Pattern Characteristics: {json.dumps(title_pattern_hints)}

TIMESTAMPS & PACING SAMPLES (Structure reference only):
{transcript_summary_for_prompt}

Return ONLY valid JSON matching this exact schema:
{{
  "hook_style": "string description of the hook mechanism",
  "section_count": <integer number of distinct sections/beats>,
  "section_pacing": [
    "Beat 1: Hook and premise introduction (approx 0-30s)",
    "Beat 2: Core problem breakdown...",
    ...
  ],
  "tone": "string describing tone and delivery style",
  "title_formula": "string describing the title template/formula",
  "avg_section_length_seconds": <integer average section duration>,
  "ending_style": "string describing the CTA and closing pattern",
  "estimated_total_length_seconds": <integer total estimated duration>
}}
"""

    style_template: Dict[str, Any] = {}

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
                    temperature=0.2,
                ),
            )
            raw_text = response.text.strip()
            style_template = json.loads(raw_text)
            LOGGER.info("Successfully received structured style template from Gemini API.")
        except Exception as exc:
            LOGGER.warning(f"Gemini API call failed ({exc}). Falling back to algorithmic format heuristic.")
            style_template = _heuristic_style_template(metadata, transcript_data, title_pattern_hints, raw_duration_sec)
    else:
        LOGGER.info("No GEMINI_API_KEY detected. Generating structural template using built-in format heuristics.")
        style_template = _heuristic_style_template(metadata, transcript_data, title_pattern_hints, raw_duration_sec)

    # Attach title and thumbnail pattern metadata
    style_template["title_thumbnail_pattern"] = title_pattern_hints
    style_template["source_video_id"] = video_id
    style_template["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    style_template["guardrail_compliance"] = (
        "Strict format DNA only. No verbatim competitor dialogue or proprietary content."
    )

    # Save to cache
    cache_dir = ensure_dir(get_project_root() / "cache" / "competitor" / video_id)
    template_file = cache_dir / "style_template.json"
    with open(template_file, "w", encoding="utf-8") as f:
        json.dump(style_template, f, indent=2, ensure_ascii=False)

    log_audit_trail(video_id, "STYLE_TEMPLATE_GENERATED", {
        "hook_style": style_template.get("hook_style"),
        "section_count": style_template.get("section_count"),
        "tone": style_template.get("tone"),
        "title_formula": style_template.get("title_formula"),
    })

    return style_template


def _heuristic_style_template(
    metadata: Dict[str, Any],
    transcript_data: Optional[Dict[str, Any]],
    title_pattern: Dict[str, Any],
    duration_sec: int,
) -> Dict[str, Any]:
    """Deterministic fallback format template generator when API key is unavailable."""
    title = metadata.get("title", "")
    
    # Infer title formula
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

    return {
        "hook_style": "High-impact opening question posing the central challenge within 15 seconds.",
        "section_count": section_count,
        "section_pacing": [
            f"Beat {i+1}: {'Context & Problem Setup' if i==0 else ('Key Strategic Insight' if i < section_count-1 else 'Actionable Conclusion & Next Steps')} (~{avg_len}s)"
            for i in range(section_count)
        ],
        "tone": "Authoritative, educational, and engaging with concise explanations.",
        "title_formula": formula,
        "avg_section_length_seconds": avg_len,
        "ending_style": "Key takeaway summary followed by a targeted call-to-action question.",
        "estimated_total_length_seconds": total_sec,
    }


def analyze_competitor_video(
    url_or_id: str,
    youtube_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    output_path: Optional[str] = None,
) -> str:
    """End-to-end competitor video analysis.

    Returns the absolute path to the generated style_template.json.
    """
    video_id = extract_video_id(url_or_id)
    LOGGER.info(f"Starting competitor format analysis for video ID: {video_id}")

    # Step 1: Metadata
    metadata = fetch_public_metadata(video_id, api_key=youtube_api_key)

    # Step 2: Transcript
    transcript_data = fetch_transcript(video_id)

    # Step 3 & 5: Structural Analysis
    style_template = analyze_structure_with_gemini(
        metadata=metadata,
        transcript_data=transcript_data,
        gemini_api_key=gemini_api_key,
    )

    # Save to custom output path if requested
    if output_path:
        out_file = Path(output_path).resolve()
        ensure_dir(out_file.parent)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(style_template, f, indent=2, ensure_ascii=False)
        target_path = str(out_file)
    else:
        target_path = str(get_project_root() / "cache" / "competitor" / video_id / "style_template.json")

    LOGGER.info(f"Style template successfully generated: {target_path}")
    return target_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze YouTube video structural DNA and output a reusable style template."
    )
    parser.add_argument(
        "--url",
        "-u",
        required=True,
        help="YouTube video URL or 11-character Video ID.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Optional custom output path for style_template.json.",
    )
    args = parser.parse_args()

    try:
        template_path = analyze_competitor_video(
            url_or_id=args.url,
            output_path=args.output,
        )
        print(template_path)
    except Exception as exc:
        LOGGER.error(f"Analysis failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
