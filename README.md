# 🎙️ PodcastLM Cloud

A free, open-source alternative to NotebookLM. Convert PDFs, Word docs, and text into realistic, two-person audio podcasts using Llama 3 and Neural Text-to-Speech.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-Cloud-red)
![Groq](https://img.shields.io/badge/Powered%20by-Groq-orange)

## ✨ Features

*   **📄 Multi-Format Input:** Upload PDFs, DOCX files, or simply paste text.
*   **⚡ Blazing Fast:** Uses Groq's LPU inference engine (Llama 3) to write scripts in seconds.
*   **🗣️ Realistic Audio:** Uses EdgeTTS for high-quality, neural voice synthesis (no robotic sounds).
*   **📝 Human-in-the-loop:** Review and edit the script before generating audio to ensure accuracy.
*   **🎵 Audio Mixing:** Automatically mixes dialogue with background Lo-Fi music.
*   **☁️ Cloud Ready:** Optimized for one-click deployment on Streamlit Community Cloud.

## 🚀 How to Deploy (Free)

You can deploy this app for free on Streamlit Community Cloud. You only need a GitHub account.

### 1. Prepare your Repository
Create a new GitHub repository and add these **3 essential files**:

1.  **`app.py`**: The main application code.
2.  **`requirements.txt`**:
    ```text
    streamlit
    groq
    edge-tts
    pydub
    python-docx
    PyPDF2
    beautifulsoup4
    requests
    ```
3.  **`packages.txt`** (Crucial for audio processing):
    ```text
    ffmpeg
    ```

### 2. Deploy to Streamlit
1.  Go to [share.streamlit.io](https://share.streamlit.io/).
2.  Click **New App**.
3.  Select your repository and point to `app.py`.
4.  Click **Deploy**.

### 3. Add your API Key
Once deployed, the app will launch. To make it work:
1.  Get a free API Key from [Groq Console](https://console.groq.com/keys).
2.  On your Streamlit App, click **Settings** (bottom right) -> **Secrets**.
3.  Paste the following:
    ```toml
    GROQ_API_KEY = "gsk_your_key_here"
    ```
4.  Save. The app is now live and ready for public use!

---

## 💻 Running Locally

If you prefer to run this on your own machine:

1.  **Clone the repo:**
    ```bash
    git clone https://github.com/yourusername/podcastlm-cloud.git
    cd podcastlm-cloud
    ```

2.  **Install FFmpeg:**
    *   *Windows:* [Download here](https://ffmpeg.org/download.html) and add to System PATH.
    *   *Mac:* `brew install ffmpeg`
    *   *Linux:* `sudo apt install ffmpeg`

3.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the app:**
    ```bash
    streamlit run app.py
    ```

## 🛠️ Tech Stack

*   **Frontend:** [Streamlit](https://streamlit.io/)
*   **LLM (Scripting):** Llama 3 via [Groq Cloud](https://groq.com/)
*   **TTS (Audio):** [EdgeTTS](https://github.com/rany2/edge-tts) (Microsoft Azure Neural Voices)
*   **Audio Processing:** [Pydub](https://github.com/jiaaro/pydub) & FFmpeg

## 📄 License

MIT License. Feel free to fork, modify, and distribute.
