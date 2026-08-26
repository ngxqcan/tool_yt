"""Channel Crawler & Viral Outlier Video Detector Module.

Scrapes recent videos from a YouTube channel, computes channel baseline metrics,
and identifies high-leverage Outlier Videos (3x-10x+ views above channel average).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

from models import ChannelAnalysisModel, OutlierVideoModel
from utils import ensure_dir, get_project_root, retry_with_backoff, setup_logging

load_dotenv()
LOGGER = setup_logging("channel_crawler")


@retry_with_backoff(max_retries=3, initial_delay=1.0)
def _call_youtube_api(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute authenticated YouTube Data API v3 request with retries."""
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}"
    resp = requests.get(url, params=params, timeout=10)
    if resp.status_code != 200:
        raise requests.RequestException(f"YouTube API [{endpoint}] failed ({resp.status_code}): {resp.text[:120]}")
    return resp.json()


def resolve_channel_id(channel_input: str, api_key: str) -> Tuple[str, str, str]:
    """Resolve channel ID, title, and uploads playlist ID from handle, URL, or ID."""
    clean = channel_input.strip()
    if clean.startswith("https://"):
        if "/@" in clean:
            handle = clean.split("/@")[1].split("/")[0].split("?")[0]
            clean = f"@{handle}"
        elif "/channel/" in clean:
            clean = clean.split("/channel/")[1].split("/")[0].split("?")[0]

    # If it's a handle
    if clean.startswith("@"):
        params = {"part": "snippet,contentDetails", "forHandle": clean, "key": api_key}
        data = _call_youtube_api("channels", params)
        items = data.get("items", [])
        if not items:
            # Fallback search
            search_params = {"part": "snippet", "q": clean, "type": "channel", "maxResults": 1, "key": api_key}
            s_data = _call_youtube_api("search", search_params)
            s_items = s_data.get("items", [])
            if not s_items:
                raise ValueError(f"Could not resolve channel handle: {clean}")
            cid = s_items[0]["snippet"]["channelId"]
            return resolve_channel_id(cid, api_key)

        item = items[0]
        cid = item["id"]
        title = item["snippet"]["title"]
        uploads_id = item["contentDetails"]["relatedPlaylists"]["uploads"]
        return cid, title, uploads_id

    # If it's direct Channel ID
    params = {"part": "snippet,contentDetails", "id": clean, "key": api_key}
    data = _call_youtube_api("channels", params)
    items = data.get("items", [])
    if not items:
        raise ValueError(f"Channel not found: {channel_input}")

    item = items[0]
    cid = item["id"]
    title = item["snippet"]["title"]
    uploads_id = item["contentDetails"]["relatedPlaylists"]["uploads"]
    return cid, title, uploads_id


def crawl_channel_outliers(
    channel_input: str,
    api_key: Optional[str] = None,
    max_videos: int = 50,
    min_outlier_multiplier: float = 2.0,
) -> ChannelAnalysisModel:
    """Crawl recent channel uploads, compute baseline view metrics, and identify outlier videos."""
    raw_key = api_key or os.getenv("YOUTUBE_API_KEY")
    key = raw_key if raw_key and not raw_key.lower().startswith("your_") else None
    if not key:
        LOGGER.warning("No YOUTUBE_API_KEY configured. Generating mock channel outlier analysis.")
        return _mock_channel_analysis(channel_input)

    LOGGER.info(f"Resolving channel: {channel_input}...")
    channel_id, channel_title, uploads_id = resolve_channel_id(channel_input, key)
    LOGGER.info(f"Connected to '{channel_title}' (ID: {channel_id}). Fetching recent uploads...")

    # Fetch playlist items from uploads playlist
    video_ids: List[str] = []
    page_token = None
    while len(video_ids) < max_videos:
        p_params = {
            "part": "contentDetails",
            "playlistId": uploads_id,
            "maxResults": min(50, max_videos - len(video_ids)),
            "key": key,
        }
        if page_token:
            p_params["pageToken"] = page_token

        data = _call_youtube_api("playlistItems", p_params)
        items = data.get("items", [])
        if not items:
            break

        for it in items:
            video_ids.append(it["contentDetails"]["videoId"])

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    LOGGER.info(f"Fetched {len(video_ids)} video IDs. Pulling video statistics...")

    # Fetch stats in chunks of 50
    video_records: List[Dict[str, Any]] = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        v_params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(chunk),
            "key": key,
        }
        v_data = _call_youtube_api("videos", v_params)
        for it in v_data.get("items", []):
            stats = it.get("statistics", {})
            snippet = it.get("snippet", {})
            video_records.append({
                "video_id": it["id"],
                "title": snippet.get("title", ""),
                "published_at": snippet.get("publishedAt", ""),
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "url": f"https://www.youtube.com/watch?v={it['id']}",
            })

    if not video_records:
        raise ValueError("No video records found for this channel.")

    # Compute baseline metrics
    views = [v["view_count"] for v in video_records if v["view_count"] > 0]
    avg_views = sum(views) / len(views) if views else 1.0
    sorted_views = sorted(views)
    median_views = sorted_views[len(sorted_views) // 2] if sorted_views else 1.0

    LOGGER.info(f"Channel Average Views: {avg_views:,.0f} | Median: {median_views:,.0f}")

    # Extract Outliers
    outliers: List[OutlierVideoModel] = []
    all_words: List[str] = []

    for v in video_records:
        score = v["view_count"] / avg_views if avg_views > 0 else 0.0
        if score >= min_outlier_multiplier:
            outliers.append(OutlierVideoModel(
                video_id=v["video_id"],
                title=v["title"],
                url=v["url"],
                view_count=v["view_count"],
                published_at=v["published_at"],
                outlier_score=round(score, 2),
                like_count=v["like_count"],
            ))
            # Track words in outlier titles
            words = [w.lower() for w in re.findall(r"\w+", v["title"]) if len(w) > 3]
            all_words.extend(words)

    # Sort outliers by multiplier descending
    outliers.sort(key=lambda o: o.outlier_score, reverse=True)

    # Extract recurring keywords
    from collections import Counter
    top_keywords = [word for word, count in Counter(all_words).most_common(8)]

    analysis = ChannelAnalysisModel(
        channel_id=channel_id,
        channel_title=channel_title,
        total_videos_analyzed=len(video_records),
        average_view_count=round(avg_views, 2),
        median_view_count=float(median_views),
        outlier_videos=outliers,
        dominant_title_keywords=top_keywords,
    )

    # Cache analysis
    cache_dir = ensure_dir(get_project_root() / "cache" / "channel" / channel_id)
    cache_file = cache_dir / "outliers.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(analysis.model_dump_json(indent=2))

    LOGGER.info(f"Identified {len(outliers)} viral outlier video(s). Saved analysis to: {cache_file}")
    return analysis


def _mock_channel_analysis(channel_input: str) -> ChannelAnalysisModel:
    """Mock analysis when YouTube API key is not present."""
    return ChannelAnalysisModel(
        channel_id="mock_channel_123",
        channel_title=channel_input or "Tech Mastery Channel",
        total_videos_analyzed=30,
        average_view_count=25000.0,
        median_view_count=18000.0,
        outlier_videos=[
            OutlierVideoModel(
                video_id="dQw4w9WgXcQ",
                title="The 1 Secret Nobody Tells You About Python Architecture (2026)",
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                view_count=128000,
                published_at="2026-01-15T10:00:00Z",
                outlier_score=5.12,
                like_count=8500,
            ),
            OutlierVideoModel(
                video_id="dQw4w9WgXcQ",
                title="Why 90% of AI Startups Will Die This Year",
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                view_count=82000,
                published_at="2026-02-01T14:30:00Z",
                outlier_score=3.28,
                like_count=4200,
            ),
        ],
        dominant_title_keywords=["python", "architecture", "startups", "secret"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Find viral outlier videos across a YouTube channel.")
    parser.add_argument("--channel", "-c", required=True, help="Channel handle (@creator), URL, or Channel ID.")
    parser.add_argument("--max-videos", type=int, default=50, help="Number of recent videos to analyze (default: 50).")
    parser.add_argument("--min-score", type=float, default=2.0, help="Minimum outlier multiplier (default: 2.0x avg).")
    args = parser.parse_args()

    try:
        res = crawl_channel_outliers(
            channel_input=args.channel,
            max_videos=args.max_videos,
            min_outlier_multiplier=args.min_score,
        )
        print("\n================ CHANNEL OUTLIER REPORT ================")
        print(f"Channel: {res.channel_title} ({res.channel_id})")
        print(f"Average Views: {res.average_view_count:,.0f} | Median: {res.median_view_count:,.0f}")
        print(f"Found {len(res.outlier_videos)} Viral Outliers (>={args.min_score}x avg):")
        for idx, out in enumerate(res.outlier_videos, 1):
            print(f"\n{idx}. [{out.outlier_score}x Outlier] {out.title}")
            print(f"   Views: {out.view_count:,} | URL: {out.url}")
        print(f"\nDominant Outlier Keywords: {', '.join(res.dominant_title_keywords)}")
        print("========================================================\n")
    except Exception as exc:
        LOGGER.error(f"Channel crawling failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
