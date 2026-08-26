# YouTube AI Production Suite 🎬🚀

[![CI Test Suite](https://github.com/ngxqcan/tool_yt/actions/workflows/test.yml/badge.svg)](https://github.com/ngxqcan/tool_yt/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-green.svg)](https://docs.pydantic.dev/)
[![Zero Cost: 100% Free](https://img.shields.io/badge/Cost-100%25_Free_0đ-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Streamlit App](https://img.shields.io/badge/Streamlit-Web_UI-FF4B4B.svg)](https://streamlit.io/)

An end-to-end automated YouTube content creation powerhouse built with a strict **100% Free / Zero-Cost** architecture. From competitor format DNA extraction and viral outlier discovery to original scriptwriting, Shorts repurposing, Edge-TTS studio voiceovers, 100% Free FLUX.1 AI visuals, smart audio ducking with BGM & SFX, and MrBeast-style kinetic subtitle video assembly.

---

## 🌟 Comprehensive Feature Map (100% Zero Cost)

```
                          ┌────────────────────────┐
                          │   YouTube AI Suite     │
                          └───────────┬────────────┘
                                      │
    ┌──────────────────┬──────────────┼──────────────┬──────────────────┐
    ▼                  ▼              ▼              ▼                  ▼
[1. Intelligence]  [2. Scripting] [3. Voice & BGM][4. Free Visuals][5. Assembly]
- Channel Outliers - Long-form    - Edge-TTS      - FLUX.1 AI      - 1080p MP4
- Comment Gaps     - 3x Shorts    - Smart Ducking - Vision Eye     - MrBeast Subs
- Format DNA       - Subtitles    - CC0 SFX/BGM   - PIL Mockups    - Auto-Upload
```

### 1. Pre-Production Intelligence
- **Channel Outlier Detector (`channel_crawler.py`)**: Scrapes competitor channels, calculates channel view baselines, and flags viral Outliers ($3x - 10x+$ view spikes).
- **Comment Gap Miner (`comment_miner.py`)**: Mines top viewer comments to identify unanswered questions and content gaps to feed into the script prompt.
- **Competitor DNA Analyzer (`competitor_analyzer.py`)**: Extracts pacing, hook mechanisms, beat cadence, tone, and title formulas. Supports multi-competitor synthesis (`--urls`).
- **Gemini Vision Thumbnail Analyzer (`thumbnail_analyzer.py`)**: Downloads actual thumbnail images and performs multimodal computer vision analysis on facial expressions, color contrast, and visual hierarchy.

### 2. Scriptwriting & Growth Repurposing
- **Original Script Generator (`script_generator.py`)**: Generates 100% original scripts with visual B-roll cues, timestamps, and SEO blueprints.
- **Shorts Repurposing Engine (`shorts_generator.py`)**: Derives 3 high-impact vertical short-form scripts (<60s) with 9:16 subtitle files.
- **Community & Newsletter (`community_generator.py`)**: Generates YouTube Community Polls and email newsletter summaries.

### 3. Voiceover & Smart Sound Design (Zero Cost)
- **Neural Voiceover Studio (`tts_generator.py`)**: Free, unlimited neural voiceovers via Microsoft Edge-TTS (Vietnamese Hoài My/Nam Minh, English US/UK).
- **Smart Audio Mixer & Ducking (`audio_mixer.py`)**: Automatically blends background music (Lo-Fi, Cinematic, Tech), applies **Audio Ducking** (-18dB during speech), and injects transition sound effects (Whoosh, Pop).

### 4. 100% Free AI Visuals & Thumbnail Design
- **Free AI Image Generator (`image_generator.py`)**: Uses Pollinations AI / FLUX.1 to automatically generate 1080p full HD scene visuals from script B-roll prompts without requiring subscriptions or API keys.
- **AI Thumbnail Designer (`thumbnail_designer.py`)**: Formulates high-CTR prompts and renders 720p PNG mockup cards.
- **Stock B-Roll Finder (`broll_finder.py`)**: Pexels / Pixabay stock footage integration.

### 5. Automated Video Compositor
- **Kinetic Video Assembler (`video_assembler.py`)**: 1-click video rendering combining voiceover, AI visuals, smart ducking BGM, and MrBeast-style bold stroke neon subtitles into 1080p MP4.
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
5. **🎬 Video Assembly & Upload**: 1-click 1080p video render with AI visuals, BGM audio ducking, and kinetic subtitles.

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
GEMINI_MODEL=gemini-3.6-flash
LOG_DIR=logs
CACHE_DIR=cache
OUTPUT_DIR=output
```

Verify your API keys:
```bash
python main.py --validate-keys
```

---

## 🛠️ CLI Quick Reference

### Full End-to-End Batch Video Factory (Script + Voiceover + Free AI Visuals + Audio Ducking + Video):
```bash
python main.py --topics topics.csv --resume --generate-tts --generate-shorts --design-thumbnails --generate-ai-images --assemble-video
```

### Generate 100% Free AI Image via FLUX.1:
```bash
python image_generator.py --prompt "futuristic cyber server room 4k cinematic" --output scene.jpg
```

### Mix Audio with Background Music & Audio Ducking:
```bash
python audio_mixer.py --voiceover output/voiceover/voice_sample.mp3 --bgm-genre lofi
```

### Assemble 1080p MP4 Video with MrBeast Subtitles:
```bash
python video_assembler.py --script output/script_sample.json --audio output/voiceover/voice_sample.mp3
```

---

## 📂 Sample Outputs & Examples

Explore full production examples in the [`examples/`](./examples) directory:
- [Sample Style Template JSON](./examples/sample_style_template.json)
- [Sample Generated Script Markdown](./examples/sample_script.md)
- [Sample Timed Subtitles (.SRT)](./examples/sample_subtitles.srt)
- [Sample Thumbnail Vision Analysis](./examples/sample_thumbnail_vision.json)

---

## ⚠️ Limitations & Edge Cases

1. **Captions / Transcript Availability**:
   If a competitor video has disabled captions, the analyzer falls back to metadata heuristics.
2. **Quota & Rate Limits**:
   Batch runs utilize an exponential backoff retry handler (`@retry_with_backoff`) and rate limiting. Use `--resume` for large batch runs.
3. **Zero-Cost Image Generation**:
   Pollinations AI FLUX.1 model generates images free without API keys. In case of offline execution, deterministic procedural gradients are generated locally.

---

## 🔒 Guardrail & Ethical Policy
This toolkit is strictly a **format & strategy analyzer**. It extracts meta-patterns only and never reproduces or quotes competitor scripts, dialogue, or footage. All generated scripts are 100% original.

---

## 📄 License
Released under the [MIT License](LICENSE).
