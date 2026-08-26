# YouTube AI Production Suite 🎬🚀

[![CI Test Suite](https://github.com/ngxqcan/tool_yt/actions/workflows/test.yml/badge.svg)](https://github.com/ngxqcan/tool_yt/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-green.svg)](https://docs.pydantic.dev/)
[![Streamlit App](https://img.shields.io/badge/Streamlit-Web_UI-FF4B4B.svg)](https://streamlit.io/)

An end-to-end automated YouTube content powerhouse. From competitor format DNA extraction and viral outlier discovery to original scriptwriting, Shorts repurposing, Edge-TTS studio voiceovers, AI thumbnail design, and automated 1080p video assembly.

---

## 🌟 Comprehensive Feature Map

```
                          ┌────────────────────────┐
                          │   YouTube AI Suite     │
                          └───────────┬────────────┘
                                      │
    ┌──────────────────┬──────────────┼──────────────┬──────────────────┐
    ▼                  ▼              ▼              ▼                  ▼
[1. Intelligence]  [2. Scripting] [3. Voiceover]  [4. Visuals]    [5. Assembly]
- Channel Outliers - Long-form    - Edge-TTS      - Midjourney    - 1080p MP4
- Comment Gaps     - 3x Shorts    - Multi-voice   - DALL-E 3      - Subtitles
- Format DNA       - Subtitles    - Vi & En       - PIL Mockups   - Auto-Upload
```

### 1. Pre-Production Intelligence
- **Channel Outlier Detector (`channel_crawler.py`)**: Scrapes competitor channels, calculates channel view baselines, and flags viral Outliers ($3x - 10x+$ view spikes).
- **Comment Gap Miner (`comment_miner.py`)**: Mines top viewer comments to identify unanswered questions and content gaps.
- **Competitor DNA Analyzer (`competitor_analyzer.py`)**: Extracts pacing, hook mechanisms, beat cadence, tone, and title formulas. Supports multi-competitor synthesis (`--urls`).

### 2. Scriptwriting & Growth Repurposing
- **Original Script Generator (`script_generator.py`)**: Generates 100% original scripts with visual B-roll cues, timestamps, and SEO blueprints.
- **Shorts Repurposing Engine (`shorts_generator.py`)**: Derives 3 high-impact vertical short-form scripts (<60s) with 9:16 subtitle files.
- **Community & Newsletter (`community_generator.py`)**: Generates YouTube Community Polls and email newsletter summaries.

### 3. Voiceover, Visuals & Video Production
- **Neural Voiceover Studio (`tts_generator.py`)**: Free, unlimited neural voiceovers via Microsoft Edge-TTS (Vietnamese Hoài My/Nam Minh, English US/UK).
- **AI Thumbnail Designer (`thumbnail_designer.py`)**: Builds optimized prompts for Midjourney v6, DALL-E 3, and Imagen 3, plus renders 720p PNG mockup cards.
- **Stock B-Roll Finder (`broll_finder.py`)**: Pexels / Pixabay stock footage integration.
- **Automated Video Assembler (`video_assembler.py`)**: 1-click video rendering combining voiceover, visuals, and subtitles into 1080p MP4.
- **Direct YouTube Upload (`youtube_uploader.py`)**: OAuth 2.0 video publishing.

---

## 🖥️ Interactive Web Dashboard (Streamlit)

Launch the modern Web UI:
```bash
streamlit run app.py
# or
python main.py --gui
```

Includes 5 interactive studios:
1. **🔍 Competitor & Outliers**: Analyze videos, blend multiple competitors, scan channels for outliers, and mine comment gaps.
2. **✍️ Script & Shorts Studio**: Write long-form scripts and auto-extract 3 companion vertical Shorts.
3. **🎙️ Neural Voiceover Studio**: Listen to Edge-TTS voiceovers and download MP3s.
4. **🎨 Thumbnail Studio**: View AI image prompts and download 720p mockup thumbnail graphics.
5. **🎬 Video Assembly & Upload**: 1-click video render and YouTube upload.

---

## 📦 Installation & Setup

```bash
git clone https://github.com/ngxqcan/tool_yt.git
cd tool_yt
pip install -r requirements.txt
```

### Configuration (`.env`)
```bash
cp .env.example .env
```
```env
GEMINI_API_KEY=your_gemini_api_key_here
YOUTUBE_API_KEY=your_youtube_data_api_v3_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Verify your API keys:
```bash
python main.py --validate-keys
```

---

## 🛠️ CLI Quick Reference

### Full End-to-End Batch Pipeline (Scripts + TTS + Shorts + Thumbnails):
```bash
python main.py --topics topics.csv --generate-tts --generate-shorts --design-thumbnails
```

### Scan Channel for Viral Outliers:
```bash
python main.py --channel "@mkbhd" --min-score 2.5
```

### Mine Video Comment Gaps:
```bash
python comment_miner.py --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Generate Neural Voiceover:
```bash
python tts_generator.py --text "Xin chào các bạn!" --voice vi-male --output output/voice.mp3
```

### Generate 3 Viral YouTube Shorts:
```bash
python shorts_generator.py --topic "AI Agents in 2026"
```

### Assemble & Render 1080p MP4 Video:
```bash
python video_assembler.py --audio output/voice.mp3 --title "AI Breakthrough" --subtitle "The 2026 Guide"
```

---

## 🧪 Running Tests

```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## 🔒 Guardrail & Ethical Policy
This toolkit is strictly a **format & strategy analyzer**. It extracts meta-patterns only and never reproduces or quotes competitor scripts, dialogue, or footage. All generated scripts are 100% original.
