# 🎙️ OmniDub AI - Multithreaded Video Redubbing & Recap Engine

An automated, commercial-grade software engine for turning foreign videos (anime, drama, movies, recap videos) from **any video platform** into high-quality **English redubbed recap videos** with time-synced AI narration and background music.

---

## 🛠️ Setup & Installation Guide

### Step 1: Prerequisites

1. **Python 3.9+**: Download and install from [python.org](https://www.python.org/downloads/).
   > ⚠️ **Windows Users**: Ensure you check the box **"Add Python to PATH"** during installation.

2. **FFmpeg**: Essential for video processing and audio time-stretching.
   - **Windows**: `winget install ffmpeg` (or download from [ffmpeg.org](https://ffmpeg.org))
   - **macOS**: `brew install ffmpeg`
   - **Linux**: `sudo apt update && sudo apt install ffmpeg`

### Step 2: Clone Repository & Install Dependencies

```bash
# 1. Clone the repository
git clone https://github.com/jaypal1046/OmniDub.git
cd OmniDub

# 2. Install Python dependencies
pip install -r requirements.txt
```

### Step 3: Verify Installation

Run the help command to ensure all CLI arguments are recognized:
```bash
python app.py --help
```

---

## 📁 Dedicated `translated/` Subfolder Architecture

Each project creates a dedicated `translated/` subfolder containing your translated narration text:

```text
output/<project_id>/
├── state.json              <-- State Persistence & Step Manager
├── video.mp4               <-- Original MP4 Video
├── audio.mp3               <-- Original Audio Track
├── audio.vtt               <-- Original Transcribed Chinese Subtitles (Whisper)
├── bgm_music.mp3           <-- Isolated Background Music & SFX (Demucs AI)
├── synced_voiceover.mp3    <-- Frame-Synced English Narration (Edge-TTS)
├── FINAL_RECAP.mp4         <-- 🎉 Final Redubbed Recap Video
└── translated/             📁 Dedicated Subfolder for Translated Subtitles
    └── audio.vtt           📝 Edit/Translate this file for voiceover narration!
```

---

## ⚡ Workflow (Automatic Detection on Re-run)

### Step 1: Initial Processing
```powershell
python app.py "https://www.youtube.com/watch?v=t95pOwN8NFY" -name anime_ep1
```
* **What happens**: Downloads video/audio, creates `audio.vtt` (original), creates `translated/audio.vtt` template, isolates `bgm_music.mp3`, and pauses.

### Step 2: Translate Subtitles
Open `output/anime_ep1/translated/audio.vtt` in your editor, translate the subtitle lines into English (or your target language), and save it.

### Step 3: Resume to Build Final Video
```powershell
python app.py "https://www.youtube.com/watch?v=t95pOwN8NFY" -name anime_ep1 --auto-continue --burn-subtitles
```
* **What happens**: Automatically detects `translated/audio.vtt`, generates frame-synced English voiceover narration, and merges `FINAL_RECAP.mp4`!

---

## 💻 CLI Options

| Goal | Command |
| :--- | :--- |
| **Run Initial Processing** | `python app.py "https://..." -name project1` |
| **Resume After Editing `translated/audio.vtt`** | `python app.py "https://..." -name project1 --auto-continue` |
| **Force Re-Run (Bypass Cache)** | `python app.py "https://..." --force` |
| **Choose Narrator Voice** | `python app.py "https://..." -v en-US-ChristopherNeural` |
| **Burn Subtitles onto Video** | `python app.py "https://..." --burn-subtitles` |
| **List Available Narrator Voices** | `python list_sample_voices.py` |
