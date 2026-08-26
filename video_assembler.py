"""Automated 1080p MP4 Video Compositor & Kinetic Subtitle Engine.

Combines AI-generated scene visuals, studio voiceovers (with BGM & ducking),
and MrBeast-style bold neon subtitles into full 1080p MP4 videos.
Supports both 16:9 widescreen long-form videos and 9:16 vertical Shorts.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from audio_mixer import mix_voiceover_with_bgm_and_sfx
from image_generator import generate_images_for_script, generate_single_image
from models import GeneratedScriptModel
from utils import ensure_dir, get_output_dir, get_project_root, setup_logging

load_dotenv()
LOGGER = setup_logging("video_assembler")


def render_kinetic_subtitle_frame(
    base_image_path: Path,
    caption_text: str,
    output_frame_path: Path,
    width: int = 1920,
    height: int = 1080,
    highlight_color: str = "#FFE600",
    stroke_width: int = 6,
) -> Path:
    """Overlay MrBeast-style high-contrast kinetic subtitles onto a scene image."""
    try:
        base_img = Image.open(str(base_image_path)).convert("RGBA")
        if base_img.size != (width, height):
            base_img = base_img.resize((width, height), Image.Resampling.LANCZOS)
    except Exception:
        base_img = Image.new("RGBA", (width, height), color=(15, 23, 42, 255))

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Word wrapping
    words = caption_text.strip().split()
    lines: List[str] = []
    curr_line: List[str] = []
    max_chars_per_line = 32 if width > height else 18

    for w in words:
        if len(" ".join(curr_line + [w])) <= max_chars_per_line:
            curr_line.append(w)
        else:
            if curr_line:
                lines.append(" ".join(curr_line))
            curr_line = [w]
    if curr_line:
        lines.append(" ".join(curr_line))

    # Font size
    font_size = 54 if width > height else 64
    try:
        # Try system bold font or default
        font = ImageFont.truetype("arialbd.ttf", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

    line_height = int(font_size * 1.3)
    total_text_height = len(lines) * line_height
    start_y = height - total_text_height - (140 if width > height else 280)

    # Render each line with heavy black stroke
    for i, line in enumerate(lines):
        # Calculate line width for centering
        try:
            bbox = font.getbbox(line)
            w_line = bbox[2] - bbox[0]
        except Exception:
            w_line = len(line) * (font_size // 2)

        line_x = (width - w_line) // 2
        line_y = start_y + i * line_height

        # Draw dark backplate for readability
        pad_x, pad_y = 20, 8
        draw.rounded_rectangle(
            [(line_x - pad_x, line_y - pad_y), (line_x + w_line + pad_x, line_y + line_height)],
            radius=12,
            fill=(0, 0, 0, 160),
        )

        # Draw stroke (thick outline)
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx * dx + dy * dy <= stroke_width * stroke_width:
                    draw.text((line_x + dx, line_y + dy), line, font=font, fill=(0, 0, 0, 255))

        # Fill text (first word or key line in bright yellow highlight)
        text_color = highlight_color if i == 0 else "#FFFFFF"
        draw.text((line_x, line_y), line, font=font, fill=text_color)

    final_img = Image.alpha_composite(base_img, overlay).convert("RGB")
    ensure_dir(output_frame_path.parent)
    final_img.save(str(output_frame_path), quality=95)
    return output_frame_path


from capcut_integrator import create_capcut_draft_package

def assemble_video_from_script(
    script_data: GeneratedScriptModel | Dict[str, Any],
    voiceover_path: str,
    output_video_path: Optional[str] = None,
    add_bgm: bool = True,
    bgm_genre: str = "lofi",
    is_vertical: bool = False,
) -> Path:
    """Render a complete 1080p MP4 video with 100% frame-perfect audio-visual sync and CapCut draft."""
    if isinstance(script_data, dict):
        script_model = GeneratedScriptModel.model_validate(script_data)
    else:
        script_model = script_data

    from moviepy import AudioFileClip, CompositeVideoClip, ImageClip, concatenate_videoclips

    topic_slug = "".join(c if c.isalnum() else "_" for c in script_model.topic).strip("_")[:40]
    out_video = Path(output_video_path).resolve() if output_video_path else ensure_dir(get_output_dir() / "videos") / f"video_{topic_slug}.mp4"
    ensure_dir(out_video.parent)

    # 1. Prepare Master Audio with BGM and Ducking
    trans_times: List[float] = [0.0]
    curr_time = float(script_model.hook.duration_seconds)
    for sec in script_model.sections:
        trans_times.append(curr_time)
        curr_time += float(sec.duration_seconds)

    if add_bgm:
        LOGGER.info("Mixing master audio track with BGM and Audio Ducking...")
        master_audio_path = mix_voiceover_with_bgm_and_sfx(
            voiceover_path=voiceover_path,
            bgm_genre=bgm_genre,
            transition_timestamps=trans_times,
        )
        audio_clip = AudioFileClip(str(master_audio_path))
    else:
        master_audio_path = Path(voiceover_path)
        audio_clip = AudioFileClip(str(voiceover_path))

    total_duration = audio_clip.duration
    LOGGER.info(f"Total video production duration: {total_duration:.1f}s")

    # 2. Generate/Load 1080p Scene Visuals
    LOGGER.info("Generating 100% Free AI scene visuals...")
    scene_images = generate_images_for_script(script_model, is_vertical=is_vertical)

    width, height = (1080, 1920) if is_vertical else (1920, 1080)

    # 3. Create Video Scenes with Kinetic Subtitles & Exact Audio Matching
    scenes_data = [
        (scene_images[0], script_model.hook.spoken_dialogue, script_model.hook.duration_seconds),
    ]
    for i, sec in enumerate(script_model.sections):
        img_p = scene_images[i + 1] if i + 1 < len(scene_images) else scene_images[-1]
        scenes_data.append((img_p, sec.spoken_dialogue, sec.duration_seconds))

    outro_img = scene_images[-1]
    scenes_data.append((outro_img, script_model.call_to_action_and_outro.spoken_dialogue, script_model.call_to_action_and_outro.duration_seconds))

    # Scale segment durations proportionally to exact master audio duration so zero gap/drift occurs
    raw_sum = sum(s[2] for s in scenes_data)
    scale_factor = total_duration / raw_sum if raw_sum > 0 else 1.0

    temp_frames_dir = ensure_dir(get_output_dir() / "temp_frames" / topic_slug)
    video_clips = []
    capcut_scenes = []

    for idx, (img_path, dialogue, dur) in enumerate(scenes_data):
        seg_duration = max(0.5, dur * scale_factor)
        frame_out = temp_frames_dir / f"frame_{idx:02d}.jpg"

        render_kinetic_subtitle_frame(
            base_image_path=img_path,
            caption_text=dialogue[:120],
            output_frame_path=frame_out,
            width=width,
            height=height,
        )

        clip = ImageClip(str(frame_out)).with_duration(seg_duration)
        video_clips.append(clip)

        capcut_scenes.append({
            "image_path": str(img_path),
            "duration": seg_duration,
            "text": dialogue,
        })

    final_video = concatenate_videoclips(video_clips, method="compose")
    final_video = final_video.with_audio(audio_clip)

    LOGGER.info(f"Rendering 1080p MP4 video ({width}x{height}, {total_duration:.1f}s) to: {out_video}...")
    final_video.write_videofile(
        str(out_video),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4,
        logger=None,
    )

    audio_clip.close()
    final_video.close()

    # 4. Generate CapCut Windows Draft Project
    try:
        draft_info = create_capcut_draft_package(
            project_name=topic_slug,
            scenes=capcut_scenes,
            is_vertical=is_vertical,
            bgm_path=str(master_audio_path),
        )
        LOGGER.info(f"✂️ CapCut draft generated: {draft_info['output_draft_dir']}")
    except Exception as exc:
        LOGGER.warning(f"CapCut draft creation notice: {exc}")

    LOGGER.info(f"✅ Video successfully rendered at: {out_video}")
    return out_video


def assemble_quick_video(
    audio_path: str,
    title: str,
    subtitle: Optional[str] = None,
    output_path: Optional[str] = None,
    bg_image_path: Optional[str] = None,
    is_vertical: bool = False,
) -> Path:
    """Render a quick 1080p slide video for any voiceover track."""
    from moviepy import AudioFileClip, ImageClip

    a_clip = AudioFileClip(audio_path)
    dur = a_clip.duration

    width, height = (1080, 1920) if is_vertical else (1920, 1080)
    out_video = Path(output_path) if output_path else ensure_dir(get_output_dir() / "videos") / f"quick_{Path(audio_path).stem}.mp4"

    # Generate or load background
    if bg_image_path and Path(bg_image_path).exists():
        bg_p = Path(bg_image_path)
    else:
        bg_p = generate_single_image(f"{title} {subtitle or ''}", width=width, height=height)

    frame_out = ensure_dir(get_output_dir() / "temp_frames") / f"quick_{Path(audio_path).stem}.jpg"
    render_kinetic_subtitle_frame(
        base_image_path=bg_p,
        caption_text=f"{title}\n{subtitle or ''}",
        output_frame_path=frame_out,
        width=width,
        height=height,
    )

    v_clip = ImageClip(str(frame_out)).with_duration(dur).with_audio(a_clip)
    v_clip.write_videofile(str(out_video), fps=24, codec="libx264", audio_codec="aac", preset="ultrafast", logger=None)

    a_clip.close()
    v_clip.close()
    return out_video


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble 1080p MP4 Video with Free AI Visuals and MrBeast Subtitles.")
    parser.add_argument("--script", "-s", required=True, help="Path to script JSON file.")
    parser.add_argument("--audio", "-a", required=True, help="Path to voiceover MP3 file.")
    parser.add_argument("--output", "-o", default=None, help="Output MP4 video path.")
    parser.add_argument("--no-bgm", action="store_true", help="Disable background music mixing.")
    parser.add_argument("--bgm-genre", default="lofi", choices=["lofi", "cinematic", "tech"], help="BGM genre.")
    parser.add_argument("--vertical", action="store_true", help="Render 9:16 vertical Shorts video (1080x1920).")
    args = parser.parse_args()

    with open(args.script, "r", encoding="utf-8") as f:
        s_data = json.load(f)

    try:
        vid_path = assemble_video_from_script(
            script_data=s_data,
            voiceover_path=args.audio,
            output_video_path=args.output,
            add_bgm=not args.no_bgm,
            bgm_genre=args.bgm_genre,
            is_vertical=args.vertical,
        )
        print(f"\n🎬 1080p Video Successfully Assembled: {vid_path}\n")
    except Exception as exc:
        LOGGER.error(f"Video assembly failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
