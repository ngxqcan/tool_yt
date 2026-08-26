"""YouTube Video Uploader Module.

Uploads generated video files, thumbnails, and metadata directly to YouTube via YouTube Data API v3 OAuth 2.0.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils import ensure_dir, get_project_root, setup_logging

LOGGER = setup_logging("youtube_uploader")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_authenticated_service(client_secrets_file: Optional[str] = None) -> Any:
    """Authenticate with YouTube Data API v3 using OAuth 2.0."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request
        import pickle

        secrets_path = client_secrets_file or os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json")
        token_pickle = get_project_root() / "token.pickle"

        creds = None
        if token_pickle.exists():
            with open(token_pickle, "rb") as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not Path(secrets_path).exists():
                    raise FileNotFoundError(
                        f"OAuth Client Secrets file not found at: {secrets_path}. "
                        "Please download client_secrets.json from Google Cloud Console."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(token_pickle, "wb") as token:
                pickle.dump(creds, token)

        return build("youtube", "v3", credentials=creds)

    except ImportError:
        LOGGER.error("google-auth-oauthlib or google-api-python-client not installed.")
        raise


def upload_video(
    file_path: str,
    title: str,
    description: str,
    tags: Optional[List[str]] = None,
    category_id: str = "28",  # 28 = Science & Technology
    privacy_status: str = "private",  # private, public, unlisted
    client_secrets_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload a video file to YouTube with resumable chunking."""
    from googleapiclient.http import MediaFileUpload

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Video file not found at: {file_path}")

    LOGGER.info(f"Authenticating and preparing upload for '{title}' ({path.name})...")
    youtube = get_authenticated_service(client_secrets_file)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(path),
        chunksize=1024 * 1024 * 5,  # 5MB chunks
        resumable=True,
    )

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    LOGGER.info("Uploading video chunks to YouTube...")
    while response is None:
        status, response = request.next_chunk()
        if status:
            LOGGER.info(f"Uploaded {int(status.progress() * 100)}%")

    video_id = response.get("id")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    LOGGER.info(f"Upload complete! Video ID: {video_id} -> {video_url}")
    return response


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload video directly to YouTube via Data API v3.")
    parser.add_argument("--file", "-f", required=True, help="Path to video file (.mp4, .mov, etc.)")
    parser.add_argument("--title", "-t", required=True, help="Video title")
    parser.add_argument("--description", "-d", default="", help="Video description")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--privacy", default="private", choices=["private", "public", "unlisted"])
    parser.add_argument("--secrets", default=None, help="Path to client_secrets.json")
    args = parser.parse_args()

    tag_list = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    try:
        res = upload_video(
            file_path=args.file,
            title=args.title,
            description=args.description,
            tags=tag_list,
            privacy_status=args.privacy,
            client_secrets_file=args.secrets,
        )
        print(f"Successfully uploaded: https://www.youtube.com/watch?v={res.get('id')}")
    except Exception as exc:
        LOGGER.error(f"Upload failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
