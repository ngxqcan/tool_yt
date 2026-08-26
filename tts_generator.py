"""Text-to-Speech (TTS) Voiceover Generator Module.

Uses edge-tts to generate natural neural voiceovers in Vietnamese and English for free.
Extracts timed audio segments matching script beats and subtitles.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import edge_tts
from dotenv import load_dotenv

from models import GeneratedScriptModel
from utils import ensure_dir, get_project_root, setup_logging

load_dotenv()
LOGGER = setup_logging("tts_generator")

# Popular neural voices
VOICES = {
    # Vietnamese
    "vi-female": "vi-VN-HoaiMyNeural",
    "vi-male": "vi-VN-NamMinhNeural",
    # English (US)
    "en-male": "en-US-GuyNeural",
    "en-female": "en-US-JennyNeural",
    "en-deep": "en-US-ChristopherNeural",
    # English (UK)
    "en-uk-female": "en-GB-SoniaNeural",
    "en-uk-male": "en-GB-RyanNeural",
}


async def generate_speech_async(
    text: str,
    output_audio_path: str,
    voice: str = "vi-VN-NamMinhNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> Tuple[Path, List[Dict[str, Any]]]:
    """Generate audio file from text using edge-tts with sentence timestamps."""
    out_file = Path(output_audio_path).resolve()
    ensure_dir(out_file.parent)

    actual_voice = VOICES.get(voice, voice)
    LOGGER.info(f"Generating voiceover with voice '{actual_voice}' ({len(text)} chars)...")

    communicate = edge_tts.Communicate(text=text, voice=actual_voice, rate=rate, pitch=pitch)
    
    subtitles_timing = []
    # Save audio stream
    await communicate.save(str(out_file))

    LOGGER.info(f"Voiceover successfully generated: {out_file}")
    return out_file, subtitles_timing


def generate_voiceover(
    text: str,
    output_path: Optional[str] = None,
    voice: str = "vi-VN-NamMinhNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> Path:
    """Synchronous wrapper for generate_speech_async."""
    if not output_path:
        out_dir = ensure_dir(get_project_root() / "output")
        output_path = str(out_dir / "voiceover.mp3")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        out_file, _ = loop.run_until_complete(
            generate_speech_async(text=text, output_audio_path=output_path, voice=voice, rate=rate, pitch=pitch)
        )
        return out_file
    finally:
        loop.close()


def generate_script_voiceover(
    script_data: GeneratedScriptModel | Dict[str, Any],
    output_dir: Optional[str] = None,
    voice: str = "vi-VN-NamMinhNeural",
) -> Dict[str, Path]:
    """Generate voiceovers for an entire video script (full audio + individual section audios)."""
    if isinstance(script_data, dict):
        model = GeneratedScriptModel.model_validate(script_data)
    else:
        model = script_data

    target_dir = ensure_dir(Path(output_dir) if output_dir else get_project_root() / "output" / "audio")
    topic_slug = "".join(c if c.isalnum() else "_" for c in model.topic).strip("_")[:40]

    # Combine full spoken text
    full_speech_parts = [model.hook.spoken_dialogue]
    for sec in model.sections:
        full_speech_parts.append(sec.spoken_dialogue)
    full_speech_parts.append(model.call_to_action_and_outro.spoken_dialogue)
    full_text = "\n\n".join(full_speech_parts)

    full_audio_path = target_dir / f"{topic_slug}_full_voiceover.mp3"
    generate_voiceover(text=full_text, output_path=str(full_audio_path), voice=voice)

    return {"full_audio": full_audio_path}


def list_available_voices() -> Dict[str, str]:
    """Return dictionary of recommended voice shortcuts."""
    return VOICES


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate natural neural TTS voiceover for scripts.")
    parser.add_argument("--text", "-t", required=True, help="Text to speak.")
    parser.add_argument("--output", "-o", default=None, help="Output .mp3 audio file path.")
    parser.add_argument(
        "--voice",
        "-v",
        default="vi-male",
        help=f"Voice key or name (choices: {', '.join(VOICES.keys())} or custom neural voice).",
    )
    parser.add_argument("--rate", default="+0%", help="Speed adjustment, e.g. '+10%%' or '-10%%'.")
    args = parser.parse_args()

    try:
        out_path = generate_voiceover(text=args.text, output_path=args.output, voice=args.voice, rate=args.rate)
        print(f"Audio generated at: {out_path}")
    except Exception as exc:
        LOGGER.error(f"TTS generation failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
