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
import re
import edge_tts
import requests
import shutil
from pathlib import Path
from pydub import AudioSegment

# --- TEXT PROCESSING ---
import PyPDF2
import docx
from bs4 import BeautifulSoup

# --- AI CLIENT ---
from groq import Groq

# ================= CONFIGURATION =================
st.set_page_config(
    page_title="PodcastLM Cloud", 
    page_icon="🎙️", 
    layout="centered", # Centered is easier on the eyes for reading scripts
    initial_sidebar_state="expanded"
)

# ================= SESSION STATE =================
if "script_data" not in st.session_state:
    st.session_state.script_data = None
if "audio_path" not in st.session_state:
    st.session_state.audio_path = None

# ================= UTILITY FUNCTIONS =================

def check_ffmpeg():
    """Checks if FFmpeg is installed (Critical for Cloud)"""
    if shutil.which("ffmpeg") is None:
        st.error("🚨 **System Error: FFmpeg not found.**")
        st.markdown("""
            If running locally: Install FFmpeg and add to PATH.  
            If on Streamlit Cloud: Create a file named `packages.txt` in your repo and write `ffmpeg` inside it.
        """)
        return False
    return True

def clean_text(text):
    """Sanitize text for TTS"""
    return text.replace("*", "").replace("#", "").strip()

def extract_text_from_files(files):
    """Extracts text from various file formats"""
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

def parse_json_output(raw_text):
    """Robust JSON extractor for LLM responses"""
    try:
        # Try direct parsing first
        return json.loads(raw_text)
    except:
        # If LLM added chatter, find the first '{' and last '}'
        try:
            start = raw_text.find('{')
            end = raw_text.rfind('}') + 1
            if start != -1 and end != -1:
                json_str = raw_text[start:end]
                return json.loads(json_str)
        except:
            return None

async def generate_tts_audio(text, voice, output_path):
    """Async wrapper for EdgeTTS"""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

# ================= MAIN UI =================

st.title("🎙️ PodcastLM Cloud")
st.markdown("Turn documents or text into a realistic 2-person podcast.")

if not check_ffmpeg():
    st.stop()

# --- SIDEBAR SETTINGS ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    # 1. API Key Handling (Priority: Secrets > User Input)
    api_key = None
    if "GROQ_API_KEY" in st.secrets:
        api_key = st.secrets["GROQ_API_KEY"]
        st.success("✅ API Key loaded from Secrets")
    else:
        api_key = st.text_input("Groq API Key", type="password", placeholder="gsk_...")
        st.caption("[Get a Free Key Here](https://console.groq.com/keys)")

    st.divider()
    
    # 2. Voice Settings
    voice_style = st.selectbox("Podcast Style", [
        "NPR Style (Balanced)", 
        "Morning Radio (Energetic)", 
        "British Documentarian",
    ])
    
    # Mapping friendly names to EdgeTTS voices
    # Format: (Male Voice, Female Voice)
    voice_map = {
        "NPR Style (Balanced)": ("en-US-GuyNeural", "en-US-JennyNeural"),
        "Morning Radio (Energetic)": ("en-US-ChristopherNeural", "en-US-AriaNeural"),
        "British Documentarian": ("en-GB-RyanNeural", "en-GB-SoniaNeural"),
    }
    
    model_choice = st.selectbox("LLM Model", ["llama3-8b-8192", "llama3-70b-8192"], index=1)
    add_music = st.checkbox("Add Background Music", value=True)

# --- TABS FOR WORKFLOW ---
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
            st.error("Please provide an API Key in the sidebar.")
        elif len(final_text) < 50:
            st.error("Text is too short. Please add more content.")
        else:
            # --- LLM GENERATION ---
            try:
                client = Groq(api_key=api_key)
                
                prompt = f"""
                You are a podcast producer. Convert the provided text into an engaging dialogue between two hosts, Alex (Male) and Sam (Female).
                
                Rules:
                1. Make it sound natural (include brief laughs, 'hmm', 'exactly').
                2. Do not just summarize; discuss the content.
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
                {final_text[:15000]} 
                """
                
                with st.spinner("Writing the script... (This takes ~5 seconds)"):
                    completion = client.chat.completions.create(
                        model=model_choice,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.7,
                        response_format={"type": "json_object"}
                    )
                    
                    parsed_json = parse_json_output(completion.choices[0].message.content)
                    
                    if parsed_json and "dialogue" in parsed_json:
                        st.session_state.script_data = parsed_json
                        st.session_state.audio_path = None # Reset audio
                        st.success("Script generated! Go to the 'Edit Script' tab.")
                    else:
                        st.error("The AI failed to format the script correctly. Please try again.")
                        
            except Exception as e:
                st.error(f"API Error: {e}")

# ================= TAB 2: EDIT =================
with tab2:
    if st.session_state.script_data:
        data = st.session_state.script_data
        
        st.subheader(f"Title: {data.get('title', 'Podcast')}")
        
        # We use a form so the page doesn't reload on every character type
        with st.form("edit_script_form"):
            updated_dialogue = []
            
            for i, line in enumerate(data['dialogue']):
                col_a, col_b = st.columns([1, 5])
                with col_a:
                    # Speaker toggle
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
            
            # Create a temp directory for processing
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                audio_segments = []
                
                # 1. Generate Speech
                for idx, line in enumerate(script):
                    status_text.text(f"Recording line {idx+1} of {len(script)}...")
                    
                    voice = m_voice if line['speaker'] == "Alex" else f_voice
                    filename = temp_path / f"line_{idx}.mp3"
                    
                    # Run Async TTS
                    asyncio.run(generate_tts_audio(line['text'], voice, str(filename)))
                    
                    # Process Audio
                    seg = AudioSegment.from_file(filename)
                    audio_segments.append(seg)
                    
                    # Add small pause between speakers
                    audio_segments.append(AudioSegment.silent(duration=300))
                    
                    progress_bar.progress((idx + 1) / (len(script) + 1))

                # 2. Combine & Music
                status_text.text("Mixing audio...")
                final_audio = sum(audio_segments)
                
                if add_music:
                    try:
                        # Download Lo-Fi track
                        music_url = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=lofi-study-112191.mp3"
                        music_data = requests.get(music_url).content
                        with open(temp_path / "bg_music.mp3", "wb") as f:
                            f.write(music_data)
                        
                        bg_music = AudioSegment.from_file(temp_path / "bg_music.mp3")
                        
                        # Lower volume significantly
                        bg_music = bg_music - 22 
                        
                        # Loop music if script is longer than song
                        while len(bg_music) < len(final_audio) + 5000:
                            bg_music += bg_music
                            
                        # Trim to length + fade out
                        bg_music = bg_music[:len(final_audio) + 1000].fade_out(2000)
                        
                        # Overlay
                        final_audio = bg_music.overlay(final_audio)
                    except Exception as e:
                        st.warning(f"Could not add music: {e}")

                # 3. Export
                output_filename = "podcast_output.mp3"
                final_audio.export(output_filename, format="mp3")
                st.session_state.audio_path = output_filename
                
                progress_bar.progress(100)
                status_text.text("Ready!")

        # Show Player
        if st.session_state.audio_path:
            st.audio(st.session_state.audio_path)
            with open(st.session_state.audio_path, "rb") as f:
                st.download_button("Download MP3", f, file_name="my_podcast.mp3")

    else:
        st.info("Generate a script in Tab 1 first.")