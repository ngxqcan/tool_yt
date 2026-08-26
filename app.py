"""Interactive Streamlit Web Dashboard for YouTube AI Production Suite.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv

from channel_crawler import crawl_channel_outliers
from comment_miner import mine_video_comments
from competitor_analyzer import analyze_competitor_video, analyze_multiple_competitors
from models import GeneratedScriptModel, StyleTemplateModel
from script_generator import generate_script, save_script_outputs
from shorts_generator import generate_shorts_from_topic_or_script, save_shorts_outputs
from thumbnail_designer import design_thumbnail_prompts, render_thumbnail_mockup
from tts_generator import VOICES, generate_voiceover
from utils import ensure_dir, get_project_root, validate_api_keys

load_dotenv()

st.set_page_config(
    page_title="YouTube AI Production Suite",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.3rem;
        font-weight: 800;
        background: -webkit-linear-gradient(45deg, #FF4B4B, #FF9900);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #8b949e;
        font-size: 1.1rem;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #1e293b;
        border-radius: 10px;
        padding: 15px;
        border-left: 5px solid #38bdf8;
    }
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown("# 🚀 YouTube AI Suite")
st.sidebar.markdown("---")

# Pre-flight status
diag = validate_api_keys()
st.sidebar.markdown("### 🔑 API Status")
if diag["gemini"]["valid"]:
    st.sidebar.success("Gemini API: Connected ✅")
else:
    st.sidebar.info("Gemini API: Fallback Engine ℹ️")

if diag["youtube"]["valid"]:
    st.sidebar.success("YouTube Data API: Active ✅")
else:
    st.sidebar.info("YouTube API: oEmbed Mode ℹ️")

st.sidebar.markdown("---")
st.sidebar.markdown("💡 **Tip:** Configure your API keys in `.env` for AI features.")

# Main tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔍 1. Competitor & Outliers",
    "✍️ 2. Script & Shorts Studio",
    "🎙️ 3. Neural Voiceover (TTS)",
    "🎨 4. Thumbnail Studio",
    "🎬 5. Video Assembly & Upload",
])

# -----------------------------------------------------------------------------
# TAB 1: Competitor & Outliers
# -----------------------------------------------------------------------------
with tab1:
    st.markdown('<div class="main-header">Competitor Format DNA & Outliers</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Extract structural patterns, identify viral outlier videos, and mine viewer comment gaps.</div>', unsafe_allow_html=True)

    mode = st.radio("Select Analysis Mode:", ["Single Video DNA", "Multi-Competitor Synthesis", "Channel Viral Outliers", "Comment Gap Mining"], horizontal=True)

    if mode == "Single Video DNA":
        vid_url = st.text_input("YouTube Video URL or ID:", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        force_ref = st.checkbox("Bypass Cache (Force Refresh)", value=False)
        if st.button("🚀 Analyze Structural DNA", type="primary"):
            with st.spinner("Extracting metadata, transcript, and Gemini structural patterns..."):
                try:
                    tmpl_path = analyze_competitor_video(vid_url, force_refresh=force_ref)
                    with open(tmpl_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    st.success("✅ Style Template Extracted Successfully!")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**🎣 Hook Style:** {data.get('hook_style')}")
                        st.markdown(f"**⚡ Tone:** {data.get('tone')}")
                        st.markdown(f"**🎯 Title Formula:** `{data.get('title_formula')}`")
                        st.markdown(f"**⏱️ Section Count:** {data.get('section_count')} beats (~{data.get('avg_section_length_seconds')}s each)")
                    with col2:
                        st.json(data)
                    st.session_state["active_template_path"] = tmpl_path
                except Exception as e:
                    st.error(f"Analysis failed: {e}")

    elif mode == "Multi-Competitor Synthesis":
        urls_input = st.text_area("Enter Competitor YouTube URLs (one per line):", "https://www.youtube.com/watch?v=dQw4w9WgXcQ\nhttps://www.youtube.com/watch?v=dQw4w9WgXcQ")
        if st.button("🧬 Synthesize Multi-Video Blueprint", type="primary"):
            urls = [u.strip() for u in urls_input.splitlines() if u.strip()]
            with st.spinner(f"Analyzing and blending {len(urls)} videos..."):
                try:
                    comp_path = analyze_multiple_competitors(urls)
                    with open(comp_path, "r", encoding="utf-8") as f:
                        c_data = json.load(f)
                    st.success("✅ Synthesized Multi-Video Style Template Generated!")
                    st.json(c_data)
                    st.session_state["active_template_path"] = str(comp_path)
                except Exception as e:
                    st.error(f"Synthesis failed: {e}")

    elif mode == "Channel Viral Outliers":
        channel_input = st.text_input("Enter Channel Handle or URL (@creator):", "@mkbhd")
        min_score = st.slider("Min Outlier Multiplier (x Channel Average):", 1.5, 5.0, 2.0, 0.5)
        if st.button("📊 Scan Channel for Outliers", type="primary"):
            with st.spinner("Scanning channel uploads and calculating view multipliers..."):
                try:
                    ch_res = crawl_channel_outliers(channel_input, min_outlier_multiplier=min_score)
                    st.markdown(f"### Channel: **{ch_res.channel_title}**")
                    st.markdown(f"- Analyzed Videos: **{ch_res.total_videos_analyzed}**")
                    st.markdown(f"- Average Views: **{ch_res.average_view_count:,.0f}** | Median: **{ch_res.median_view_count:,.0f}**")
                    st.markdown(f"- Top Keywords: `{'`, `'.join(ch_res.dominant_title_keywords)}`")

                    st.markdown("#### 🔥 Viral Outlier Videos:")
                    for out in ch_res.outlier_videos:
                        st.markdown(f"- **[{out.outlier_score}x Outlier]** [{out.title}]({out.url}) — *{out.view_count:,} views*")
                except Exception as e:
                    st.error(f"Channel crawl failed: {e}")

    elif mode == "Comment Gap Mining":
        comm_url = st.text_input("YouTube URL for Comment Mining:", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        if st.button("💬 Mine Audience Content Gaps", type="primary"):
            with st.spinner("Fetching comments & extracting content gaps..."):
                try:
                    gap_res = mine_video_comments(comm_url)
                    st.success(f"Analyzed {gap_res.total_comments_analyzed} comments! Sentiment: **{gap_res.audience_sentiment}**")
                    st.markdown("### 🎯 Unanswered Content Gaps:")
                    for gap in gap_res.content_gaps:
                        st.warning(f"**Q/Critique:** {gap.question_or_critique}\n\n👉 **Our Script Angle:** {gap.suggested_script_angle}")
                    st.markdown("### 💡 Recommended Key Talking Points:")
                    for pt in gap_res.recommended_talking_points:
                        st.info(f"• {pt}")
                    st.session_state["active_gaps_path"] = str(get_project_root() / "cache" / "competitor" / gap_res.video_id / "comment_gaps.json")
                except Exception as e:
                    st.error(f"Comment mining failed: {e}")

# -----------------------------------------------------------------------------
# TAB 2: Script & Shorts Studio
# -----------------------------------------------------------------------------
with tab2:
    st.markdown('<div class="main-header">Script & Shorts Studio</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Generate 100% original long-form video scripts & 3 companion viral Shorts.</div>', unsafe_allow_html=True)

    colA, colB = st.columns([2, 1])
    with colA:
        topic_input = st.text_input("Video Topic / Working Title:", "How Quantum Computing Will Break Modern Encryption")
        audience_input = st.text_input("Target Audience:", "Software developers, tech enthusiasts, and security researchers")
    with colB:
        tmpl_source = st.text_input("Style Template Path (optional):", st.session_state.get("active_template_path", ""))
        gaps_source = st.text_input("Comment Gaps Path (optional):", st.session_state.get("active_gaps_path", ""))

    gen_shorts = st.checkbox("Also generate 3 YouTube Shorts / TikTok scripts (<60s)", value=True)

    if st.button("✨ Generate Original Script Package", type="primary"):
        with st.spinner("Writing 100% original script with anti-plagiarism guardrails..."):
            try:
                script = generate_script(
                    topic=topic_input,
                    target_audience=audience_input,
                    style_template_source=tmpl_source if tmpl_source else None,
                    comment_gaps_source=gaps_source if gaps_source else None,
                )
                saved_json = save_script_outputs(script)
                st.session_state["current_script"] = script.model_dump()

                st.success("✅ Original Video Script Successfully Generated!")
                st.markdown(f"### 🎯 Suggested Titles:")
                for t in script.suggested_titles:
                    st.markdown(f"- **{t}**")

                st.markdown(f"#### 🎣 Hook ({script.hook.duration_seconds}s)")
                st.info(script.hook.spoken_dialogue)

                st.markdown("#### 🎬 Main Beats & Sections")
                for s in script.sections:
                    with st.expander(f"Beat {s.section_number}: {s.title} (~{s.duration_seconds}s)"):
                        st.markdown(f"**Spoken Voiceover:**\n> {s.spoken_dialogue}")
                        st.markdown(f"**Visuals & B-Roll:**\n*{s.visual_b_roll_instructions}*")

                st.markdown(f"#### 📣 CTA & Outro ({script.call_to_action_and_outro.duration_seconds}s)")
                st.write(script.call_to_action_and_outro.spoken_dialogue)

                # Subtitle download
                srt_path = saved_json.with_suffix(".srt")
                if srt_path.exists():
                    with open(srt_path, "r", encoding="utf-8") as s_file:
                        st.download_button("📥 Download Subtitles (.SRT)", s_file.read(), file_name=srt_path.name, mime="text/plain")

                # Shorts Generation
                if gen_shorts:
                    st.markdown("---")
                    st.markdown("### 📱 Repurposed YouTube Shorts / TikTok Scripts (<60s)")
                    shorts_coll = generate_shorts_from_topic_or_script(topic_input, script)
                    save_shorts_outputs(shorts_coll)
                    for sh in shorts_coll.shorts:
                        with st.expander(f"📱 Shorts #{sh.shorts_id}: {sh.title} (~{sh.target_duration_seconds}s)"):
                            st.markdown(f"**Hook (0-3s):** `{sh.hook}`")
                            for b in sh.beats:
                                st.markdown(f"- **[{b.on_screen_text}]** {b.spoken_dialogue}")
                            st.markdown(f"**CTA:** {sh.call_to_action}")
                            st.markdown(f"**Hashtags:** {' '.join(sh.hashtags)}")

            except Exception as e:
                st.error(f"Script generation error: {e}")

# -----------------------------------------------------------------------------
# TAB 3: Neural Voiceover (TTS)
# -----------------------------------------------------------------------------
with tab3:
    st.markdown('<div class="main-header">Neural Voiceover Studio (Edge-TTS)</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Free, unlimited, studio-quality neural voiceover generator.</div>', unsafe_allow_html=True)

    voice_choice = st.selectbox(
        "Select Neural Voice:",
        list(VOICES.keys()),
        format_func=lambda k: f"{k} ({VOICES[k]})",
    )

    default_text = "Chào mừng bạn đến với video hôm nay. Trong bài phân tích này, chúng ta sẽ cùng khám phá công thức tối ưu nhất."
    if "current_script" in st.session_state:
        cs = st.session_state["current_script"]
        default_text = cs.get("hook", {}).get("spoken_dialogue", default_text)

    text_to_speak = st.text_area("Text to Speak:", default_text, height=180)
    rate_adj = st.select_slider("Speed Rate Adjustment:", ["-20%", "-10%", "+0%", "+10%", "+20%"], value="+0%")

    if st.button("🎙️ Generate Voiceover Audio", type="primary"):
        with st.spinner("Synthesizing neural voiceover with Edge-TTS..."):
            try:
                audio_file = generate_voiceover(text=text_to_speak, voice=voice_choice, rate=rate_adj)
                st.success(f"Audio generated: `{audio_file.name}`")
                st.audio(str(audio_file), format="audio/mp3")
                with open(audio_file, "rb") as f:
                    st.download_button("📥 Download MP3 Voiceover", f, file_name=audio_file.name, mime="audio/mp3")
                st.session_state["last_audio_file"] = str(audio_file)
            except Exception as e:
                st.error(f"TTS synthesis failed: {e}")

# -----------------------------------------------------------------------------
# TAB 4: Thumbnail Studio
# -----------------------------------------------------------------------------
with tab4:
    st.markdown('<div class="main-header">AI Thumbnail Designer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Formulate high-converting Midjourney / DALL-E prompts & render mockup graphics.</div>', unsafe_allow_html=True)

    thumb_topic = st.text_input("Thumbnail Topic / Concept:", "Quantum Computing Breaking Encryption")
    emotion = st.selectbox("Emotional Trigger:", ["High Shock & Curiosity", "Urgent Warning", "Secret Breakthrough", "Step-by-Step Mastery"])

    if st.button("🎨 Design Thumbnail Concepts", type="primary"):
        with st.spinner("Designing thumbnail prompts..."):
            try:
                t_model = design_thumbnail_prompts(thumb_topic, target_emotion=emotion)
                st.success("✅ Thumbnail Prompts Created!")
                st.markdown(f"**Visual Metaphor:** {t_model.core_visual_metaphor}")

                for idx, p in enumerate(t_model.prompts, 1):
                    with st.expander(f"Concept #{idx}: {p.variation_name} (Text Overlay: \"{p.recommended_text_overlay}\")"):
                        st.markdown(f"**Midjourney v6 Prompt:**\n```\n{p.midjourney_prompt}\n```")
                        st.markdown(f"**DALL-E 3 Prompt:**\n```\n{p.dalle_prompt}\n```")
                        st.markdown(f"**Google Imagen Prompt:**\n```\n{p.imagen_prompt}\n```")

                # Render mockup
                first_text = t_model.prompts[0].recommended_text_overlay if t_model.prompts else "NEW BREAKTHROUGH"
                mock_png = render_thumbnail_mockup(text_overlay=first_text, subtitle=thumb_topic)
                st.image(str(mock_png), caption="Rendered 720p PNG Mockup Card", use_container_width=True)
            except Exception as e:
                st.error(f"Thumbnail design failed: {e}")

# -----------------------------------------------------------------------------
# TAB 5: Video Assembly & Upload
# -----------------------------------------------------------------------------
with tab5:
    st.markdown('<div class="main-header">Automated Video Assembly & Upload</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Composite voiceover + slides + subtitles into an MP4 video and publish to YouTube.</div>', unsafe_allow_html=True)

    st.markdown("### 🎬 1-Click Video Assembly")
    audio_src = st.text_input("Path to Voiceover Audio (.mp3):", st.session_state.get("last_audio_file", ""))
    v_title = st.text_input("Video On-Screen Title:", "Quantum Computing 2026")
    v_sub = st.text_input("Video Tagline:", "The Definitive Breakdown")

    if st.button("🎥 Render 1080p MP4 Video", type="primary"):
        if not audio_src or not Path(audio_src).exists():
            st.error("Please provide a valid audio file path (or generate one in Tab 3).")
        else:
            with st.spinner("Rendering video using MoviePy and Pillow..."):
                try:
                    from video_assembler import assemble_video
                    rendered_mp4 = assemble_video(audio_path=audio_src, title=v_title, subtitle=v_sub)
                    st.success(f"✅ Video Rendered: {rendered_mp4.name}")
                    st.video(str(rendered_mp4))
                    with open(rendered_mp4, "rb") as f:
                        st.download_button("📥 Download Final MP4", f, file_name=rendered_mp4.name, mime="video/mp4")
                except Exception as e:
                    st.error(f"Video rendering error: {e}")
