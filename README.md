# YouTube Content Creation Tool & Competitor Video Analyzer

A Python pipeline for analyzing YouTube competitor video format DNA (hook style, beat structure, pacing, tone, and title formulas) and generating 100% original, high-retention video scripts.

## 🚀 Features

- **Competitor Format DNA Extraction (`competitor_analyzer.py`)**:
  - Pulls public video metadata using YouTube Data API v3 (with oEmbed fallback).
  - Fetches timestamped transcripts using `youtube-transcript-api` (cached strictly as `reference-only, do not quote`).
  - Analyzes structural patterns with Gemini to generate a reusable `style_template.json`.
  - Extracts title and thumbnail packaging hints (length, casing, emojis, brackets, numbers).
  - Immutable audit trail in `logs/competitor_analysis.log`.
- **Original Script Generator (`script_generator.py`)**:
  - Injects style templates and strict anti-plagiarism guardrails into Gemini prompts.
  - Generates full spoken scripts with visual B-roll cues, timestamps, and SEO tags in Markdown and JSON.
- **Batch Processing Pipeline (`main.py`)**:
  - Reads topics from `topics.csv` and outputs scripts for each topic.

## 📦 Installation

```bash
git clone <YOUR_REPO_URL>
cd tool_yt
pip install -r requirements.txt
```

## ⚙️ Configuration

Copy `.env.example` to `.env` and set your API keys:
```bash
cp .env.example .env
```

```env
GEMINI_API_KEY=your_gemini_api_key_here
YOUTUBE_API_KEY=your_youtube_data_api_v3_key_here
```

## 🛠️ Usage

### 1. Analyze a Competitor Video
```bash
python competitor_analyzer.py --url "https://www.youtube.com/watch?v=VIDEO_ID"
```

### 2. Generate a Script for a Single Topic
```bash
python script_generator.py --topic "AI Agents in 2026" --style_template cache/competitor/VIDEO_ID/style_template.json
```

### 3. Batch Script Generation from Topics CSV
```bash
python main.py --topics topics.csv --style_template cache/competitor/VIDEO_ID/style_template.json
```

### 4. End-to-End Pipeline Directly from Competitor URL
```bash
python main.py --topics topics.csv --competitor_url "https://www.youtube.com/watch?v=VIDEO_ID"
```

## 🧪 Running Tests

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## 🔒 Guardrail Policy
This repository is strictly a format & strategy analyzer. It extracts meta-patterns only and never reproduces or quotes competitor scripts, dialogue, or footage.
