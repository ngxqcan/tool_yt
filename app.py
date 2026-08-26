"""Interactive Bilingual Streamlit Web Dashboard for YouTube AI Production Suite.

Includes:
- ⚡ 1-Click All-in-One Autonomous Production Pipeline (DNA -> Script -> Voiceover -> Thumbnail -> 1080p Video).
- 5 Modular Studios (Competitor Explorer, Script Studio, Voiceover Studio, Thumbnail Studio, Video Assembly).
- 100% Persistent State across all tabs with Seamless Vietnamese 🇻🇳 / English 🇬🇧 toggles.

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
from translations import get_text
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
        font-size: 2.2rem;
        font-weight: 800;
        background: -webkit-linear-gradient(45deg, #FF4B4B, #FF9900);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #8b949e;
        font-size: 1.05rem;
        margin-bottom: 1.3rem;
    }
    .metric-card {
        background-color: #1e293b;
        border-radius: 10px;
        padding: 15px;
        border-left: 5px solid #38bdf8;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# LANGUAGE SWITCHER IN SIDEBAR
# -----------------------------------------------------------------------------
if "language" not in st.session_state:
    st.session_state["language"] = "vi"

st.sidebar.markdown("# 🚀 YouTube AI Suite")

# Language Toggle Button / Radio
lang_choice = st.sidebar.radio(
    "🌐 Ngôn ngữ / Language:",
    options=["🇻🇳 Tiếng Việt", "🇬🇧 English"],
    index=0 if st.session_state["language"] == "vi" else 1,
    horizontal=True,
)
current_lang = "vi" if "Tiếng Việt" in lang_choice else "en"
st.session_state["language"] = current_lang


def t(key: str) -> str:
    """Helper to get localized text."""
    return get_text(key, lang=st.session_state["language"])


st.sidebar.markdown("---")

# Pre-flight API Key diagnostics in Sidebar
diag = validate_api_keys()
st.sidebar.markdown(f"### {t('api_status_header')}")
if diag["gemini"]["valid"]:
    st.sidebar.success(t("gemini_connected"))
else:
    st.sidebar.info(t("gemini_fallback"))

if diag["youtube"]["valid"]:
    st.sidebar.success(t("yt_active"))
else:
    st.sidebar.info(t("yt_oembed"))

st.sidebar.markdown("---")
st.sidebar.markdown(t("tip_env"))

# -----------------------------------------------------------------------------
# MAIN DASHBOARD TABS
# -----------------------------------------------------------------------------
tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs([
    t("tab0_name"),
    t("tab1_name"),
    t("tab2_name"),
    t("tab3_name"),
    t("tab4_name"),
    t("tab5_name"),
])

# -----------------------------------------------------------------------------
# TAB 0: All-in-One Autopilot
# -----------------------------------------------------------------------------
with tab0:
    st.markdown(f'<div class="main-header">{t("tab0_header")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">{t("tab0_sub")}</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 2])
    with col1:
        auto_url = st.text_input(t("auto_url_label"), "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        auto_topic = st.text_input(t("auto_topic_label"), "", placeholder=t("auto_topic_placeholder"))
    with col2:
        auto_lang = st.selectbox(t("auto_lang_label"), ["🇻🇳 Tiếng Việt", "🇬🇧 English"], index=0 if current_lang == "vi" else 1)
        lang_code = "vi" if "Tiếng Việt" in auto_lang else "en"
        default_voice_idx = 0 if lang_code == "vi" else 2
        auto_voice = st.selectbox(t("auto_voice_label"), list(VOICES.keys()), index=default_voice_idx, format_func=lambda k: f"{k} ({VOICES[k]})")

    col3, col4 = st.columns(2)
    with col3:
        auto_bgm = st.selectbox(t("auto_bgm_label"), ["cinematic", "lofi", "tech"])
    with col4:
        auto_format = st.radio(t("auto_format_label"), [t("auto_format_wide"), t("auto_format_vert")], horizontal=True)
        is_vert = auto_format == t("auto_format_vert")

    if st.button(t("btn_start_autopilot"), type="primary", use_container_width=True):
        status_box = st.status(t("btn_start_autopilot"), expanded=True)
        try:
            # 1. Competitor DNA
            status_box.update(label=t("step1_status"), state="running")
            tmpl_path = analyze_competitor_video(auto_url, force_refresh=False)
            with open(tmpl_path, "r", encoding="utf-8") as f:
                tmpl_data = json.load(f)
            st.session_state["single_dna_result"] = tmpl_data
            st.session_state["single_dna_path"] = str(tmpl_path)
            st.session_state["active_template_path"] = str(tmpl_path)

            # Determine topic
            actual_topic = auto_topic.strip()
            if not actual_topic:
                actual_topic = tmpl_data.get("topic", "The Untold Science and History")
                if lang_code == "vi" and (actual_topic == "The Untold Science and History" or "ancient" in auto_url.lower()):
                    actual_topic = "Bí Quyết Sinh Tồn Và Phát Triển Của Con Người Thời Cổ Đại"

            # 2. Script & Shorts
            status_box.update(label=t("step2_status"), state="running")
            script = generate_script(
                topic=actual_topic,
                style_template_source=tmpl_path,
                language=lang_code,
            )
            saved_script_path = save_script_outputs(script)
            st.session_state["current_script"] = script.model_dump()
            st.session_state["active_script_file"] = str(saved_script_path)

            shorts_res = generate_shorts_from_topic_or_script(actual_topic, script)
            save_shorts_outputs(shorts_res)
            st.session_state["current_shorts"] = shorts_res.model_dump()

            # 3. Voiceover
            status_box.update(label=t("step3_status"), state="running")
            full_voiceover_text = script.hook.spoken_dialogue + " " + " ".join([s.spoken_dialogue for s in script.sections]) + " " + script.call_to_action_and_outro.spoken_dialogue
            audio_file = generate_voiceover(text=full_voiceover_text, voice=auto_voice, rate="+0%")
            st.session_state["last_audio_file"] = str(audio_file)

            # 4. Thumbnail Prompts & Mockup
            status_box.update(label=t("step4_status"), state="running")
            t_model = design_thumbnail_prompts(actual_topic, target_emotion="High Shock & Curiosity")
            st.session_state["current_thumbnail_model"] = t_model.model_dump()
            first_text = t_model.prompts[0].recommended_text_overlay if t_model.prompts else actual_topic[:20]
            mock_png = render_thumbnail_mockup(text_overlay=first_text, subtitle=actual_topic)
            st.session_state["current_mockup_path"] = str(mock_png)

            # 5. Video Assembly
            status_box.update(label=t("step5_status"), state="running")
            from video_assembler import assemble_video_from_script
            rendered_mp4 = assemble_video_from_script(
                script_data=st.session_state["current_script"],
                voiceover_path=str(audio_file),
                add_bgm=True,
                bgm_genre=auto_bgm,
                is_vertical=is_vert,
            )
            st.session_state["last_video_file"] = str(rendered_mp4)
            st.session_state["autopilot_complete"] = True

            status_box.update(label=t("autopilot_success_header"), state="complete", expanded=False)
            st.balloons()

        except Exception as e:
            status_box.update(label=f"❌ Error: {e}", state="error")
            st.error(f"Autopilot failed: {e}")

    # Persistent presentation of completed All-In-One results
    if st.session_state.get("autopilot_complete") and "last_video_file" in st.session_state:
        st.markdown("---")
        st.markdown(f"## {t('autopilot_success_header')}")
        v_col1, v_col2 = st.columns([3, 2])
        with v_col1:
            st.markdown("### 🎬 Video 1080p Hoàn Chỉnh (Full AI Visuals + BGM Ducking + Phụ Đề)")
            v_path = Path(st.session_state["last_video_file"])
            if v_path.exists():
                st.video(str(v_path))
                with open(v_path, "rb") as f:
                    st.download_button(t("btn_dl_video"), f, file_name=v_path.name, mime="video/mp4", type="primary")

        with v_col2:
            st.markdown("### 🖼️ Thumbnail & Giọng Đọc Studio")
            if "current_mockup_path" in st.session_state and Path(st.session_state["current_mockup_path"]).exists():
                st.image(st.session_state["current_mockup_path"], caption=t("mockup_caption"), use_container_width=True)
            if "last_audio_file" in st.session_state and Path(st.session_state["last_audio_file"]).exists():
                st.audio(st.session_state["last_audio_file"], format="audio/mp3")

        st.markdown("---")
        # Direct Upload Expander
        with st.expander(t("yt_upload_header"), expanded=False):
            up_t = st.session_state.get("current_script", {}).get("suggested_titles", ["My New Video"])[0]
            auto_up_title = st.text_input(t("upload_title_label"), up_t, key="auto_yt_title")
            auto_up_desc = st.text_area(t("upload_desc_label"), "Auto-generated with YouTube AI Production Suite.", key="auto_yt_desc")
            auto_up_priv = st.selectbox(t("upload_privacy_label"), ["private", "unlisted", "public"], key="auto_yt_priv")
            if st.button(t("btn_upload_yt"), key="auto_yt_btn", type="secondary"):
                with st.spinner("Uploading to YouTube..."):
                    try:
                        from youtube_uploader import upload_video_to_youtube
                        v_id = upload_video_to_youtube(
                            video_file=st.session_state["last_video_file"],
                            title=auto_up_title,
                            description=auto_up_desc,
                            privacy_status=auto_up_priv,
                        )
                        st.success(f"🎉 Successfully Uploaded to YouTube! Video ID: `{v_id}`")
                        st.markdown(f"[View Video on YouTube](https://www.youtube.com/watch?v={v_id})")
                    except Exception as e:
                        st.error(f"Upload failed: {e}")

# -----------------------------------------------------------------------------
# TAB 1: Competitor & Outliers
# -----------------------------------------------------------------------------
with tab1:
    st.markdown(f'<div class="main-header">{t("tab1_header")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">{t("tab1_sub")}</div>', unsafe_allow_html=True)

    mode_options = [
        t("mode_single"),
        t("mode_multi"),
        t("mode_channel"),
        t("mode_comments"),
    ]
    mode = st.radio(t("mode_select"), mode_options, horizontal=True)

    if mode == t("mode_single"):
        vid_url = st.text_input(t("single_url_label"), "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        force_ref = st.checkbox(t("chk_bypass_cache"), value=False)
        if st.button(t("btn_analyze_dna"), type="primary"):
            with st.spinner("Extracting metadata, transcript, and Gemini structural patterns..."):
                try:
                    tmpl_path = analyze_competitor_video(vid_url, force_refresh=force_ref)
                    with open(tmpl_path, "r", encoding="utf-8") as f:
                        tmpl_data = json.load(f)
                    st.session_state["single_dna_result"] = tmpl_data
                    st.session_state["single_dna_path"] = str(tmpl_path)
                    st.session_state["active_template_path"] = str(tmpl_path)
                except Exception as e:
                    st.error(f"Analysis failed: {e}")

        # Persistent render for single DNA
        if "single_dna_result" in st.session_state:
            st.success(f"✅ DNA Extracted! Saved to: `{st.session_state.get('single_dna_path')}`")
            st.json(st.session_state["single_dna_result"])

    elif mode == t("mode_multi"):
        urls_input = st.text_area(
            t("multi_urls_label"),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ\nhttps://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        if st.button(t("btn_synthesize"), type="primary"):
            urls = [u.strip() for u in urls_input.splitlines() if u.strip()]
            with st.spinner(f"Analyzing and blending {len(urls)} videos..."):
                try:
                    comp_path = analyze_multiple_competitors(urls)
                    with open(comp_path, "r", encoding="utf-8") as f:
                        c_data = json.load(f)
                    st.session_state["multi_dna_result"] = c_data
                    st.session_state["multi_dna_path"] = str(comp_path)
                    st.session_state["active_template_path"] = str(comp_path)
                except Exception as e:
                    st.error(f"Synthesis failed: {e}")

        # Persistent render for multi DNA
        if "multi_dna_result" in st.session_state:
            st.success(f"✅ Synthesized Multi-Video Style Template Generated! Saved to: `{st.session_state.get('multi_dna_path')}`")
            st.json(st.session_state["multi_dna_result"])

    elif mode == t("mode_channel"):
        channel_input = st.text_input(t("channel_input_label"), "@mkbhd")
        min_score = st.slider(t("outlier_multiplier_label"), 1.5, 5.0, 2.0, 0.5)
        if st.button(t("btn_scan_channel"), type="primary"):
            with st.spinner("Scanning channel uploads and calculating view multipliers..."):
                try:
                    ch_res = crawl_channel_outliers(channel_input, min_outlier_multiplier=min_score)
                    st.session_state["channel_outliers_result"] = ch_res.model_dump()
                except Exception as e:
                    st.error(f"Channel crawl failed: {e}")

        # Persistent render for channel outliers
        if "channel_outliers_result" in st.session_state:
            ch_data = st.session_state["channel_outliers_result"]
            st.markdown(f"### Channel: **{ch_data.get('channel_title')}**")
            st.markdown(f"- Analyzed Videos: **{ch_data.get('total_videos_analyzed')}**")
            st.markdown(f"- Average Views: **{ch_data.get('average_view_count', 0):,.0f}** | Median: **{ch_data.get('median_view_count', 0):,.0f}**")
            st.markdown(f"- Top Keywords: `{'`, `'.join(ch_data.get('dominant_title_keywords', []))}`")

            st.markdown("#### 🔥 Viral Outlier Videos:")
            for out in ch_data.get("outlier_videos", []):
                st.markdown(f"- **[{out.get('outlier_score')}x Outlier]** [{out.get('title')}]({out.get('url')}) — *{out.get('view_count', 0):,} views*")

    elif mode == t("mode_comments"):
        comm_url = st.text_input(t("comm_url_label"), "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        if st.button(t("btn_mine_comments"), type="primary"):
            with st.spinner("Fetching comments & extracting content gaps..."):
                try:
                    gap_res = mine_video_comments(comm_url)
                    st.session_state["comment_gaps_result"] = gap_res.model_dump()
                    st.session_state["active_gaps_path"] = str(get_project_root() / "cache" / "competitor" / gap_res.video_id / "comment_gaps.json")
                except Exception as e:
                    st.error(f"Comment mining failed: {e}")

        # Persistent render for comment gaps
        if "comment_gaps_result" in st.session_state:
            gap_data = st.session_state["comment_gaps_result"]
            st.success(f"Analyzed {gap_data.get('total_comments_analyzed')} comments! Sentiment: **{gap_data.get('audience_sentiment')}**")
            st.markdown(f"### {t('unanswered_gaps_header')}")
            for gap in gap_data.get("content_gaps", []):
                st.warning(f"**Q/Critique:** {gap.get('question_or_critique')}\n\n👉 **Our Script Angle:** {gap.get('suggested_script_angle')}")
            st.markdown(f"### {t('talking_points_header')}")
            for pt in gap_data.get("recommended_talking_points", []):
                st.info(f"• {pt}")

# -----------------------------------------------------------------------------
# TAB 2: Script & Shorts Studio
# -----------------------------------------------------------------------------
with tab2:
    st.markdown(f'<div class="main-header">{t("tab2_header")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">{t("tab2_sub")}</div>', unsafe_allow_html=True)

    colA, colB = st.columns([2, 1])
    with colA:
        default_topic = "Cách Công Nghệ Lượng Tử Phá Vỡ Mã Hóa Hiện Đại" if current_lang == "vi" else "How Quantum Computing Will Break Modern Encryption"
        default_aud = "Lập trình viên, chuyên gia an ninh mạng và người yêu công nghệ" if current_lang == "vi" else "Software developers, cybersecurity researchers, and tech enthusiasts"
        topic_input = st.text_input(t("topic_label"), default_topic)
        audience_input = st.text_input(t("audience_label"), default_aud)
    with colB:
        script_lang = st.selectbox(t("script_lang_label"), ["Tiếng Việt (vi)", "English (en)"], index=0 if current_lang == "vi" else 1)
        tmpl_source = st.text_input(t("style_tmpl_label"), st.session_state.get("active_template_path", ""))
        gaps_source = st.text_input(t("gaps_label"), st.session_state.get("active_gaps_path", ""))

    gen_shorts = st.checkbox(t("chk_shorts"), value=True)

    if st.button(t("btn_generate_script"), type="primary"):
        with st.spinner("Writing 100% original script with anti-plagiarism guardrails..."):
            try:
                target_script_lang = "vi" if "Tiếng Việt" in script_lang else "en"
                script = generate_script(
                    topic=topic_input,
                    target_audience=audience_input,
                    style_template_source=tmpl_source if tmpl_source else None,
                    comment_gaps_source=gaps_source if gaps_source else None,
                    language=target_script_lang,
                )
                saved_json = save_script_outputs(script)
                st.session_state["current_script"] = script.model_dump()
                st.session_state["active_script_file"] = str(saved_json)

                if gen_shorts:
                    with st.spinner("Deriving 3 viral Shorts scripts..."):
                        shorts_res = generate_shorts_from_topic_or_script(topic_input, script)
                        save_shorts_outputs(shorts_res)
                        st.session_state["current_shorts"] = shorts_res.model_dump()

            except Exception as e:
                st.error(f"Script generation failed: {e}")

    # Persistent render for Script & Shorts
    if "current_script" in st.session_state:
        s_data = st.session_state["current_script"]
        st.success(t("script_created_success"))
        st.markdown(f"### 🎯 Suggested Titles:\n" + "\n".join([f"- **{t_title}**" for t_title in s_data.get("suggested_titles", [])]))

        with st.expander(t("hook_header"), expanded=True):
            st.markdown(f"**Dialogue:** {s_data.get('hook', {}).get('spoken_dialogue')}")
            st.info(f"**Visual & B-Roll:** {s_data.get('hook', {}).get('visual_b_roll_instructions')}")

        with st.expander(t("sections_header"), expanded=True):
            for idx, sec in enumerate(s_data.get("sections", []), 1):
                st.markdown(f"#### Beat {idx}: {sec.get('title')} (~{sec.get('duration_seconds')}s)")
                st.markdown(f"**Dialogue:** {sec.get('spoken_dialogue')}")
                st.caption(f"**Visual:** {sec.get('visual_b_roll_instructions')}")

        with st.expander(t("outro_header")):
            st.markdown(f"**Outro:** {s_data.get('call_to_action_and_outro', {}).get('spoken_dialogue')}")

        if "current_shorts" in st.session_state:
            sh_data = st.session_state["current_shorts"]
            st.markdown(f"### {t('shorts_created_header')}")
            for s_idx, sh in enumerate(sh_data.get("shorts", []), 1):
                with st.expander(f"📱 Short #{s_idx}: {sh.get('hook_title')} ({sh.get('estimated_duration_seconds')}s)"):
                    st.markdown(f"**Spoken Dialogue:**\n> {sh.get('spoken_dialogue')}")
                    st.caption(f"**Visual Cues:** {sh.get('visual_cues')}")

# -----------------------------------------------------------------------------
# TAB 3: Neural Voice Studio
# -----------------------------------------------------------------------------
with tab3:
    st.markdown(f'<div class="main-header">{t("tab3_header")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">{t("tab3_sub")}</div>', unsafe_allow_html=True)

    voice_choice = st.selectbox(
        t("voice_label"),
        options=list(VOICES.keys()),
        index=0 if current_lang == "vi" else 2,
        format_func=lambda k: f"{k} ({VOICES[k]})",
    )

    default_text = "Chào mừng bạn đến với video hôm nay. Trong bài phân tích này, chúng ta sẽ cùng khám phá công thức tối ưu nhất." if current_lang == "vi" else "Welcome to today's breakdown. In this video, we explore the definitive blueprint."
    if "current_script" in st.session_state:
        cs = st.session_state["current_script"]
        default_text = cs.get("hook", {}).get("spoken_dialogue", default_text)

    text_to_speak = st.text_area(t("text_to_speak_label"), default_text, height=180)
    rate_adj = st.select_slider(t("speed_adj_label"), ["-20%", "-10%", "+0%", "+10%", "+20%"], value="+0%")

    if st.button(t("btn_gen_voice"), type="primary"):
        with st.spinner("Synthesizing neural voiceover with Edge-TTS..."):
            try:
                audio_file = generate_voiceover(text=text_to_speak, voice=voice_choice, rate=rate_adj)
                st.session_state["last_audio_file"] = str(audio_file)
            except Exception as e:
                st.error(f"TTS synthesis failed: {e}")

    # Persistent render for Voiceover
    if "last_audio_file" in st.session_state and Path(st.session_state["last_audio_file"]).exists():
        a_file = Path(st.session_state["last_audio_file"])
        st.success(f"Audio generated: `{a_file.name}`")
        st.audio(str(a_file), format="audio/mp3")
        with open(a_file, "rb") as f:
            st.download_button(t("btn_dl_audio"), f, file_name=a_file.name, mime="audio/mp3")

# -----------------------------------------------------------------------------
# TAB 4: Thumbnail Studio
# -----------------------------------------------------------------------------
with tab4:
    st.markdown(f'<div class="main-header">{t("tab4_header")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">{t("tab4_sub")}</div>', unsafe_allow_html=True)

    default_thumb_topic = "Quantum Computing Breaking Encryption"
    thumb_topic = st.text_input(t("thumb_topic_label"), default_thumb_topic)
    emotion = st.selectbox(t("emotion_label"), ["High Shock & Curiosity", "Urgent Warning", "Secret Breakthrough", "Step-by-Step Mastery"])

    if st.button(t("btn_design_thumb"), type="primary"):
        with st.spinner("Designing thumbnail prompts..."):
            try:
                t_model = design_thumbnail_prompts(thumb_topic, target_emotion=emotion)
                st.session_state["current_thumbnail_model"] = t_model.model_dump()
                first_text = t_model.prompts[0].recommended_text_overlay if t_model.prompts else "NEW BREAKTHROUGH"
                mock_png = render_thumbnail_mockup(text_overlay=first_text, subtitle=thumb_topic)
                st.session_state["current_mockup_path"] = str(mock_png)
            except Exception as e:
                st.error(f"Thumbnail design failed: {e}")

    # Persistent render for Thumbnail Studio
    if "current_thumbnail_model" in st.session_state:
        t_data = st.session_state["current_thumbnail_model"]
        st.success("✅ Thumbnail Prompts Created!")
        st.markdown(f"**Visual Metaphor:** {t_data.get('core_visual_metaphor')}")

        for idx, p in enumerate(t_data.get("prompts", []), 1):
            with st.expander(f"Concept #{idx}: {p.get('variation_name')} (Text Overlay: \"{p.get('recommended_text_overlay')}\")"):
                st.markdown(f"**Midjourney v6 Prompt:**\n```\n{p.get('midjourney_prompt')}\n```")
                st.markdown(f"**DALL-E 3 Prompt:**\n```\n{p.get('dalle_prompt')}\n```")
                st.markdown(f"**Google Imagen Prompt:**\n```\n{p.get('imagen_prompt')}\n```")

        if "current_mockup_path" in st.session_state and Path(st.session_state["current_mockup_path"]).exists():
            st.image(st.session_state["current_mockup_path"], caption=t("mockup_caption"), use_container_width=True)

# -----------------------------------------------------------------------------
# TAB 5: Video Assembly & Upload
# -----------------------------------------------------------------------------
with tab5:
    st.markdown(f'<div class="main-header">{t("tab5_header")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub-header">{t("tab5_sub")}</div>', unsafe_allow_html=True)

    v_mode = st.radio(t("assembly_mode"), [t("mode_full_script"), t("mode_quick_slide")], horizontal=True)

    if v_mode == t("mode_full_script"):
        st.markdown(f"#### 🎬 {t('mode_full_script')}")
        if "current_script" not in st.session_state:
            st.info("💡 Generate a script in **Tab 2** first to enable 1-click full multi-scene assembly.")

        audio_src = st.text_input(t("audio_path_label"), st.session_state.get("last_audio_file", ""))
        col_bgm1, col_bgm2 = st.columns(2)
        with col_bgm1:
            bgm_genre = st.selectbox(t("bgm_genre_label"), ["lofi", "cinematic", "tech"])
        with col_bgm2:
            is_vert = st.checkbox(t("chk_vertical"), value=False)

        add_bgm = st.checkbox(t("chk_ducking"), value=True)

        if st.button(t("btn_render_master"), type="primary"):
            if not audio_src or not Path(audio_src).exists():
                st.error("Please provide a valid audio file path (or generate one in Tab 3).")
            elif "current_script" not in st.session_state:
                st.error("No active script found in session. Please generate a script in Tab 2.")
            else:
                with st.spinner("Generating 100% Free AI scene visuals, mixing BGM with Ducking & rendering 1080p MP4..."):
                    try:
                        from video_assembler import assemble_video_from_script
                        rendered_mp4 = assemble_video_from_script(
                            script_data=st.session_state["current_script"],
                            voiceover_path=audio_src,
                            add_bgm=add_bgm,
                            bgm_genre=bgm_genre,
                            is_vertical=is_vert,
                        )
                        st.session_state["last_video_file"] = str(rendered_mp4)
                    except Exception as e:
                        st.error(f"Video assembly failed: {e}")

    else:
        st.markdown(f"#### ⚡ {t('mode_quick_slide')}")
        audio_src = st.text_input(t("audio_path_label"), st.session_state.get("last_audio_file", ""), key="quick_audio")
        v_title = st.text_input("Video Title:", "Quantum Computing 2026")
        v_sub = st.text_input("Video Subtitle:", "The Definitive Breakdown")

        if st.button("🎥 Render Quick Video", type="primary"):
            if not audio_src or not Path(audio_src).exists():
                st.error("Please provide a valid audio file path (or generate one in Tab 3).")
            else:
                with st.spinner("Rendering quick 1080p video with kinetic text..."):
                    try:
                        from video_assembler import assemble_quick_video
                        rendered_mp4 = assemble_quick_video(audio_path=audio_src, title=v_title, subtitle=v_sub)
                        st.session_state["last_video_file"] = str(rendered_mp4)
                    except Exception as e:
                        st.error(f"Quick video assembly failed: {e}")

    # Persistent render for Assembled Video
    if "last_video_file" in st.session_state and Path(st.session_state["last_video_file"]).exists():
        v_file = Path(st.session_state["last_video_file"])
        st.success(f"✅ Video Rendered: `{v_file.name}`")
        st.video(str(v_file))
        with open(v_file, "rb") as f:
            st.download_button(t("btn_dl_video"), f, file_name=v_file.name, mime="video/mp4")

    st.markdown("---")
    st.markdown(f"### {t('yt_upload_header')}")
    upload_file = st.text_input("Video File to Upload:", st.session_state.get("last_video_file", ""))
    up_title = st.text_input(t("upload_title_label"), "How Quantum Computing Breaks Encryption")
    up_desc = st.text_area(t("upload_desc_label"), "Full breakdown of post-quantum cryptography.")
    up_privacy = st.selectbox(t("upload_privacy_label"), ["private", "unlisted", "public"])

    if st.button(t("btn_upload_yt"), type="secondary"):
        if not upload_file or not Path(upload_file).exists():
            st.error("Video file does not exist. Please render a video first.")
        else:
            with st.spinner("Authenticating and uploading video to YouTube..."):
                try:
                    from youtube_uploader import upload_video_to_youtube
                    vid_id = upload_video_to_youtube(
                        video_file=upload_file,
                        title=up_title,
                        description=up_desc,
                        privacy_status=up_privacy,
                    )
                    st.success(f"🎉 Successfully Uploaded to YouTube! Video ID: `{vid_id}`")
                    st.markdown(f"[View Video on YouTube](https://www.youtube.com/watch?v={vid_id})")
                except Exception as e:
                    st.error(f"Upload failed: {e}")
