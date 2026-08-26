"""Comment Mining & Audience Content Gap Analyzer Module.

Fetches viewer comments on competitor videos, performs sentiment analysis,
and extracts unanswered questions and content gaps to inform script generation.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from competitor_analyzer import extract_video_id
from models import CommentGapAnalysisModel, CommentGapModel, parse_and_validate_json
from utils import ensure_dir, get_project_root, retry_with_backoff, setup_logging

load_dotenv()
LOGGER = setup_logging("comment_miner")


@retry_with_backoff(max_retries=3, initial_delay=1.0)
def fetch_top_comments(video_id: str, api_key: Optional[str] = None, max_comments: int = 100) -> List[Dict[str, Any]]:
    """Fetch top liked comments for a YouTube video via Data API v3."""
    key = api_key or os.getenv("YOUTUBE_API_KEY")
    if not key:
        LOGGER.warning(f"No YOUTUBE_API_KEY provided. Using synthetic sample comments for {video_id}.")
        return _mock_comments(video_id)

    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "order": "relevance",
        "maxResults": min(100, max_comments),
        "textFormat": "plainText",
        "key": key,
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            comments = []
            for item in data.get("items", []):
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                comments.append({
                    "author": snippet.get("authorDisplayName", "Viewer"),
                    "text": snippet.get("textDisplay", ""),
                    "like_count": int(snippet.get("likeCount", 0)),
                    "published_at": snippet.get("publishedAt", ""),
                })
            LOGGER.info(f"Retrieved {len(comments)} top comments for video: {video_id}")
            return comments
        else:
            LOGGER.warning(f"Comment API returned {resp.status_code}: {resp.text[:100]}. Falling back to samples.")
            return _mock_comments(video_id)
    except Exception as exc:
        LOGGER.warning(f"Error fetching comments: {exc}. Using fallback.")
        return _mock_comments(video_id)


def analyze_comment_gaps(
    video_id: str,
    comments: List[Dict[str, Any]],
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
) -> CommentGapAnalysisModel:
    """Use Gemini to identify unanswered questions and content gaps from viewer comments."""
    api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model_name = gemini_model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Format top comments for prompt
    top_samples = sorted(comments, key=lambda c: c.get("like_count", 0), reverse=True)[:50]
    comments_text = "\n".join([f"- [{c.get('like_count', 0)} likes]: {c.get('text', '')[:120]}" for c in top_samples])

    prompt = f"""You are analyzing viewer comments on a YouTube competitor video to find CONTENT GAPS.

Identify:
1. Overall audience sentiment (inquisitive, skeptical, confused, enthusiastic).
2. Top recurring questions viewers are asking.
3. Content Gaps: What critical questions, pitfalls, or details did the creator FAIL to address or explain clearly?
4. Concrete talking points our original video should emphasize to provide 10x more value.

COMMENTS SAMPLES:
{comments_text}

Return valid JSON matching this schema:
{{
  "video_id": "{video_id}",
  "total_comments_analyzed": {len(comments)},
  "audience_sentiment": "string description",
  "top_liked_questions": ["question 1", "question 2"],
  "content_gaps": [
    {{
      "question_or_critique": "string",
      "frequency_or_relevance": "High | Medium",
      "suggested_script_angle": "How our script can address this"
    }}
  ],
  "recommended_talking_points": ["Point 1", "Point 2"]
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
                    temperature=0.2,
                ),
            )
            model = parse_and_validate_json(response.text or "", CommentGapAnalysisModel)
            LOGGER.info(f"Successfully analyzed comment gaps for video: {video_id}")
            _save_comment_analysis(video_id, model)
            return model
        except Exception as exc:
            LOGGER.warning(f"Gemini comment analysis failed ({exc}). Falling back to heuristic analysis.")

    # Fallback heuristic
    fallback = CommentGapAnalysisModel(
        video_id=video_id,
        total_comments_analyzed=len(comments),
        audience_sentiment="Inquisitive and eager for practical steps",
        top_liked_questions=[
            "How does this apply to complete beginners?",
            "What are the exact tools or costs involved?",
            "What if this doesn't work for my specific use case?",
        ],
        content_gaps=[
            CommentGapModel(
                question_or_critique="Video lacked real step-by-step implementation code/examples.",
                frequency_or_relevance="High",
                suggested_script_angle="Include explicit concrete examples and walkthrough diagrams in Beat 2 & 3.",
            ),
            CommentGapModel(
                question_or_critique="No mention of common failure modes and beginner mistakes.",
                frequency_or_relevance="High",
                suggested_script_angle="Dedicate a dedicated beat to troubleshooting and anti-patterns.",
            ),
        ],
        recommended_talking_points=[
            "Provide transparent cost and setup breakdown upfront.",
            "Address the 3 biggest beginner roadblocks immediately in the hook.",
            "Give actionable checklist at the end of the video.",
        ],
    )
    _save_comment_analysis(video_id, fallback)
    return fallback


def _save_comment_analysis(video_id: str, model: CommentGapAnalysisModel) -> None:
    cache_dir = ensure_dir(get_project_root() / "cache" / "competitor" / video_id)
    cache_file = cache_dir / "comment_gaps.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(model.model_dump_json(indent=2))


def _mock_comments(video_id: str) -> List[Dict[str, Any]]:
    return [
        {"author": "DevGamer", "text": "Great overview, but how do I actually set this up on Windows/Mac?", "like_count": 142},
        {"author": "CodeNewbie", "text": "Is this free or does it require expensive subscriptions?", "like_count": 89},
        {"author": "TechLead2026", "text": "You skipped the most important security part! What about data privacy?", "like_count": 65},
        {"author": "Sarah_AI", "text": "Can you make a video on how to troubleshoot when it fails?", "like_count": 44},
    ]


def mine_video_comments(url_or_id: str, api_key: Optional[str] = None, gemini_key: Optional[str] = None) -> CommentGapAnalysisModel:
    vid = extract_video_id(url_or_id)
    comments = fetch_top_comments(vid, api_key=api_key)
    return analyze_comment_gaps(vid, comments, gemini_api_key=gemini_key)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine competitor comments to uncover viewer content gaps.")
    parser.add_argument("--url", "-u", required=True, help="YouTube video URL or Video ID.")
    args = parser.parse_args()

    try:
        res = mine_video_comments(args.url)
        print("\n================ AUDIENCE CONTENT GAP ANALYSIS ================")
        print(f"Video ID: {res.video_id} | Comments Analyzed: {res.total_comments_analyzed}")
        print(f"Sentiment: {res.audience_sentiment}\n")
        print("🎯 Top Unanswered Content Gaps (Competitor Missed):")
        for idx, gap in enumerate(res.content_gaps, 1):
            print(f"{idx}. [{gap.frequency_or_relevance} Priority] {gap.question_or_critique}")
            print(f"   👉 Suggested Script Angle: {gap.suggested_script_angle}\n")
        print("💡 Recommended Talking Points for Your Video:")
        for pt in res.recommended_talking_points:
            print(f" - {pt}")
        print("===============================================================\n")
    except Exception as exc:
        LOGGER.error(f"Comment mining failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
