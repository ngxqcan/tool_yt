"""CapCut Windows Draft Integration Module.

Generates native CapCut Draft project packages containing aligned video layers,
voiceover audio, royalty-free BGM, and kinetic subtitle text tracks.
Allows 1-click automatic export and launch into CapCut desktop.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from utils import ensure_dir, get_output_dir, get_project_root, setup_logging

load_dotenv()
LOGGER = setup_logging("capcut_integrator")


def find_capcut_drafts_dir() -> Optional[Path]:
    """Locate the CapCut Desktop drafts directory on Windows."""
    local_appdata = os.getenv("LOCALAPPDATA", "")
    candidates = [
        Path(local_appdata) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
        Path(local_appdata) / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft",
        Path(os.path.expanduser("~")) / "AppData" / "Local" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
    ]
    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    return None


def find_capcut_executable() -> Optional[Path]:
    """Find the CapCut Windows executable path."""
    local_appdata = os.getenv("LOCALAPPDATA", "")
    program_files = os.getenv("PROGRAMFILES", "C:\\Program Files")
    program_files_x86 = os.getenv("PROGRAMFILES(X86)", "C:\\Program Files (x86)")

    candidates = [
        Path(local_appdata) / "CapCut" / "Apps" / "CapCut.exe",
        Path(program_files) / "CapCut" / "CapCut.exe",
        Path(program_files_x86) / "CapCut" / "CapCut.exe",
    ]
    # Check versioned app folders
    apps_dir = Path(local_appdata) / "CapCut" / "Apps"
    if apps_dir.exists():
        for sub in apps_dir.iterdir():
            if sub.is_dir() and (sub / "CapCut.exe").exists():
                return sub / "CapCut.exe"

    for c in candidates:
        if c.exists():
            return c
    return None


def generate_capcut_draft_content(
    scenes: List[Dict[str, Any]],
    project_name: str,
    is_vertical: bool = False,
    bgm_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a compliant draft_content.json timeline structure for CapCut."""
    canvas_w = 1080 if is_vertical else 1920
    canvas_h = 1920 if is_vertical else 1080

    total_duration_us = 0
    videos_material = []
    audios_material = []
    texts_material = []

    video_segments = []
    audio_segments = []
    text_segments = []

    current_start_us = 0

    for idx, sc in enumerate(scenes):
        dur_sec = float(sc.get("duration", 5.0))
        dur_us = int(dur_sec * 1_000_000)
        img_path = str(Path(sc.get("image_path", "")).resolve()).replace("\\", "/")
        audio_path = str(Path(sc.get("audio_path", "")).resolve()).replace("\\", "/")
        caption = sc.get("text", "")

        # 1. Video/Image Material
        v_id = f"mat_video_{idx}_{uuid.uuid4().hex[:8]}"
        videos_material.append({
            "id": v_id,
            "path": img_path,
            "type": "photo",
            "duration": dur_us,
            "width": canvas_w,
            "height": canvas_h,
        })
        video_segments.append({
            "id": f"seg_v_{idx}",
            "material_id": v_id,
            "target_timerange": {"start": current_start_us, "duration": dur_us},
            "source_timerange": {"start": 0, "duration": dur_us},
            "speed": 1.0,
        })

        # 2. Voiceover Audio Material
        if audio_path and Path(audio_path).exists():
            a_id = f"mat_audio_{idx}_{uuid.uuid4().hex[:8]}"
            audios_material.append({
                "id": a_id,
                "path": audio_path,
                "type": "extract_music",
                "duration": dur_us,
            })
            audio_segments.append({
                "id": f"seg_a_{idx}",
                "material_id": a_id,
                "target_timerange": {"start": current_start_us, "duration": dur_us},
                "source_timerange": {"start": 0, "duration": dur_us},
                "volume": 1.0,
            })

        # 3. Subtitle Text Material
        if caption:
            t_id = f"mat_text_{idx}_{uuid.uuid4().hex[:8]}"
            texts_material.append({
                "id": t_id,
                "content": json.dumps({"text": caption, "styles": [{"fill": {"alpha": 1.0, "content": {"solid": {"color": [1.0, 0.9, 0.0]}}}}]}),
                "type": "subtitle",
            })
            text_segments.append({
                "id": f"seg_t_{idx}",
                "material_id": t_id,
                "target_timerange": {"start": current_start_us, "duration": dur_us},
            })

        current_start_us += dur_us

    total_duration_us = current_start_us

    # 4. Optional BGM track
    if bgm_path and Path(bgm_path).exists():
        bgm_resolved = str(Path(bgm_path).resolve()).replace("\\", "/")
        bgm_id = f"mat_bgm_{uuid.uuid4().hex[:8]}"
        audios_material.append({
            "id": bgm_id,
            "path": bgm_resolved,
            "type": "music",
            "duration": total_duration_us,
        })
        audio_segments.append({
            "id": "seg_bgm_track",
            "material_id": bgm_id,
            "target_timerange": {"start": 0, "duration": total_duration_us},
            "source_timerange": {"start": 0, "duration": total_duration_us},
            "volume": 0.15,
        })

    tracks = [
        {"id": "track_video", "type": "video", "segments": video_segments},
        {"id": "track_audio_voice", "type": "audio", "segments": audio_segments},
        {"id": "track_subtitles", "type": "text", "segments": text_segments},
    ]

    return {
        "id": f"draft_{uuid.uuid4().hex[:12]}",
        "version": 300000,
        "canvas_config": {"width": canvas_w, "height": canvas_h, "ratio": "9:16" if is_vertical else "16:9"},
        "duration": total_duration_us,
        "materials": {
            "videos": videos_material,
            "audios": audios_material,
            "texts": texts_material,
        },
        "tracks": tracks,
    }


def create_capcut_draft_package(
    project_name: str,
    scenes: List[Dict[str, Any]],
    is_vertical: bool = False,
    bgm_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate and deploy a complete CapCut project draft to Windows CapCut folder and output/."""
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in project_name).strip("_")[:45]
    if not safe_name:
        safe_name = f"YT_Project_{int(time.time())}"

    # Draft metadata
    draft_meta = {
        "draft_id": f"draft_{uuid.uuid4().hex[:12]}",
        "draft_name": safe_name,
        "draft_create_time": int(time.time()),
        "draft_update_time": int(time.time()),
        "tm_draft_cloud_completed": "",
        "draft_timeline_duration": sum(int(s.get("duration", 5.0) * 1_000_000) for s in scenes),
    }

    draft_content = generate_capcut_draft_content(scenes, safe_name, is_vertical=is_vertical, bgm_path=bgm_path)

    # 1. Save in project output folder
    output_draft_dir = ensure_dir(get_output_dir() / "capcut_drafts" / safe_name)
    with open(output_draft_dir / "draft_content.json", "w", encoding="utf-8") as f:
        json.dump(draft_content, f, indent=2, ensure_ascii=False)
    with open(output_draft_dir / "draft_meta_info.json", "w", encoding="utf-8") as f:
        json.dump(draft_meta, f, indent=2, ensure_ascii=False)

    # Write import helper batch script
    import_bat = output_draft_dir / "open_in_capcut.bat"
    capcut_drafts_root = find_capcut_drafts_dir()
    capcut_exe = find_capcut_executable()

    with open(import_bat, "w", encoding="utf-8") as f:
        f.write(f"""@echo off
echo ========================================================
echo Importing '{safe_name}' to CapCut Desktop...
echo ========================================================
set "TARGET_DIR=%LOCALAPPDATA%\\CapCut\\User Data\\Projects\\com.lveditor.draft\\{safe_name}"
mkdir "%TARGET_DIR%" 2>nul
xcopy /Y /E /I "%~dp0*.*" "%TARGET_DIR%\\"
echo [OK] Project copied to CapCut drafts!
start "" "{capcut_exe if capcut_exe else 'CapCut'}"
pause
""")

    # 2. Automatically copy to CapCut Desktop drafts folder if detected
    deployed_to_capcut = False
    if capcut_drafts_root and capcut_drafts_root.exists():
        try:
            target_capcut_dir = capcut_drafts_root / safe_name
            ensure_dir(target_capcut_dir)
            shutil.copy2(output_draft_dir / "draft_content.json", target_capcut_dir / "draft_content.json")
            shutil.copy2(output_draft_dir / "draft_meta_info.json", target_capcut_dir / "draft_meta_info.json")
            LOGGER.info(f"✅ Automatically deployed project to CapCut drafts: {target_capcut_dir}")
            deployed_to_capcut = True
        except Exception as e:
            LOGGER.warning(f"Could not auto-copy to CapCut folder ({e}). Available via output folder.")

    return {
        "project_name": safe_name,
        "output_draft_dir": str(output_draft_dir),
        "deployed_to_capcut": deployed_to_capcut,
        "capcut_drafts_root": str(capcut_drafts_root) if capcut_drafts_root else None,
        "capcut_exe": str(capcut_exe) if capcut_exe else None,
    }


def launch_capcut_app() -> bool:
    """Launch CapCut application on Windows."""
    capcut_exe = find_capcut_executable()
    if capcut_exe and capcut_exe.exists():
        subprocess.Popen([str(capcut_exe)])
        return True
    try:
        subprocess.Popen(["start", "capcut"], shell=True)
        return True
    except Exception:
        return False
