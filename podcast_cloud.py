# run command:
#                             streamlit run podcast_cloud.py
#                  directory setup: cd C:\users\oakhtar\documents\pyprojs_local
#   OPTIMIZED for deployment -
#

import streamlit as st
import os
import tempfile
import asyncio
import json
import edge_tts
import requests
import shutil
import re
from pathlib import Path
from pydub import AudioSegment

# --- TEXT PROCESSING ---
import PyPDF2
import docx
from bs4 import BeautifulSoup

# --- AI CLIENT ---
from openai import OpenAI

# ================= CONFIGURATION =================
st.set_page_config(
    page_title="PodcastLM Cloud (OpenAI)", 
    page_icon="🎙️", 
    layout="centered",
    initial_sidebar_state="expanded"
)

# ================= SESSION STATE =================
if "script_data" not in st.session_state:
    st.session_state.script_data = None
if "audio_path" not in st.session_state:
    st.session_state.audio_path = None

# ================= UTILITY FUNCTIONS =================

def check_ffmpeg():
    """Checks if FFmpeg is installed"""
    if shutil.which("ffmpeg") is None:
        st.error("🚨 **System Error: FFmpeg not found.**")
        st.markdown("Please ensure `packages.txt` contains `ffmpeg` in your GitHub repo.")
        return False
    return True

def extract_text_from_files(files):
    """Extracts text from uploaded files"""
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
            st.warning(f"Could not read {file.name}: {e}")
    return text

def clean_text_for_audio(text):
    """Removes markdown and special characters that break EdgeTTS"""
    # Remove bold/italic markdown
    text = text.replace("*", "").replace("_", "")
    # Remove quotes that might look weird
    text = text.replace('"', "").replace("'", "")
    return text.strip()

async def generate_tts_with_retry(text, voice, output_path):
    """
    Generates audio with a retry mechanism.
    EdgeTTS acts up on Cloud servers, so we try 3 times.
    """
    text = clean_text_for_audio(text)
    if not text: return # Skip empty lines
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
            return # Success
        except Exception as e:
            if attempt == max_retries - 1:
                # If last attempt failed, raise the error
                raise e
            # Wait 1 second before retrying
            await asyncio.sleep(1)

# ================= MAIN UI =================

st.title("🎙️ PodcastLM Cloud")
st.caption("Powered by OpenAI GPT-4o-mini & EdgeTTS")

if not check_ffmpeg():
    st.stop()

# --- SIDEBAR SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # 1. API Key Handling
    api_key = None
    if "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]
        st.success("✅ API Key loaded")
    else:
        api_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")
        st.caption("[Get Key Here](https://platform.openai.com/api-keys)")

    st.divider()
    
    # 2. Voice Settings
    voice_style = st.selectbox("Podcast Style", [
        "NPR Style (Balanced)", 
        "Morning Radio (Energetic)", 
        "British Documentarian",
    ])
    
    voice_map = {
        "NPR Style (Balanced)": ("en-US-GuyNeural", "en-US-JennyNeural"),
        "Morning Radio (Energetic)": ("en-US-ChristopherNeural", "en-US-AriaNeural"),
        "British Documentarian": ("en-GB-RyanNeural", "en-GB-SoniaNeural"),
    }
    
    add_music = st.checkbox("Add Background Music", value=True)

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["1. Input Content", "2. Edit Script", "3. Listen"])

# ================= TAB 1: INPUT =================
with tab1:
    input_method = st.radio("Input Source", ["Upload Files", "Paste Text"], horizontal=True)
    
    final_text = ""
    
    if input_method == "Upload Files":
        files = st.file_uploader("Drop PDF, DOCX, or TXT files", accept_multiple_files=True)
        if files:
            with st.spinner("Reading files..."):
                final_text = extract_text_from_files(files)
                st.caption(f"Loaded {len(final_text)} characters.")
    else:
        final_text = st.text_area("Paste Article / Text Here", height=300)

    if st.button("Generate Script", type="primary"):
        if not api_key:
            st.error("Please provide an OpenAI API Key.")
        elif len(final_text) < 50:
            st.error("Text is too short.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                
                prompt = f"""
                You are a podcast producer. Convert the source text into an engaging dialogue between two hosts, Alex (Male) and Sam (Female).
                
                Rules:
                1. Make it sound natural (include brief laughs, 'hmm', 'exactly').
                2. Do not just summarize; discuss the content as friends.
                3. Length: Approx 12-16 exchanges.
                
                Output strictly JSON format:
                {{
                    "title": "Catchy Title",
                    "dialogue": [
                        {{"speaker": "Alex", "text": "..."}},
                        {{"speaker": "Sam", "text": "..."}}
                    ]
                }}
                
                Source Text:
                {final_text[:20000]} 
                """
                
                with st.spinner("Writing script with GPT-4o-mini..."):
                    completion = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "You are a helpful scriptwriter."},
                                  {"role": "user", "content": prompt}],
                        temperature=0.7,
                        response_format={"type": "json_object"}
                    )
                    
                    script_json = json.loads(completion.choices[0].message.content)
                    st.session_state.script_data = script_json
                    st.session_state.audio_path = None
                    st.success("Script generated! Go to the 'Edit Script' tab.")
                        
            except Exception as e:
                st.error(f"OpenAI Error: {e}")

# ================= TAB 2: EDIT =================
with tab2:
    if st.session_state.script_data:
        data = st.session_state.script_data
        st.subheader(f"Title: {data.get('title', 'Podcast')}")
        
        with st.form("edit_script_form"):
            updated_dialogue = []
            for i, line in enumerate(data['dialogue']):
                col_a, col_b = st.columns([1, 5])
                with col_a:
                    speakers = ["Alex", "Sam"]
                    current_idx = 0 if line['speaker'] == "Alex" else 1
                    new_speaker = st.selectbox(f"Speaker", speakers, index=current_idx, key=f"spk_{i}", label_visibility="collapsed")
                with col_b:
                    new_text = st.text_area(f"Line {i+1}", value=line['text'], height=70, key=f"txt_{i}", label_visibility="collapsed")
                updated_dialogue.append({"speaker": new_speaker, "text": new_text})
            
            if st.form_submit_button("Save Changes"):
                st.session_state.script_data['dialogue'] = updated_dialogue
                st.success("Script updated.")
    else:
        st.info("Generate a script in Tab 1 first.")

# ================= TAB 3: AUDIO =================
with tab3:
    if st.session_state.script_data:
        if st.button("🚀 Generate Audio (MP3)", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            m_voice, f_voice = voice_map[voice_style]
            script = st.session_state.script_data['dialogue']
            
            # Create Temp Dir
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                audio_segments = []
                
                total_lines = len(script)
                
                for idx, line in enumerate(script):
                    status_text.text(f"Recording line {idx+1} of {total_lines}...")
                    
                    voice = m_voice if line['speaker'] == "Alex" else f_voice
                    filename = temp_path / f"line_{idx}.mp3"
                    
                    try:
                        # Call the new Retry Function
                        asyncio.run(generate_tts_with_retry(line['text'], voice, str(filename)))
                        
                        # Append Audio
                        seg = AudioSegment.from_file(filename)
                        audio_segments.append(seg)
                        audio_segments.append(AudioSegment.silent(duration=300)) # Pause
                        
                    except Exception as e:
                        st.warning(f"Skipped line {idx+1} due to error: {e}")
                    
                    progress_bar.progress((idx + 1) / (total_lines + 1))

                # Mix Audio
                status_text.text("Mixing audio...")
                if audio_segments:
                    final_audio = sum(audio_segments)
                    
                    if add_music:
                        try:
                            music_url = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=lofi-study-112191.mp3"
                            music_data = requests.get(music_url, timeout=10).content
                            with open(temp_path / "bg_music.mp3", "wb") as f:
                                f.write(music_data)
                            bg_music = AudioSegment.from_file(temp_path / "bg_music.mp3")
                            bg_music = bg_music - 25 # Lower Volume
                            
                            # Loop Music
                            while len(bg_music) < len(final_audio) + 5000:
                                bg_music += bg_music
                            
                            # Trim and Fade
                            bg_music = bg_music[:len(final_audio) + 1000].fade_out(2000)
                            final_audio = bg_music.overlay(final_audio)
                        except Exception as e:
                            st.warning(f"Music failed to load, skipping music: {e}")

                    # Export
                    output_filename = "podcast_output.mp3"
                    final_audio.export(output_filename, format="mp3")
                    st.session_state.audio_path = output_filename
                    progress_bar.progress(100)
                    status_text.text("Done! Audio Ready below.")
                else:
                    st.error("No audio segments were generated successfully.")

        if st.session_state.audio_path:
            st.audio(st.session_state.audio_path)
            with open(st.session_state.audio_path, "rb") as f:
                st.download_button("Download MP3", f, file_name="my_podcast.mp3")
    else:
        st.info("Generate a script in Tab 1 first.")

