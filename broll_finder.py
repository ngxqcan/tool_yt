"""Stock B-Roll & Footage Finder Module.

Searches for free HD stock footage via Pexels API / Pixabay API matching script visual cues.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from dotenv import load_dotenv

from utils import ensure_dir, get_project_root, retry_with_backoff, setup_logging

load_dotenv()
LOGGER = setup_logging("broll_finder")


@retry_with_backoff(max_retries=3, initial_delay=1.0)
def search_pexels_videos(query: str, api_key: Optional[str] = None, per_page: int = 3) -> List[Dict[str, Any]]:
    """Search for free HD stock video clips via Pexels Video API."""
    key = api_key or os.getenv("PEXELS_API_KEY")
    if not key:
        LOGGER.info(f"No PEXELS_API_KEY provided. Returning curated search queries for: '{query}'")
        return [
            {
                "id": "mock_1",
                "title": f"Stock footage match for '{query}'",
                "duration": 15,
                "video_url": f"https://www.pexels.com/search/videos/{query.replace(' ', '%20')}/",
                "download_url": None,
            }
        ]

    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": key}
    params = {"query": query, "per_page": per_page, "orientation": "landscape"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for v in data.get("videos", []):
                # Get best HD video file
                files = v.get("video_files", [])
                hd_file = next((f for f in files if f.get("quality") == "hd" and f.get("width", 0) >= 1280), None)
                if not hd_file and files:
                    hd_file = files[0]

                results.append({
                    "id": str(v.get("id")),
                    "duration": v.get("duration", 10),
                    "video_url": v.get("url"),
                    "download_url": hd_file.get("link") if hd_file else None,
                    "width": hd_file.get("width") if hd_file else 1920,
                    "height": hd_file.get("height") if hd_file else 1080,
                })
            LOGGER.info(f"Found {len(results)} stock video(s) for query: '{query}'")
            return results
        else:
            LOGGER.warning(f"Pexels API error {resp.status_code}: {resp.text[:100]}")
            return []
    except Exception as exc:
        LOGGER.warning(f"Failed to query Pexels API: {exc}")
        return []


def download_broll_clip(download_url: str, output_path: str) -> Optional[Path]:
    """Download an HD stock video file locally."""
    if not download_url:
        return None
    out_file = Path(output_path).resolve()
    ensure_dir(out_file.parent)

    try:
        LOGGER.info(f"Downloading B-roll clip to {out_file.name}...")
        resp = requests.get(download_url, stream=True, timeout=30)
        if resp.status_code == 200:
            with open(out_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            LOGGER.info(f"Downloaded B-roll clip: {out_file}")
            return out_file
    except Exception as exc:
        LOGGER.warning(f"Could not download B-roll from {download_url}: {exc}")
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Find free HD stock B-roll clips for video beats.")
    parser.add_argument("--query", "-q", required=True, help="Visual keyword or scene description.")
    parser.add_argument("--count", type=int, default=3, help="Max results (default: 3).")
    args = parser.parse_args()

    try:
        clips = search_pexels_videos(args.query, per_page=args.count)
        print(f"\nFound {len(clips)} B-roll clips for '{args.query}':")
        for idx, c in enumerate(clips, 1):
            print(f"{idx}. {c.get('title', 'HD Stock Clip')} (Duration: {c.get('duration')}s)")
            print(f"   URL: {c.get('video_url')}")
            if c.get("download_url"):
                print(f"   Download link: {c.get('download_url')}")
    except Exception as exc:
        LOGGER.error(f"B-roll search failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
