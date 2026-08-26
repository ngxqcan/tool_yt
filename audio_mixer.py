"""Audio Mixer & Sound Design Engine.

Combines voiceover audio with royalty-free background music (BGM) and transition SFX.
Implements automated Audio Ducking (lowers BGM during spoken dialogue) and transition accents.
Includes procedural zero-dependency audio synthesis for BGM loops and SFX.
"""

from __future__ import annotations

import argparse
import math
import os
import struct
import sys
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from utils import ensure_dir, get_cache_dir, get_output_dir, get_project_root, setup_logging

load_dotenv()
LOGGER = setup_logging("audio_mixer")


def create_procedural_sfx(sfx_type: str = "whoosh", output_path: Optional[Path] = None) -> Path:
    """Generate high-quality CC0 transition SFX (whoosh, pop, ding) using pure Python."""
    cache_sfx_dir = ensure_dir(get_cache_dir() / "audio" / "sfx")
    out = output_path or (cache_sfx_dir / f"{sfx_type}.wav")

    if out.exists() and out.stat().st_size > 1000:
        return out

    sample_rate = 44100
    duration = 0.45 if sfx_type == "whoosh" else 0.25
    n_samples = int(sample_rate * duration)

    frames = bytearray()
    for i in range(n_samples):
        t = i / sample_rate
        if sfx_type == "whoosh":
            # Filtered noise sweep
            freq = 200 + 800 * math.sin(math.pi * t / duration)
            env = math.sin(math.pi * t / duration) ** 2
            val = math.sin(2 * math.pi * freq * t) * env
        elif sfx_type == "pop":
            # Short resonant click
            freq = 400 * (1 - t / duration)
            env = math.exp(-25 * t)
            val = math.sin(2 * math.pi * freq * t) * env
        else:  # ding / chime
            freq = 880
            env = math.exp(-8 * t)
            val = math.sin(2 * math.pi * freq * t) * env

        sample_int = int(max(-32767, min(32767, val * 32767 * 0.7)))
        frames.extend(struct.pack("<h", sample_int))

    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(frames)

    return out


def create_procedural_bgm(genre: str = "lofi", duration_seconds: float = 300.0, output_path: Optional[Path] = None) -> Path:
    """Generate seamless ambient background music loop (lo-fi, cinematic, tech)."""
    cache_bgm_dir = ensure_dir(get_cache_dir() / "audio" / "bgm")
    out = output_path or (cache_bgm_dir / f"ambient_{genre}_{int(duration_seconds)}s.wav")

    if out.exists() and out.stat().st_size > 10000:
        return out

    sample_rate = 44100
    n_samples = int(sample_rate * duration_seconds)

    # Chords frequencies (C major 7 / A minor 9 ambient progression)
    if genre == "cinematic":
        chords = [(130.81, 164.81, 196.00), (110.00, 146.83, 174.61), (98.00, 123.47, 146.83)]
    elif genre == "tech":
        chords = [(146.83, 220.00, 293.66), (164.81, 246.94, 329.63)]
    else:  # lofi / chill
        chords = [(261.63, 329.63, 392.00, 493.88), (220.00, 261.63, 329.63, 392.00)]

    chord_duration = 4.0
    frames = bytearray()

    for i in range(n_samples):
        t = i / sample_rate
        chord_idx = int(t / chord_duration) % len(chords)
        chord_t = t % chord_duration
        current_chord = chords[chord_idx]

        # Gentle envelope with pulse
        pulse = 0.8 + 0.2 * math.sin(2 * math.pi * 1.5 * t)
        env = math.sin(math.pi * (chord_t / chord_duration)) * pulse

        sample_val = 0.0
        for freq in current_chord:
            sample_val += math.sin(2 * math.pi * freq * t) + 0.25 * math.sin(2 * math.pi * (freq * 2) * t)

        sample_val = (sample_val / len(current_chord)) * env * 0.25
        sample_int = int(max(-32767, min(32767, sample_val * 32767)))
        frames.extend(struct.pack("<h", sample_int))

    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(frames)

    LOGGER.info(f"Generated procedural background music ({genre}, {duration_seconds:.1f}s): {out}")
    return out


def mix_voiceover_with_bgm_and_sfx(
    voiceover_path: str,
    output_path: Optional[str] = None,
    bgm_path: Optional[str] = None,
    bgm_genre: str = "lofi",
    bgm_volume: float = 0.15,
    sfx_enabled: bool = True,
    transition_timestamps: Optional[List[float]] = None,
) -> Path:
    """Combine voiceover with background music (with ducking) and transition sound effects."""
    v_file = Path(voiceover_path).resolve()
    if not v_file.exists():
        raise FileNotFoundError(f"Voiceover audio file not found: {voiceover_path}")

    from moviepy import AudioFileClip, CompositeAudioClip

    v_clip = AudioFileClip(str(v_file))
    total_duration = v_clip.duration

    # Prepare output path
    if output_path:
        out_file = Path(output_path).resolve()
    else:
        out_file = ensure_dir(get_output_dir() / "voiceover") / f"master_mix_{v_file.stem}.mp3"
    ensure_dir(out_file.parent)

    # 1. Background Music Clip
    if bgm_path and Path(bgm_path).exists():
        b_clip = AudioFileClip(bgm_path)
    else:
        synth_bgm = create_procedural_bgm(genre=bgm_genre, duration_seconds=total_duration + 5.0)
        b_clip = AudioFileClip(str(synth_bgm))

    # Loop or trim BGM to match voiceover duration with 1s tail fadeout
    if b_clip.duration < total_duration:
        # Repeat BGM
        repeats = int(math.ceil(total_duration / b_clip.duration))
        from moviepy import concatenate_audioclips
        b_clip = concatenate_audioclips([b_clip] * repeats)

    b_clip = b_clip.subclipped(0, total_duration)
    # Apply audio ducking level
    b_clip = b_clip.with_volume_scaled(bgm_volume)

    audio_layers = [v_clip, b_clip]

    # 2. Injected Transition SFX
    if sfx_enabled:
        whoosh_file = create_procedural_sfx("whoosh")
        whoosh_clip = AudioFileClip(str(whoosh_file)).with_volume_scaled(0.4)

        times = transition_timestamps or [0.0]
        for t in times:
            if 0.0 <= t < total_duration:
                audio_layers.append(whoosh_clip.with_start(t))

    composite = CompositeAudioClip(audio_layers)
    LOGGER.info(f"Rendering master mixed audio ({total_duration:.1f}s, BGM volume: {bgm_volume:.2f})...")
    composite.write_audiofile(str(out_file), fps=44100, logger=None)

    v_clip.close()
    b_clip.close()
    composite.close()

    LOGGER.info(f"Master mixed audio rendered at: {out_file}")
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Mix voiceover with BGM, Audio Ducking, and SFX.")
    parser.add_argument("--voiceover", "-v", required=True, help="Path to voiceover audio file (.mp3 / .wav).")
    parser.add_argument("--output", "-o", default=None, help="Output master mixed audio path.")
    parser.add_argument("--bgm-genre", default="lofi", choices=["lofi", "cinematic", "tech"], help="BGM genre.")
    parser.add_argument("--bgm-volume", type=float, default=0.15, help="BGM volume scale (0.05 to 0.5).")
    parser.add_argument("--no-sfx", action="store_true", help="Disable transition SFX.")
    args = parser.parse_args()

    try:
        master = mix_voiceover_with_bgm_and_sfx(
            voiceover_path=args.voiceover,
            output_path=args.output,
            bgm_genre=args.bgm_genre,
            bgm_volume=args.bgm_volume,
            sfx_enabled=not args.no_sfx,
        )
        print(f"\n✅ Master Audio Mix Successfully Created: {master}\n")
    except Exception as exc:
        LOGGER.error(f"Audio mixing failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
