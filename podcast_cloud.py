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
import re
from pathlib import Path
from pydub import AudioSegment

# --- TEXT PROCESSING ---
import PyPDF2
import docx
from bs4 import BeautifulSoup
import yt_dlp

# --- AI CLIENT ---
from openai import OpenAI

# ================= CONFIGURATION =================
st.set_page_config(
    page_title="PodcastLM Studio", 
    page_icon="🎧", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= AUTHENTICATION =================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_password():
    user_pass = st.session_state.get("password_input", "")
    correct_pass = st.secrets.get("APP_PASSWORD")
    if correct_pass and user_pass == correct_pass:
        st.session_state.authenticated = True
    else:
        st.error("❌ Incorrect Password")

if not st.session_state.authenticated:
    st.title("🔒 Studio Login")
    st.text_input("Enter Password", type="password", key="password_input", on_change=check_password)
    st.stop()

# ================= UTILS & SCRAPERS =================

def download_file_with_headers(url, save_path):
    """Downloads a file using browser headers to avoid 403 blocks"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, stream=True, timeout=15)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        return False
    except Exception as e:
        print(f"Download Error: {e}")
        return False

def download_and_transcribe_video(url, client):
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(tmp_dir, 'audio.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }],
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                }
            }
            
            st.info("⏳ Downloading audio stream...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            audio_path = os.path.join(tmp_dir, "audio.mp3")
            
            if not os.path.exists(audio_path):
                return None, "Download failed (403 Forbidden). Try uploading the file manually."

            file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
            if file_size_mb > 24:
                return None, "Audio > 25MB. Please use a shorter video."

            st.info("📝 Transcribing with Whisper...")
            with open(audio_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file
                )
            return transcript.text, None

    except Exception as e:
        return None, str(e)

def scrape_website(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        for script in soup(["script", "style", "header", "footer", "nav"]):
            script.decompose()
        return soup.get_text()
    except Exception as e:
        return None

def extract_text_from_files(files, client=None):
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
            elif name.endswith((".mp3", ".mp4", ".wav", ".m4a")):
                if client:
                    with st.spinner(f"Transcribing {name}..."):
                        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(name)[1]) as tmp_file:
                            tmp_file.write(file.getvalue())
                            tmp_path = tmp_file.name
                        with open(tmp_path, "rb") as audio_file:
                            transcript = client.audio.transcriptions.create(model="whisper-1", file=audio_file)
                        text += transcript.text + "\n"
                        os.remove(tmp_path)
                else:
                    st.warning(f"Skipped {name}: API Key required.")
        except Exception as e:
            st.error(f"Error reading {file.name}: {e}")
    return text

def generate_audio_openai(client, text, voice, filename, speed=1.0):
    try:
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
            speed=speed
        )
        response.stream_to_file(filename)
        return True
    except Exception as e:
        st.error(f"TTS Error: {e}")
        return False

# ================= MAIN UI =================

with st.sidebar:
    st.title("🎛️ Studio Settings")
    
    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        api_key = st.text_input("OpenAI API Key", type="password")
    
    privacy_mode = st.toggle("🛡️ Privacy Mode", value=False)
    st.divider()

    st.subheader("🌍 Localization")
    language_options = [
        "English (US)", "English (UK)", "Spanish (Spain)", "Spanish (LatAm)", 
        "French", "German", "Italian", "Portuguese", "Portuguese (Brazil)",
        "Japanese", "Chinese (Mandarin)", "Korean", "Hindi", "Urdu", "Arabic", "Russian",
        "Turkish", "Dutch", "Polish", "Swedish", "Danish", "Norwegian", "Finnish",
        "Greek", "Czech", "Romanian", "Indonesian", "Vietnamese", "Thai", "Hebrew"
    ]
    language = st.selectbox("Output Language", language_options)
    
    length_option = st.select_slider(
        "Target Duration", 
        options=["Short (2 min)", "Medium (5 min)", "Long (15 min)", "Extra Long (30 min)"],
        value="Short (2 min)"
    )

    st.subheader("🎭 Hosts")
    host1_persona = st.text_input("Host 1 Persona", "Male, curious, slightly skeptical")
    host2_persona = st.text_input("Host 2 Persona", "Female, enthusiastic expert, fast talker")
    
    voice_style = st.selectbox("Voice Pair", [
        "Dynamic (Alloy & Nova)", 
        "Calm (Onyx & Shimmer)", 
        "Formal (Echo & Fable)",
    ])
    voice_map = {
        "Dynamic (Alloy & Nova)": ("alloy", "nova"),
        "Calm (Onyx & Shimmer)": ("onyx", "shimmer"),
        "Formal (Echo & Fable)": ("echo", "fable"),
    }

    st.markdown("---")
    st.subheader("🎵 Music & Branding")
    
    # 1. Background Music Selection
    bg_source = st.radio("Background Music", ["Presets", "Upload Custom", "None"], horizontal=True)
    
    selected_bg_url = None
    uploaded_bg_file = None
    
    if bg_source == "Presets":
        music_choice = st.selectbox("Select Track", ["Lo-Fi (Study)", "Upbeat (Morning)", "Ambient (News)", "Cinematic (Deep)", "Jazz (Lounge)"])
        music_urls = {
            "Lo-Fi (Study)": "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=lofi-study-112191.mp3",
            "Upbeat (Morning)": "https://cdn.pixabay.com/download/audio/2024/05/24/audio_95e3f5f471.mp3?filename=good-morning-206098.mp3",
            "Ambient (News)": "https://cdn.pixabay.com/download/audio/2022/03/10/audio_c8c8a73467.mp3?filename=ambient-piano-10226.mp3",
            "Cinematic (Deep)": "https://cdn.pixabay.com/download/audio/2022/03/22/audio_c2b86c77ce.mp3?filename=cinematic-atmosphere-score-2-21266.mp3",
            "Jazz (Lounge)": "https://cdn.pixabay.com/download/audio/2020/05/30/audio_1736f460a0.mp3?filename=chill-jazzy-lofi-beat-2831.mp3"
        }
        selected_bg_url = music_urls[music_choice]
    elif bg_source == "Upload Custom":
        uploaded_bg_file = st.file_uploader("Upload Loop (MP3/WAV)", type=["mp3", "wav"])

    # 2. Intro / Outro
    with st.expander("Intro & Outro Clips (Optional)"):
        uploaded_intro = st.file_uploader("Intro Audio (Plays before)", type=["mp3", "wav"])
        uploaded_outro = st.file_uploader("Outro Audio (Plays after)", type=["mp3", "wav"])


st.title("🎧 PodcastLM Studio")

if "script_data" not in st.session_state:
    st.session_state.script_data = None

tab1, tab2, tab3 = st.tabs(["1. Source Material", "2. Script Editor", "3. Audio Production"])

# ================= TAB 1: INPUT =================
with tab1:
    input_type = st.radio("Select Input", ["📂 Upload Files (PDF/Docs/Audio/Video)", "🔗 Web URL", "📺 Video URL (Download)", "📝 Paste Text"], horizontal=True)
    final_text = ""
    
    if input_type == "📂 Upload Files (PDF/Docs/Audio/Video)":
        files = st.file_uploader("Upload Files", accept_multiple_files=True)
        if files: 
            client = OpenAI(api_key=api_key) if api_key else None
            final_text = extract_text_from_files(files, client)
            
    elif input_type == "🔗 Web URL":
        url = st.text_input("Enter Article URL")
        if url: 
            with st.spinner("Scraping website..."):
                scraped = scrape_website(url)
                if scraped: final_text = scraped
                else: st.error("Blocked by website.")
                
    elif input_type == "📺 Video URL (Download)":
        vid_url = st.text_input("Enter Video URL")
        if vid_url and st.button("Process Video"):
            if not api_key: st.error("API Key required.")
            else:
                client = OpenAI(api_key=api_key)
                text, error = download_and_transcribe_video(vid_url, client)
                if text:
                    final_text = text
                    st.session_state.video_text_cache = text 
                    st.success("Success!")
                else: st.error(f"Error: {error}")
        if "video_text_cache" in st.session_state and not final_text:
            final_text = st.session_state.video_text_cache

    elif input_type == "📝 Paste Text":
        final_text = st.text_area("Paste Content", height=300)

    if final_text:
        with st.expander("👁️ View Source Text"):
            st.text_area("Preview", final_text, height=200, disabled=True)

    if st.button("Generate Script", type="primary"):
        if not api_key: st.error("Missing API Key")
        elif not final_text or len(final_text) < 50: st.error("No source text.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                
                length_instr = "12-15 exchanges (approx 2-3 mins). Keep it punchy."
                if "Medium" in length_option: length_instr = "30 exchanges. Go deep. Use analogies."
                elif "Long" in length_option: length_instr = "At least 50 exchanges. Deep Dive. Expand on every point."
                elif "Extra Long" in length_option: length_instr = "80-100 exchanges (approx 30 mins). Comprehensive analysis."

                prompt = f"""
                Create a podcast script.
                Language: {language}
                Length: {length_instr}
                Host 1: {host1_persona}
                Host 2: {host2_persona}
                Rules: Natural conversation, interruptions, laughs.
                Format: JSON {{ "title": "...", "dialogue": [ {{"speaker": "Host 1", "text": "..."}} ] }}
                Text: {final_text[:35000]}
                """
                
                with st.spinner("Drafting Script..."):
                    res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"}
                    )
                    st.session_state.script_data = json.loads(res.choices[0].message.content)
                    st.success("Script Ready! Go to Tab 2.")
                    
                    if privacy_mode:
                        final_text = "" 
                        if "video_text_cache" in st.session_state: del st.session_state.video_text_cache
                        
            except Exception as e: st.error(f"Error: {e}")

# ================= TAB 2: EDIT =================
with tab2:
    if st.session_state.script_data:
        data = st.session_state.script_data
        st.subheader(f"Title: {data.get('title', 'Podcast')}")
        with st.form("edit_form"):
            new_dialogue = []
            for i, line in enumerate(data['dialogue']):
                c1, c2 = st.columns([1, 5])
                spk = c1.selectbox("Role", ["Host 1", "Host 2"], index=0 if line['speaker']=="Host 1" else 1, key=f"s{i}")
                txt = c2.text_area("Dialogue", line['text'], height=70, key=f"t{i}")
                new_dialogue.append({"speaker": spk, "text": txt})
            if st.form_submit_button("Save Script"):
                st.session_state.script_data['dialogue'] = new_dialogue
                st.success("Saved.")

# ================= TAB 3: AUDIO =================
with tab3:
    if st.session_state.script_data:
        if st.button("🎙️ Start Production", type="primary"):
            if not api_key: st.stop()
            
            progress = st.progress(0)
            status = st.empty()
            client = OpenAI(api_key=api_key)
            m_voice, f_voice = voice_map[voice_style]
            
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                audio_segments = []
                script = st.session_state.script_data['dialogue']
                
                # 1. GENERATE DIALOGUE
                for i, line in enumerate(script):
                    status.text(f"Recording line {i+1}/{len(script)}...")
                    voice = m_voice if line['speaker'] == "Host 1" else f_voice
                    f_path = str(tmp_path / f"line_{i}.mp3")
                    if generate_audio_openai(client, line['text'], voice, f_path):
                        seg = AudioSegment.from_file(f_path)
                        audio_segments.append(seg)
                        audio_segments.append(AudioSegment.silent(duration=350)) # Pause between lines
                    progress.progress((i+1)/len(script))
                
                # 2. MIXING
                if audio_segments:
                    status.text("Mixing Dialogue...")
                    dialogue_track = sum(audio_segments)
                    
                    # --- BACKGROUND MUSIC ---
                    if bg_source != "None":
                        bg_segment = None
                        try:
                            if bg_source == "Presets" and selected_bg_url:
                                # FIX: Use Headers to download Pixabay file
                                bg_path = tmp_path / "bg.mp3"
                                if download_file_with_headers(selected_bg_url, bg_path):
                                    bg_segment = AudioSegment.from_file(bg_path)
                                else:
                                    st.warning("Could not download background music. Continuing without it.")
                            
                            elif bg_source == "Upload Custom" and uploaded_bg_file:
                                with open(tmp_path / "bg_custom.mp3", "wb") as f: f.write(uploaded_bg_file.getvalue())
                                bg_segment = AudioSegment.from_file(tmp_path / "bg_custom.mp3")

                            # Process BG (Loop & Duck)
                            if bg_segment:
                                bg_segment = bg_segment - 22 # Lower Volume
                                while len(bg_segment) < len(dialogue_track) + 5000:
                                    bg_segment += bg_segment
                                bg_segment = bg_segment[:len(dialogue_track)+2000].fade_out(3000)
                                dialogue_track = bg_segment.overlay(dialogue_track)
                        
                        except Exception as e:
                            st.warning(f"Background Music Error: {e}")

                    # --- INTRO / OUTRO STITCHING ---
                    final_mix = dialogue_track
                    
                    try:
                        if uploaded_intro:
                            status.text("Adding Intro...")
                            with open(tmp_path / "intro.mp3", "wb") as f: f.write(uploaded_intro.getvalue())
                            intro_seg = AudioSegment.from_file(tmp_path / "intro.mp3")
                            final_mix = intro_seg + final_mix
                        
                        if uploaded_outro:
                            status.text("Adding Outro...")
                            with open(tmp_path / "outro.mp3", "wb") as f: f.write(uploaded_outro.getvalue())
                            outro_seg = AudioSegment.from_file(tmp_path / "outro.mp3")
                            final_mix = final_mix + outro_seg
                            
                    except Exception as e:
                        st.warning(f"Intro/Outro Error: {e}")

                    # 3. EXPORT
                    status.text("Finalizing...")
                    out_file = tmp_path / "podcast_master.mp3"
                    final_mix.export(out_file, format="mp3", bitrate="192k")
                    
                    with open(out_file, "rb") as f:
                        audio_bytes = f.read()
                    
                    status.success("Production Complete!")
                    st.audio(audio_bytes, format="audio/mp3")
                    st.download_button(label="💾 Download MP3", data=audio_bytes, file_name="podcast_master.mp3", mime="audio/mp3")
