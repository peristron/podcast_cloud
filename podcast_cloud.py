# run command:
#                             streamlit run podcast_cloud.py
#                  directory setup: cd C:\users\oakhtar\documents\pyprojs_local
#   OPTIMIZED for deployment -
#

import streamlit as st
import os
import tempfile
import json
import requests
import shutil
from pathlib import Path
from pydub import AudioSegment

# --- TEXT PROCESSING ---
import PyPDF2
import docx

# --- AI CLIENT ---
from openai import OpenAI

# ================= CONFIGURATION =================
st.set_page_config(
    page_title="PodcastLM Cloud (Secured)", 
    page_icon="🔒", 
    layout="centered"
)

# ================= AUTHENTICATION =================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_password():
    """Checks the password against Streamlit Secrets"""
    user_pass = st.session_state.get("password_input", "")
    correct_pass = st.secrets.get("APP_PASSWORD")
    
    if correct_pass and user_pass == correct_pass:
        st.session_state.authenticated = True
    else:
        st.error("❌ Incorrect Password")

if not st.session_state.authenticated:
    st.title("🔒 Login Required")
    st.markdown("Please enter the access password to use this app.")
    st.text_input("Password", type="password", key="password_input", on_change=check_password)
    st.stop() # STOP HERE if not authenticated

# ================= APP STARTS HERE (Only runs if logged in) =================

# --- SESSION STATE ---
if "script_data" not in st.session_state:
    st.session_state.script_data = None
if "audio_path" not in st.session_state:
    st.session_state.audio_path = None

# --- UTILS ---
def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        st.error("🚨 FFmpeg not found. Please ensure `packages.txt` contains `ffmpeg`.")
        return False
    return True

def extract_text_from_files(files):
    text = ""
    for file in files:
        try:
            name = file.name.lower()
            if name.endswith(".pdf"):
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages: text += page.extract_text() + "\n"
            elif name.endswith(".docx"):
                doc = docx.Document(file)
                for para in doc.paragraphs: text += para.text + "\n"
            elif name.endswith(".txt"):
                text = file.getvalue().decode("utf-8")
        except Exception as e:
            st.error(f"Error reading {file.name}: {e}")
    return text

def generate_audio_openai(client, text, voice, filename):
    try:
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text
        )
        response.stream_to_file(filename)
        return True
    except Exception as e:
        st.error(f"OpenAI TTS Error: {e}")
        return False

# --- MAIN UI ---
st.title("🎙️ PodcastLM Cloud")
st.caption("Powered by OpenAI (GPT-4o-mini & TTS-1)")

if not check_ffmpeg():
    st.stop()

with st.sidebar:
    st.header("⚙️ Settings")
    
    # API Key from Secrets (Preferred) or Input
    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        api_key = st.text_input("OpenAI API Key", type="password")
    
    st.divider()
    
    # Length Control
    length_option = st.select_slider(
        "Podcast Length", 
        options=["Short (2 min)", "Medium (5 min)", "Long (15-30 min)"],
        value="Short (2 min)"
    )
    
    voice_style = st.selectbox("Voice Style", [
        "Dynamic (Alloy & Nova)", 
        "Calm (Onyx & Shimmer)", 
        "Formal (Echo & Fable)",
    ])
    
    voice_map = {
        "Dynamic (Alloy & Nova)": ("alloy", "nova"),
        "Calm (Onyx & Shimmer)": ("onyx", "shimmer"),
        "Formal (Echo & Fable)": ("echo", "fable"),
    }
    
    add_music = st.checkbox("Add Background Music", value=True)

tab1, tab2, tab3 = st.tabs(["1. Input", "2. Edit", "3. Listen"])

with tab1:
    input_method = st.radio("Source", ["Upload Files", "Paste Text"], horizontal=True)
    final_text = ""
    
    if input_method == "Upload Files":
        files = st.file_uploader("Drop PDF/DOCX/TXT", accept_multiple_files=True)
        if files:
            with st.spinner("Processing..."):
                final_text = extract_text_from_files(files)
    else:
        final_text = st.text_area("Paste Text", height=300)

    if st.button("Generate Script", type="primary"):
        if not api_key or len(final_text) < 50:
            st.error("Need valid API Key and text.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                
                # Adjust prompt based on length selection
                length_instruction = "10-12 exchanges (approx 2 minutes)"
                if "Medium" in length_option:
                    length_instruction = "25-30 exchanges (approx 5 minutes). Go deeper into the topic."
                elif "Long" in length_option:
                    length_instruction = "At least 50 exchanges (approx 15-20 minutes). Very detailed discussion, deep dive."

                prompt = f"""
                Create a podcast script (Host 1 = Male, Host 2 = Female).
                Title: Catchy title.
                Goal: {length_instruction}
                Style: Casual, friendly, engaging banter.
                Format: JSON {{ "title": "...", "dialogue": [{{"speaker": "Host 1", "text": "..."}}, {{"speaker": "Host 2", "text": "..."}}] }}
                Source Text: {final_text[:25000]}
                """
                
                with st.spinner("Writing script..."):
                    res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"}
                    )
                    st.session_state.script_data = json.loads(res.choices[0].message.content)
                    st.session_state.audio_path = None
                    st.success("Script Ready! Click Tab 2.")
            except Exception as e:
                st.error(f"Error: {e}")

with tab2:
    if st.session_state.script_data:
        data = st.session_state.script_data
        st.subheader(f"Title: {data.get('title', 'Podcast')}")
        st.info("💡 Tip: You can edit the text below before generating audio.")
        
        with st.form("edit_form"):
            new_dialogue = []
            for i, line in enumerate(data['dialogue']):
                c1, c2 = st.columns([1, 5])
                spk = c1.selectbox("Speaker", ["Host 1", "Host 2"], index=0 if line['speaker']=="Host 1" else 1, key=f"s{i}")
                txt = c2.text_area("Line", line['text'], height=60, key=f"t{i}", label_visibility="collapsed")
                new_dialogue.append({"speaker": spk, "text": txt})
            
            if st.form_submit_button("Save Script Changes"):
                st.session_state.script_data['dialogue'] = new_dialogue
                st.success("Script updated!")

with tab3:
    if st.session_state.script_data:
        if st.button("🚀 Generate Audio", type="primary"):
            if not api_key:
                st.error("Missing API Key")
                st.stop()
                
            progress = st.progress(0)
            status = st.empty()
            client = OpenAI(api_key=api_key)
            m_voice, f_voice = voice_map[voice_style]
            
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                audio_segments = []
                script = st.session_state.script_data['dialogue']
                
                for i, line in enumerate(script):
                    status.text(f"Recording line {i+1} of {len(script)}...")
                    
                    voice = m_voice if line['speaker'] == "Host 1" else f_voice
                    filename = str(tmp_path / f"line_{i}.mp3")
                    
                    success = generate_audio_openai(client, line['text'], voice, filename)
                    
                    if success:
                        seg = AudioSegment.from_file(filename)
                        audio_segments.append(seg)
                        audio_segments.append(AudioSegment.silent(duration=400))
                    
                    progress.progress((i + 1) / len(script))
                
                if audio_segments:
                    status.text("Mixing audio...")
                    combined = sum(audio_segments)
                    
                    if add_music:
                        try:
                            music_url = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=lofi-study-112191.mp3"
                            m_data = requests.get(music_url, timeout=10).content
                            with open(tmp_path / "music.mp3", "wb") as f: f.write(m_data)
                            bg = AudioSegment.from_file(tmp_path / "music.mp3") - 25
                            
                            # Loop music to fit length
                            while len(bg) < len(combined) + 10000: bg += bg
                            combined = bg[:len(combined)+1000].fade_out(2000).overlay(combined)
                        except Exception as e:
                            st.warning(f"Music skipped: {e}")
                            
                    out_path = "podcast.mp3"
                    combined.export(out_path, format="mp3")
                    st.session_state.audio_path = out_path
                    status.text("Done!")
                    st.rerun()
                else:
                    st.error("Audio generation failed.")
                    
        if st.session_state.audio_path:
            st.audio(st.session_state.audio_path)
            with open(st.session_state.audio_path, "rb") as f:
                st.download_button("Download MP3", f, "podcast.mp3")






