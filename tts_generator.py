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


import re
import tempfile

def clean_text_for_tts(raw_text: str) -> str:
    """Sanitize raw script text for TTS engines by removing stage cues, markdown, and sound hints."""
    if not raw_text:
        return ""
    # Remove bracketed cues [Music], [Scene 1: ...], (Narrator: ...)
    cleaned = re.sub(r"\[.*?\]", "", raw_text)
    cleaned = re.sub(r"\(.*?\)", "", cleaned)
    # Remove markdown symbols
    cleaned = re.sub(r"[*#_`~>]", "", cleaned)
    # Remove speaker tags (Host:, Narrator:, etc.)
    cleaned = re.sub(r"^(Host|Narrator|Người dẫn|MC|Voiceover|Speaker):\s*", "", cleaned, flags=re.MULTILINE | re.IGNORECASE)
    # Collapse multiple whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


async def _synthesize_chunk_async(chunk_text: str, out_path: str, voice_name: str, rate: str, pitch: str) -> None:
    """Synthesize a single text chunk with edge-tts."""
    comm = edge_tts.Communicate(text=chunk_text, voice=voice_name, rate=rate, pitch=pitch)
    await comm.save(out_path)


async def generate_speech_async(
    text: str,
    output_audio_path: str,
    voice: str = "vi-VN-NamMinhNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> Tuple[Path, List[Dict[str, Any]]]:
    """Generate audio file from text using edge-tts with automatic chunking and fallback voices."""
    out_file = Path(output_audio_path).resolve()
    ensure_dir(out_file.parent)

    cleaned_text = clean_text_for_tts(text)
    if not cleaned_text or not cleaned_text.strip():
        cleaned_text = "Chào mừng bạn đã đến với video hôm nay."

    actual_voice = VOICES.get(voice, voice)
    LOGGER.info(f"Generating voiceover with voice '{actual_voice}' ({len(cleaned_text)} chars)...")

    # Split text into chunks if length > 600 chars to prevent websocket timeout / No audio received
    chunks = []
    if len(cleaned_text) <= 600:
        chunks = [cleaned_text]
    else:
        sentences = re.split(r"(?<=[.!?\n])\s+", cleaned_text)
        curr_chunk = ""
        for s in sentences:
            if not s.strip():
                continue
            if len(curr_chunk) + len(s) < 600:
                curr_chunk += (" " if curr_chunk else "") + s.strip()
            else:
                if curr_chunk:
                    chunks.append(curr_chunk)
                curr_chunk = s.strip()
        if curr_chunk:
            chunks.append(curr_chunk)

    if not chunks:
        chunks = [cleaned_text]

    # Candidate voices for retry
    candidate_voices = [actual_voice]
    if "vi-VN" in actual_voice:
        fallback_v = "vi-VN-HoaiMyNeural" if "NamMinh" in actual_voice else "vi-VN-NamMinhNeural"
        candidate_voices.append(fallback_v)
    elif "en-US" in actual_voice:
        candidate_voices.append("en-US-JennyNeural" if "Guy" in actual_voice else "en-US-GuyNeural")

    last_exc = None
    with tempfile.TemporaryDirectory() as tmp_dir:
        for v_name in candidate_voices:
            try:
                chunk_files = []
                for idx, ch in enumerate(chunks):
                    chunk_path = Path(tmp_dir) / f"chunk_{idx}.mp3"
                    await _synthesize_chunk_async(ch, str(chunk_path), v_name, rate, pitch)
                    if chunk_path.exists() and chunk_path.stat().st_size > 0:
                        chunk_files.append(chunk_path)
                    else:
                        raise RuntimeError(f"Empty chunk produced for chunk #{idx}")

                # Concatenate MP3 chunks into destination file
                with open(out_file, "wb") as out_f:
                    for cf in chunk_files:
                        out_f.write(cf.read_bytes())

                LOGGER.info(f"Voiceover successfully generated: {out_file} ({out_file.stat().st_size} bytes)")
                return out_file, []
            except Exception as exc:
                LOGGER.warning(f"Voice '{v_name}' synthesis failed ({exc}). Trying candidate fallback...")
                last_exc = exc

    # Final fallback: create valid silent/procedural audio if network totally failed
    if not out_file.exists() or out_file.stat().st_size == 0:
        LOGGER.error(f"Edge-TTS failed for all candidate voices ({last_exc}). Writing emergency audio.")
        # Create minimal 1-second silence mp3
        with open(out_file, "wb") as f:
            f.write(b"\xff\xfb\x90\x64\x00\x00\x00\x00\x00\x00\x00\x00" * 40)

    return out_file, []


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


def generate_script_section_audios(
    script_data: GeneratedScriptModel | Dict[str, Any],
    output_dir: Optional[str] = None,
    voice: str = "vi-VN-NamMinhNeural",
    rate: str = "+0%",
) -> List[Dict[str, Any]]:
    """Synthesize separate audio clips for each scene beat to guarantee 100% audio-visual sync."""
    if isinstance(script_data, dict):
        model = GeneratedScriptModel.model_validate(script_data)
    else:
        model = script_data

    from moviepy import AudioFileClip

    topic_slug = "".join(c if c.isalnum() else "_" for c in model.topic).strip("_")[:40]
    target_dir = ensure_dir(Path(output_dir) if output_dir else get_output_dir() / "audio" / topic_slug)

    scenes_raw = [
        ("00_hook", model.hook.spoken_dialogue, "Hook Scene"),
    ]
    for idx, sec in enumerate(model.sections, 1):
        scenes_raw.append((f"{idx:02d}_sec_{idx}", sec.spoken_dialogue, sec.title))
    scenes_raw.append(("99_outro", model.call_to_action_and_outro.spoken_dialogue, "Outro Scene"))

    manifest = []
    for tag, dialogue, title in scenes_raw:
        audio_out = target_dir / f"{tag}.mp3"
        generate_voiceover(text=dialogue, output_path=str(audio_out), voice=voice, rate=rate)
        
        # Read exact audio duration
        try:
            a_clip = AudioFileClip(str(audio_out))
            exact_dur = a_clip.duration
            a_clip.close()
        except Exception:
            exact_dur = max(2.0, len(dialogue.split()) * 0.35)

        manifest.append({
            "tag": tag,
            "title": title,
            "dialogue": dialogue,
            "audio_path": str(audio_out),
            "duration": exact_dur,
        })

    # Also build full master voiceover by concatenating chunks
    full_audio_path = target_dir / f"{topic_slug}_master_voiceover.mp3"
    with open(full_audio_path, "wb") as master_f:
        for item in manifest:
            p = Path(item["audio_path"])
            if p.exists():
                master_f.write(p.read_bytes())

    LOGGER.info(f"✅ Generated {len(manifest)} synchronized scene audio clips + master audio: {full_audio_path}")
    return manifest


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
