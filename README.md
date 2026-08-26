# YouTube Content Creation Tool & Competitor Video Analyzer

[![CI Test Suite](https://github.com/ngxqcan/tool_yt/actions/workflows/test.yml/badge.svg)](https://github.com/ngxqcan/tool_yt/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-green.svg)](https://docs.pydantic.dev/)

A production-grade Python pipeline for analyzing YouTube competitor video format DNA (hook mechanisms, beat structure, pacing, tone, and title formulas) and generating 100% original, high-retention video scripts with companion subtitles (`.srt`, `.vtt`) and automated YouTube publishing.

---

## 🚀 Key Features

- **Competitor Format DNA Extraction (`competitor_analyzer.py`)**:
  - Pulls public metadata via YouTube Data API v3 (with oEmbed fallback).
  - Fetches multi-language timestamped transcripts (`youtube-transcript-api`), strictly marked `"reference-only, do not quote"`.
  - Analyzes structural patterns with Gemini to generate reusable Pydantic-validated `style_template.json`.
  - **Multi-Competitor Synthesis**: Analyzes and blends multiple competitor videos into a single composite blueprint.
  - Extracts title and thumbnail packaging hints (character length, casing, emojis, brackets, numbers).
  - Maintains an immutable audit trail in `logs/competitor_analysis.log`.
- **Original Script Generator (`script_generator.py`)**:
  - Injects style templates and strict anti-plagiarism guardrails into Gemini prompts.
  - Generates full voiceover scripts with visual B-roll cues, timestamps, and SEO blueprints.
  - **Automatic Subtitle Export**: Generates `.srt` and `.vtt` caption files directly from script beats.
- **Batch Processing & Rate Limiting (`main.py`)**:
  - Reads topics from `topics.csv` and throttles requests with backoff and retry handlers.
  - Pre-flight API key diagnostics (`--validate-keys`).
- **Direct YouTube Video Uploader (`youtube_uploader.py`)**:
  - OAuth 2.0 resumable video upload support via YouTube Data API v3 (`videos.insert`).

---

## 📦 Installation

```bash
git clone https://github.com/ngxqcan/tool_yt.git
cd tool_yt
pip install -r requirements.txt
```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and set your API keys:
```bash
cp .env.example .env
```

```env
# Google Gemini API Key
GEMINI_API_KEY=your_gemini_api_key_here

# YouTube Data API v3 Key
YOUTUBE_API_KEY=your_youtube_data_api_v3_key_here

# Model Selection (e.g., gemini-2.5-flash, gemini-2.5-pro)
GEMINI_MODEL=gemini-2.5-flash
```

### Pre-flight Key Verification
Verify configured API keys before starting long batch runs:
```bash
python main.py --validate-keys
```

---

## 🛠️ Usage Guide

### 1. Analyze a Single Competitor Video
```bash
python competitor_analyzer.py --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

### 2. Synthesize Multiple Competitor Videos
```bash
python competitor_analyzer.py --urls "https://www.youtube.com/watch?v=VID1,https://www.youtube.com/watch?v=VID2" --force-refresh
```

### 3. Generate a Script with Subtitles for a Single Topic
```bash
python script_generator.py --topic "AI Agents in 2026" --style_template cache/competitor/VIDEO_ID/style_template.json
```

### 4. Batch Script Generation from Topics CSV
```bash
python main.py --topics topics.csv --style_template cache/competitor/VIDEO_ID/style_template.json --rate-limit-delay 2.5
```

### 5. End-to-End Pipeline Directly from Reference URLs
```bash
python main.py --topics topics.csv --competitor_urls "https://www.youtube.com/watch?v=VID1,https://www.youtube.com/watch?v=VID2"
```

### 6. Upload Video to YouTube
```bash
python youtube_uploader.py --file "render.mp4" --title "My AI Video" --description "Full video description" --privacy "private"
```

---

## 🧪 Running Tests

```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## 🔒 Guardrail & Ethical Policy
This repository is strictly a **format & strategy analyzer**. It extracts meta-patterns only and never reproduces or quotes competitor scripts, dialogue, or footage. All generated scripts are 100% original.
