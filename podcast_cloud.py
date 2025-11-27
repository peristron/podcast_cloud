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
import traceback
from pathlib import Path
from pydub import AudioSegment

# --- TEXT PROCESSING ---
import PyPDF2
import docx

# --- AI CLIENT ---
from openai import OpenAI

# ================= CONFIGURATION =================
st.set_page_config(
    page_title="PodcastLM Cloud (Debug Mode)", 
    page_icon="🎙️", 
    layout="centered"
)

# ================= SESSION STATE & LOGGING =================
if "script_data" not in st.session_state:
    st.session_state.script_data = None
if "audio_path" not in st.session_state:
    st.session_state.audio_path = None
if "logs" not in st.session_state:
    st.session_state.logs = []

def log_msg(msg, level="INFO"):
    """Adds a message to the visible debug log"""
    formatted = f"[{level}] {msg}"
    print(formatted) # Print to server console
    st.session_state.logs.append(formatted)

# ================= UTILITY FUNCTIONS =================

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
            log_msg(f"Successfully extracted {len(text)} chars from {name}")
        except Exception as e:
            log_msg(f"Error reading {file.name}: {e}", "ERROR")
    return text

def clean_text_for_audio(text):
    # Remove special characters that break TTS headers
    clean = text.replace("*", "").replace("#", "").replace('"', "").replace("\n", " ").strip()
    return clean

async def generate_single_line(text, voice, filename):
    """Generates a single audio file with specific error handling"""
    if not text:
        return False
    
    try:
        # Validate inputs
        if not voice or not filename:
            raise ValueError("Missing voice or filename")

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(filename)
        return True
    except Exception as e:
        log_msg(f"TTS Gen Failed for text: '{text[:20]}...' | Error: {str(e)}", "ERROR")
        return False

async def process_script_async(script, m_voice, f_voice, temp_path, progress_bar, status_text):
    """Batch processor"""
    generated_files = []
    total = len(script)
    
    for i, line in enumerate(script):
        status_text.text(f"Processing line {i+1}/{total}...")
        
        speaker = line['speaker']
        text = clean_text_for_audio(line['text'])
        voice = m_voice if speaker == "Alex" else f_voice
        filename = str(temp_path / f"line_{i}.mp3")
        
        log_msg(f"Line {i+1}: Speaker={speaker}, Voice={voice}, Text Length={len(text)}")
        
        # Retry loop
        success = False
        for attempt in range(3):
            success = await generate_single_line(text, voice, filename)
            if success:
                generated_files.append(filename)
                break
            else:
                log_msg(f"Retry {attempt+1} for line {i+1}...", "WARN")
                await asyncio.sleep(1.5) # Backoff
        
        if not success:
            log_msg(f"PERMANENT FAILURE on line {i+1}", "CRITICAL")
        
        progress_bar.progress((i + 1) / total)
        
    return generated_files

def run_async_safely(coroutine):
    """
    Creates a fresh event loop to avoid Streamlit/Tornado conflicts.
    This is the most robust way to run asyncio on Cloud.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coroutine)
        loop.close()
        return result
    except Exception as e:
        log_msg(f"Event Loop Error: {e}", "CRITICAL")
        log_msg(traceback.format_exc(), "DEBUG")
        return None

# ================= MAIN UI =================

st.title("🎙️ PodcastLM Cloud")
st.caption("Powered by OpenAI & EdgeTTS")

if not check_ffmpeg():
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        api_key = st.text_input("OpenAI API Key", type="password")
    else:
        st.success("✅ API Key Loaded")

    st.divider()
    
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
tab1, tab2, tab3 = st.tabs(["1. Input", "2. Edit", "3. Listen"])

# TAB 1: INPUT
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
        st.session_state.logs = [] # Clear logs
        log_msg("Starting Script Generation...")
        
        if not api_key or len(final_text) < 50:
            st.error("Need API Key and valid text.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                prompt = f"""
                Create a podcast script (Alex=Male, Sam=Female).
                Title: Catchy title.
                Dialogue: 10-15 exchanges. Casual, friendly, engaging.
                Format: JSON {{ "title": "...", "dialogue": [{{"speaker": "...", "text": "..."}}] }}
                Text: {final_text[:15000]}
                """
                with st.spinner("Writing script..."):
                    res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"}
                    )
                    st.session_state.script_data = json.loads(res.choices[0].message.content)
                    st.session_state.audio_path = None
                    log_msg("Script generated successfully.")
                    st.success("Script Ready! Click Tab 2.")
            except Exception as e:
                log_msg(f"OpenAI Error: {e}", "ERROR")
                st.error(f"Error: {e}")

# TAB 2: EDIT
with tab2:
    if st.session_state.script_data:
        data = st.session_state.script_data
        with st.form("edit_form"):
            new_dialogue = []
            for i, line in enumerate(data['dialogue']):
                c1, c2 = st.columns([1, 5])
                spk = c1.selectbox("Speaker", ["Alex", "Sam"], index=0 if line['speaker']=="Alex" else 1, key=f"s{i}")
                txt = c2.text_area("Line", line['text'], height=60, key=f"t{i}", label_visibility="collapsed")
                new_dialogue.append({"speaker": spk, "text": txt})
            
            if st.form_submit_button("Save Script"):
                st.session_state.script_data['dialogue'] = new_dialogue
                st.success("Saved!")

# TAB 3: AUDIO
with tab3:
    if st.session_state.script_data:
        if st.button("🚀 Generate Audio", type="primary"):
            log_msg("Starting Audio Generation...")
            progress = st.progress(0)
            status = st.empty()
            m_voice, f_voice = voice_map[voice_style]
            
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                
                # RUN THE SAFE LOOP
                generated_files = run_async_safely(
                    process_script_async(
                        st.session_state.script_data['dialogue'],
                        m_voice, f_voice, tmp_path, progress, status
                    )
                )
                
                if generated_files and len(generated_files) > 0:
                    log_msg(f"Generated {len(generated_files)} audio segments.")
                    status.text("Stitching audio...")
                    
                    try:
                        combined = AudioSegment.empty()
                        for f in generated_files:
                            combined += AudioSegment.from_file(f)
                            combined += AudioSegment.silent(duration=300)
                        
                        if add_music:
                            try:
                                log_msg("Downloading music...")
                                music_url = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=lofi-study-112191.mp3"
                                m_data = requests.get(music_url, timeout=5).content
                                with open(tmp_path / "music.mp3", "wb") as f: f.write(m_data)
                                bg = AudioSegment.from_file(tmp_path / "music.mp3") - 25
                                while len(bg) < len(combined) + 5000: bg += bg
                                combined = bg[:len(combined)+1000].fade_out(2000).overlay(combined)
                            except Exception as e:
                                log_msg(f"Music Error: {e}", "WARN")
                        
                        out_path = "podcast.mp3"
                        combined.export(out_path, format="mp3")
                        st.session_state.audio_path = out_path
                        log_msg("Audio Export Complete.")
                        st.rerun()
                        
                    except Exception as e:
                        log_msg(f"Stitching Error: {e}", "CRITICAL")
                        st.error("Error combining audio files. Check logs.")
                else:
                    st.error("No audio generated. Check Debug Log below.")

        if st.session_state.audio_path:
            st.audio(st.session_state.audio_path)
            with open(st.session_state.audio_path, "rb") as f:
                st.download_button("Download MP3", f, "podcast.mp3")

# --- DEBUG SECTION ---
with st.expander("🛠️ Debug Console (Expand if Error)", expanded=False):
    st.write("System Logs:")
    for log in st.session_state.logs:
        if "[ERROR]" in log or "[CRITICAL]" in log:
            st.error(log)
        elif "[WARN]" in log:
            st.warning(log)
        else:
            st.text(log)




