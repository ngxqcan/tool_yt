"""Automated Video Assembler & Render Engine Module.

Combines TTS voiceover audio, generated slide/B-roll visuals, and on-screen caption overlays
into a finalized 1080p MP4 video using MoviePy and Pillow.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from utils import ensure_dir, get_project_root, setup_logging

LOGGER = setup_logging("video_assembler")


def render_slide_image(
    title: str,
    subtitle: str,
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    bg_color: str = "#0f172a",
    accent_color: str = "#38bdf8",
) -> Path:
    """Render a clean 1080p background slide image using Pillow."""
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Gradient-style geometry
    draw.rectangle([(0, 0), (width, 20)], fill=accent_color)
    draw.ellipse([(width - 500, -100), (width + 300, 600)], fill="#1e293b")
    draw.ellipse([(-150, height - 400), (450, height + 200)], fill="#334155")
    draw.line([(100, height - 100), (width - 100, height - 100)], fill=accent_color, width=8)

    try:
        font_title = ImageFont.load_default(size=64)
        font_sub = ImageFont.load_default(size=36)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    # Draw centered text
    draw.text((120, height // 2 - 80), title.upper()[:50], fill=accent_color, font=font_title)
    if subtitle:
        draw.text((120, height // 2 + 30), subtitle[:80], fill="#f8fafc", font=font_sub)

    ensure_dir(output_path.parent)
    img.save(str(output_path))
    return output_path


def assemble_video(
    audio_path: str,
    title: str,
    subtitle: str = "",
    output_video_path: Optional[str] = None,
    fps: int = 24,
) -> Path:
    """Assemble audio and generated background into an MP4 video."""
    audio_file = Path(audio_path).resolve()
    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file not found at: {audio_path}")

    out_file = Path(output_video_path) if output_video_path else ensure_dir(get_project_root() / "output" / "rendered") / f"{audio_file.stem}_video.mp4"
    ensure_dir(out_file.parent)

    slide_img_path = ensure_dir(get_project_root() / "cache" / "slides") / f"{audio_file.stem}_slide.png"
    render_slide_image(title, subtitle, slide_img_path)

    LOGGER.info(f"Assembling video from {audio_file.name} and {slide_img_path.name}...")

    try:
        # Import moviepy safely across versions
        from moviepy import AudioFileClip, ImageClip

        audio_clip = AudioFileClip(str(audio_file))
        duration = audio_clip.duration

        # Create Image Clip matching audio duration
        img_clip = ImageClip(str(slide_img_path)).with_duration(duration) if hasattr(ImageClip, "with_duration") else ImageClip(str(slide_img_path)).set_duration(duration)
        
        # Set audio
        video_clip = img_clip.with_audio(audio_clip) if hasattr(img_clip, "with_audio") else img_clip.set_audio(audio_clip)

        LOGGER.info(f"Rendering 1080p video ({duration:.1f}s, {fps} fps)...")
        video_clip.write_videofile(
            str(out_file),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            logger=None,
        )

        audio_clip.close()
        video_clip.close()
        LOGGER.info(f"Video assembly successfully completed: {out_file}")
        return out_file

    except Exception as exc:
        LOGGER.error(f"MoviePy video rendering failed ({exc}).")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble voiceover audio and slide visual into an MP4 video.")
    parser.add_argument("--audio", "-a", required=True, help="Path to voiceover MP3 file.")
    parser.add_argument("--title", "-t", required=True, help="Main title to display on screen.")
    parser.add_argument("--subtitle", "-s", default="", help="Subtitle / tagline.")
    parser.add_argument("--output", "-o", default=None, help="Output MP4 path.")
    args = parser.parse_args()

    try:
        res = assemble_video(audio_path=args.audio, title=args.title, subtitle=args.subtitle, output_video_path=args.output)
        print(f"Rendered video saved at: {res}")
    except Exception as exc:
        LOGGER.error(f"Assembly failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
