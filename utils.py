"""Utility helpers: Logging, Exponential Backoff Retries, Subtitle Export, Rate Limiting, and Key Validation."""

from __future__ import annotations

import datetime
import functools
import logging
from logging.handlers import RotatingFileHandler
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

import requests

F = TypeVar("F", bound=Callable[..., Any])


def get_project_root() -> Path:
    """Return the absolute path to the project root."""
    return Path(__file__).resolve().parent


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists and return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_dir() -> Path:
    """Return configured logs directory from LOG_DIR env or default 'logs'."""
    raw = os.getenv("LOG_DIR", "logs").strip()
    p = Path(raw)
    return ensure_dir(p if p.is_absolute() else get_project_root() / p)


def get_cache_dir() -> Path:
    """Return configured cache directory from CACHE_DIR env or default 'cache'."""
    raw = os.getenv("CACHE_DIR", "cache").strip()
    p = Path(raw)
    return ensure_dir(p if p.is_absolute() else get_project_root() / p)


def get_output_dir() -> Path:
    """Return configured output directory from OUTPUT_DIR env or default 'output'."""
    raw = os.getenv("OUTPUT_DIR", "output").strip()
    p = Path(raw)
    return ensure_dir(p if p.is_absolute() else get_project_root() / p)


def setup_logging(logger_name: str, log_file_name: str = "app.log") -> logging.Logger:
    """Configure a logger with both console and RotatingFileHandler."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers
    if not logger.handlers:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Stream Handler (stdout)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # Rotating File Handler
        logs_dir = get_log_dir()
        log_path = logs_dir / log_file_name
        try:
            fh = RotatingFileHandler(
                log_path,
                maxBytes=5 * 1024 * 1024,  # 5 MB
                backupCount=5,
                encoding="utf-8",
            )
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except Exception as exc:
            logger.warning(f"Could not initialize RotatingFileHandler on {log_path}: {exc}")

    return logger


LOGGER = setup_logging("utils")


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator to retry a function with exponential backoff and optional jitter."""
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            retries = 0
            delay = initial_delay
            while True:
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:
                    retries += 1
                    if retries > max_retries:
                        LOGGER.error(f"Function {func.__name__} exceeded max retries ({max_retries}). Last error: {exc}")
                        raise

                    if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc) or "Quota exceeded" in str(exc):
                        LOGGER.warning(f"Google Gemini Free Tier quota reached (429). Fast fallback activated immediately.")
                        raise exc

                    actual_delay = delay + (random.uniform(0, 0.5) if jitter else 0)
                    LOGGER.warning(
                        f"[Retry {retries}/{max_retries}] {func.__name__} failed with {type(exc).__name__}: {exc}. "
                        f"Retrying in {actual_delay:.2f}s..."
                    )
                    time.sleep(actual_delay)
                    delay *= backoff_factor
        return wrapper  # type: ignore
    return decorator


class RateLimiter:
    """Simple rate limiter / throttle to prevent hitting Gemini/YouTube API quota."""

    def __init__(self, min_interval_seconds: float = 1.5):
        self.min_interval = min_interval_seconds
        self.last_call_time: float = 0.0

    def wait(self) -> None:
        """Sleep if required to maintain min_interval between requests."""
        now = time.time()
        elapsed = now - self.last_call_time
        if elapsed < self.min_interval:
            sleep_duration = self.min_interval - elapsed
            LOGGER.debug(f"RateLimiter: throttling for {sleep_duration:.2f}s...")
            time.sleep(sleep_duration)
        self.last_call_time = time.time()


# -----------------------------------------------------------------------------
# Subtitle Generation (SRT & VTT)
# -----------------------------------------------------------------------------

def format_seconds_to_srt_time(seconds: float) -> str:
    """Format seconds into SRT timestamp HH:MM:SS,mmm."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def format_seconds_to_vtt_time(seconds: float) -> str:
    """Format seconds into WebVTT timestamp HH:MM:SS.mmm."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{millis:03d}"


def generate_subtitles(script_dict: Dict[str, Any]) -> Tuple[str, str]:
    """Generate both SRT and VTT subtitle text from a structured script dictionary.

    Splits hook, sections, and outro into timed caption blocks.
    """
    caption_blocks: List[Tuple[float, float, str]] = []
    current_time = 0.0

    # 1. Hook
    hook = script_dict.get("hook", {})
    hook_dur = float(hook.get("duration_seconds", 20))
    hook_text = hook.get("spoken_dialogue", "").strip()
    if hook_text:
        caption_blocks.append((current_time, current_time + hook_dur, hook_text))
        current_time += hook_dur

    # 2. Sections
    sections = script_dict.get("sections", [])
    for sec in sections:
        sec_dur = float(sec.get("duration_seconds", 90))
        sec_text = sec.get("spoken_dialogue", "").strip()
        if sec_text:
            caption_blocks.append((current_time, current_time + sec_dur, sec_text))
            current_time += sec_dur

    # 3. Outro
    outro = script_dict.get("call_to_action_and_outro", {})
    outro_dur = float(outro.get("duration_seconds", 20))
    outro_text = outro.get("spoken_dialogue", "").strip()
    if outro_text:
        caption_blocks.append((current_time, current_time + outro_dur, outro_text))
        current_time += outro_dur

    # Build SRT content
    srt_lines: List[str] = []
    for idx, (start, end, text) in enumerate(caption_blocks, 1):
        srt_lines.append(str(idx))
        srt_lines.append(f"{format_seconds_to_srt_time(start)} --> {format_seconds_to_srt_time(end)}")
        srt_lines.append(text)
        srt_lines.append("")

    # Build VTT content
    vtt_lines: List[str] = ["WEBVTT", ""]
    for idx, (start, end, text) in enumerate(caption_blocks, 1):
        vtt_lines.append(str(idx))
        vtt_lines.append(f"{format_seconds_to_vtt_time(start)} --> {format_seconds_to_vtt_time(end)}")
        vtt_lines.append(text)
        vtt_lines.append("")

    return "\n".join(srt_lines), "\n".join(vtt_lines)


# -----------------------------------------------------------------------------
# Pre-flight API Key Validation
# -----------------------------------------------------------------------------

def validate_api_keys(
    gemini_key: Optional[str] = None,
    youtube_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify Gemini and YouTube API keys with lightweight probe calls.

    Returns diagnostic status dict for pre-flight pipeline checks.
    """
    g_key = gemini_key if gemini_key is not None else (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    y_key = youtube_key if youtube_key is not None else os.getenv("YOUTUBE_API_KEY")
    m_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    results: Dict[str, Any] = {
        "gemini": {"configured": bool(g_key), "valid": False, "message": "Not configured"},
        "youtube": {"configured": bool(y_key), "valid": False, "message": "Not configured"},
        "all_valid": False,
    }

    # Validate Gemini Key
    if g_key:
        try:
            from google import genai
            client = genai.Client(api_key=g_key)
            test_resp = client.models.generate_content(
                model=m_name,
                contents="ping",
            )
            if test_resp and test_resp.text:
                results["gemini"]["valid"] = True
                results["gemini"]["message"] = f"Valid & active (Model: {m_name})"
        except Exception as exc:
            results["gemini"]["message"] = f"Validation failed: {exc}"
    else:
        results["gemini"]["message"] = "Missing GEMINI_API_KEY (will use fallback engine)"

    # Validate YouTube Key
    if y_key:
        try:
            url = "https://www.googleapis.com/youtube/v3/videos"
            params = {"id": "dQw4w9WgXcQ", "part": "snippet", "key": y_key}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                results["youtube"]["valid"] = True
                results["youtube"]["message"] = "Valid & active"
            else:
                results["youtube"]["message"] = f"YouTube API returned status {resp.status_code}: {resp.text[:100]}"
        except Exception as exc:
            results["youtube"]["message"] = f"Validation failed: {exc}"
    else:
        results["youtube"]["message"] = "Missing YOUTUBE_API_KEY (will use oEmbed fallback)"

    results["all_valid"] = results["gemini"]["valid"]
    return results
