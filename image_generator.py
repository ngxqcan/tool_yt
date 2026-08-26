"""100% Free AI Image Generator Module.

Uses Pollinations AI (FLUX.1 & SDXL models) to generate Full HD 1080p scene illustrations
from script B-roll prompts without requiring any paid subscriptions or API keys.
Includes deterministic offline Pillow fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from models import GeneratedScriptModel
from utils import ensure_dir, get_cache_dir, get_output_dir, get_project_root, retry_with_backoff, setup_logging

load_dotenv()
LOGGER = setup_logging("image_generator")


def sanitize_prompt(prompt: str) -> str:
    """Clean and enhance prompt for optimal image generation."""
    clean = " ".join(prompt.strip().split())
    # Add cinematic lighting & high-detail keywords
    enhanced = f"{clean}, 8k resolution, cinematic lighting, photorealistic, octane render, masterpiece, hyperdetailed"
    return enhanced


@retry_with_backoff(max_retries=3, initial_delay=2.0)
def _download_pollinations_image(url: str, output_path: Path) -> Path:
    """Download image from Pollinations AI with retry backoff."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    resp = requests.get(url, headers=headers, timeout=25)
    if resp.status_code != 200:
        raise requests.RequestException(f"Pollinations AI returned HTTP {resp.status_code}")
    
    if len(resp.content) < 5000:
        raise ValueError(f"Downloaded image is suspiciously small ({len(resp.content)} bytes)")

    with open(output_path, "wb") as f:
        f.write(resp.content)
    return output_path


def generate_offline_fallback_image(
    prompt: str,
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    title_text: Optional[str] = None,
) -> Path:
    """Generate a clean dark-themed gradient background with typography when offline."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), color="#0f172a")
    draw = ImageDraw.Draw(img)

    # Draw gradient or decorative geometric accents
    accent_color = "#3b82f6"
    draw.rectangle([(0, 0), (width, 24)], fill=accent_color)
    draw.rectangle([(0, height - 24), (width, height)], fill=accent_color)

    # Add text
    display_title = title_text or "AI Visual Scene"
    draw.text((80, 100), display_title[:60], fill="#f8fafc")
    draw.text((80, 160), f"Prompt: {prompt[:80]}...", fill="#94a3b8")

    ensure_dir(output_path.parent)
    img.save(str(output_path), quality=95)
    LOGGER.info(f"Generated local procedural scene graphic: {output_path}")
    return output_path


def generate_single_image(
    prompt: str,
    output_path: Optional[str] = None,
    width: int = 1920,
    height: int = 1080,
    model: str = "flux",
    seed: Optional[int] = None,
    force_refresh: bool = False,
) -> Path:
    """Generate a single Full HD AI visual using Pollinations AI (100% Free)."""
    clean_p = sanitize_prompt(prompt)
    prompt_hash = hashlib.md5(clean_p.encode("utf-8")).hexdigest()[:10]

    if output_path:
        out_file = Path(output_path).resolve()
    else:
        out_file = ensure_dir(get_output_dir() / "images") / f"scene_{prompt_hash}_{width}x{height}.jpg"

    ensure_dir(out_file.parent)

    # Check cache
    if not force_refresh and out_file.exists() and out_file.stat().st_size > 5000:
        LOGGER.info(f"[CACHE HIT] Loaded image from: {out_file}")
        return out_file

    encoded_prompt = urllib.parse.quote(clean_p)
    seed_param = f"&seed={seed}" if seed is not None else ""
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model={model}&nologo=true{seed_param}"

    try:
        LOGGER.info(f"Generating 100% Free AI image ({width}x{height}, model={model})...")
        return _download_pollinations_image(url, out_file)
    except Exception as exc:
        LOGGER.warning(f"Pollinations AI generation failed ({exc}). Using offline fallback image.")
        return generate_offline_fallback_image(prompt, out_file, width, height)


def generate_images_for_script(
    script_data: GeneratedScriptModel | Dict[str, Any],
    output_dir: Optional[str] = None,
    is_vertical: bool = False,
    force_refresh: bool = False,
) -> List[Path]:
    """Generate a full sequence of 1080p scene images for each beat/section in a script."""
    if isinstance(script_data, dict):
        model = GeneratedScriptModel.model_validate(script_data)
    else:
        model = script_data

    topic_slug = "".join(c if c.isalnum() else "_" for c in model.topic).strip("_")[:40]
    out_dir = Path(output_dir) if output_dir else ensure_dir(get_output_dir() / "images" / topic_slug)
    ensure_dir(out_dir)

    width, height = (1080, 1920) if is_vertical else (1920, 1080)
    image_paths: List[Path] = []

    # 1. Hook Scene
    hook_prompt = f"{model.topic}: {model.hook.visual_b_roll_instructions}"
    hook_img = generate_single_image(
        prompt=hook_prompt,
        output_path=str(out_dir / f"00_hook_{width}x{height}.jpg"),
        width=width,
        height=height,
        force_refresh=force_refresh,
    )
    image_paths.append(hook_img)

    # 2. Main Sections Scenes
    for idx, sec in enumerate(model.sections, start=1):
        sec_prompt = f"{sec.title}. {sec.visual_b_roll_instructions}"
        sec_img = generate_single_image(
            prompt=sec_prompt,
            output_path=str(out_dir / f"{idx:02d}_section_{width}x{height}.jpg"),
            width=width,
            height=height,
            force_refresh=force_refresh,
        )
        image_paths.append(sec_img)

    # 3. Outro Scene
    outro_prompt = f"{model.topic} conclusion: {model.call_to_action_and_outro.visual_b_roll_instructions}"
    outro_img = generate_single_image(
        prompt=outro_prompt,
        output_path=str(out_dir / f"99_outro_{width}x{height}.jpg"),
        width=width,
        height=height,
        force_refresh=force_refresh,
    )
    image_paths.append(outro_img)

    LOGGER.info(f"Generated {len(image_paths)} visual scene images for script: '{model.topic}' at {out_dir}")
    return image_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="100% Free AI Image Generator (Pollinations FLUX.1).")
    parser.add_argument("--prompt", "-p", required=True, help="Text description of the image scene.")
    parser.add_argument("--output", "-o", default=None, help="Output image file path (.jpg / .png).")
    parser.add_argument("--width", type=int, default=1920, help="Image width in pixels (default: 1920).")
    parser.add_argument("--height", type=int, default=1080, help="Image height in pixels (default: 1080).")
    parser.add_argument("--model", default="flux", choices=["flux", "turbo", "unity"], help="AI Model.")
    parser.add_argument("--vertical", action="store_true", help="Generate 9:16 vertical Shorts image (1080x1920).")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass local cache.")
    args = parser.parse_args()

    w = 1080 if args.vertical else args.width
    h = 1920 if args.vertical else args.height

    try:
        res = generate_single_image(
            prompt=args.prompt,
            output_path=args.output,
            width=w,
            height=h,
            model=args.model,
            force_refresh=args.force_refresh,
        )
        print(f"\n✅ 100% Free AI Image Generated Successfully at: {res}\n")
    except Exception as exc:
        LOGGER.error(f"Image generation failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
