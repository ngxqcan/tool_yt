"""Thumbnail Designer & AI Image Prompt Builder Module.

Generates high-CTR thumbnail concepts and optimized prompts for Midjourney, DALL-E 3,
and Google Imagen 3, plus renders quick local mockup graphics with PIL.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont

from dotenv import load_dotenv
from models import (
    ThumbnailDesignModel,
    ThumbnailPromptVariationModel,
    parse_and_validate_json,
)
from utils import ensure_dir, get_project_root, setup_logging

load_dotenv()
LOGGER = setup_logging("thumbnail_designer")


def design_thumbnail_prompts(
    topic: str,
    target_emotion: str = "High Curiosity & Shock",
    gemini_api_key: Optional[str] = None,
    gemini_model: Optional[str] = None,
) -> ThumbnailDesignModel:
    """Generate 3 high-converting thumbnail prompt variations tailored for AI image generators."""
    raw_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    api_key = raw_api_key if raw_api_key and not raw_api_key.lower().startswith("your_") else None
    model_name = gemini_model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    prompt = f"""You are a world-class YouTube thumbnail artist specializing in high-CTR visual design.
Design 3 distinct thumbnail concepts for this video:

TOPIC: {topic}
TARGET EMOTION: {target_emotion}

CRITICAL RULES FOR THUMBNAIL CTR:
1. Max 3-4 words of punchy text overlay.
2. High contrast colors (e.g. electric yellow on dark blue, neon red on black).
3. Clear foreground focal point (expressive human face, dramatic object, visual dilemma).
4. Cinematic lighting, 16:9 ratio, 8k resolution details.

Return ONLY valid JSON matching this schema:
{{
  "video_topic": "{topic}",
  "core_visual_metaphor": "string description",
  "emotional_trigger": "string",
  "prompts": [
    {{
      "variation_name": "Concept 1: Dramatic Human Reaction",
      "style_concept": "Hyper-realistic cinematic close-up with intense lighting",
      "midjourney_prompt": "cinematic close-up portrait of person with shocked expression looking at glowing futuristic device, high contrast volumetric lighting, 8k, photorealistic, octane render --ar 16:9 --v 6.0",
      "dalle_prompt": "A vivid 16:9 YouTube thumbnail showing a person reacting in amazement to...",
      "imagen_prompt": "Photorealistic 16:9 YouTube thumbnail of...",
      "recommended_text_overlay": "IT HAPPENED!",
      "color_palette_hex": ["#FFCC00", "#111111", "#FF0033"]
    }},
    {{
      "variation_name": "Concept 2: Before vs After / Visual Split",
      "style_concept": "Split screen comparison showing drastic contrast",
      "midjourney_prompt": "split screen comparison of old broken system on left vs glowing clean futuristic system on right, high contrast --ar 16:9 --v 6.0",
      "dalle_prompt": "A split screen thumbnail graphic showing...",
      "imagen_prompt": "Cinematic split composition...",
      "recommended_text_overlay": "DON'T DO THIS",
      "color_palette_hex": ["#00E5FF", "#FF3366", "#000000"]
    }},
    {{
      "variation_name": "Concept 3: Minimalist Curiosity Gap",
      "style_concept": "Bold single element in center with stark shadows",
      "midjourney_prompt": "single iconic futuristic glowing element floating in dark studio, dramatic rim lighting --ar 16:9 --v 6.0",
      "dalle_prompt": "Minimalist striking YouTube thumbnail of...",
      "imagen_prompt": "Clean studio lighting minimalist thumbnail...",
      "recommended_text_overlay": "THE SECRET",
      "color_palette_hex": ["#FFFFFF", "#00FF88", "#0A0A0A"]
    }}
  ]
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
                    temperature=0.3,
                ),
            )
            model = parse_and_validate_json(response.text or "", ThumbnailDesignModel)
            LOGGER.info(f"Successfully generated thumbnail prompts for topic: '{topic}'")
            return model
        except Exception as exc:
            LOGGER.warning(f"Gemini thumbnail prompt generation failed ({exc}). Falling back to template.")

    # Fallback
    return ThumbnailDesignModel(
        video_topic=topic,
        core_visual_metaphor=f"Futuristic visual comparison of {topic}",
        emotional_trigger=target_emotion,
        prompts=[
            ThumbnailPromptVariationModel(
                variation_name="High-Contrast Warning / Curiosity",
                style_concept="Dramatic cinematic lighting with bold warning aesthetic",
                midjourney_prompt=f"Cinematic close-up portrait of person with amazed expression inspecting glowing holographic {topic} diagram, high contrast volumetric lighting, 8k, photorealistic --ar 16:9 --v 6.0",
                dalle_prompt=f"A vivid 16:9 YouTube thumbnail illustrating {topic} with a shocked tech creator, dramatic rim lighting and bold colors.",
                imagen_prompt=f"Photorealistic 16:9 YouTube thumbnail of {topic} with intense cinematic lighting and expressive human focal point.",
                recommended_text_overlay="DON'T MISS THIS",
                color_palette_hex=["#FFCC00", "#000000", "#FF0033"],
            ),
            ThumbnailPromptVariationModel(
                variation_name="Futuristic Breakdown",
                style_concept="Glowing neon schematic masterclass",
                midjourney_prompt=f"Minimalist glowing neon schematic of {topic} against dark obsidian background, sharp rim light, 3d render --ar 16:9 --v 6.0",
                dalle_prompt=f"Minimalist 3D rendered graphic representing {topic} in an electric cyan and dark studio setup.",
                imagen_prompt=f"Clean studio lighting thumbnail representing {topic} with vibrant neon cyan accents.",
                recommended_text_overlay="NEW FORMULA",
                color_palette_hex=["#00E5FF", "#111111", "#FFFFFF"],
            ),
        ],
    )


def render_thumbnail_mockup(
    text_overlay: str,
    subtitle: str = "",
    output_path: Optional[str] = None,
    bg_color: str = "#0d1117",
    accent_color: str = "#ffcc00",
) -> Path:
    """Render a clean 1280x720 YouTube thumbnail mockup card using Pillow."""
    width, height = 1280, 720
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Draw stylish gradient background shapes
    draw.rectangle([(0, 0), (width, 15)], fill=accent_color)
    draw.ellipse([(width - 400, -100), (width + 300, 500)], fill="#1a2332")
    draw.ellipse([(-100, height - 300), (400, height + 200)], fill="#21262d")

    # Draw border accent
    draw.line([(50, height - 60), (width - 50, height - 60)], fill=accent_color, width=6)

    # Draw main text box
    main_text = text_overlay.upper()
    try:
        font_large = ImageFont.load_default(size=72)
        font_small = ImageFont.load_default(size=36)
    except Exception:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Center-left text placement
    draw.text((80, 240), main_text, fill=accent_color, font=font_large)
    if subtitle:
        draw.text((80, 360), subtitle, fill="#ffffff", font=font_small)

    out_file = Path(output_path) if output_path else ensure_dir(get_project_root() / "output" / "thumbnails") / "thumbnail_mockup.png"
    ensure_dir(out_file.parent)
    img.save(str(out_file))
    LOGGER.info(f"Rendered thumbnail mockup: {out_file}")
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AI image thumbnail prompts and render mockups.")
    parser.add_argument("--topic", "-t", required=True, help="Video topic.")
    parser.add_argument("--mockup", action="store_true", help="Render local 1280x720 PNG mockup.")
    args = parser.parse_args()

    try:
        res = design_thumbnail_prompts(args.topic)
        print("\n================ AI THUMBNAIL PROMPT STUDIO ================")
        print(f"Topic: {res.video_topic}")
        print(f"Visual Metaphor: {res.core_visual_metaphor}\n")
        for idx, p in enumerate(res.prompts, 1):
            print(f"[{idx}] {p.variation_name}")
            print(f"    Text Overlay: \"{p.recommended_text_overlay}\"")
            print(f"    Midjourney:   {p.midjourney_prompt}")
            print(f"    DALL-E 3:     {p.dalle_prompt}\n")
        print("============================================================\n")

        if args.mockup and res.prompts:
            p0 = res.prompts[0]
            mock_path = render_thumbnail_mockup(p0.recommended_text_overlay, subtitle=args.topic)
            print(f"Mockup saved to: {mock_path}")
    except Exception as exc:
        LOGGER.error(f"Thumbnail prompt generation failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
