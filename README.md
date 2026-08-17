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

## 🎬 4 Video Output Modes (`-mode`)

OmniDub AI supports 4 output modes for assembling your final recap video:

| Mode | Option | Video Track | Audio Track | Subtitles / Transcript | Speed | Example Command |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`-mode 1`** | **Video + Audio (DEFAULT)** | Muted Original Video | TTS Synced Voiceover | None | ⚡ **Instant (~5s)** | `python app.py "URL" -name ep1 --auto-continue` |
| **`-mode 2`** | **Video + Audio + BGM** | Muted Original Video | TTS Voiceover + Isolated BGM | None | ⚡ **Instant (~5s)** | `python app.py "URL" -name ep1 -mode 2 --auto-continue` |
| **`-mode 3`** | **Video + Audio + Transcript** | Muted Original Video | TTS Synced Voiceover | Burned Subtitles | 🐢 CPU Software Encode | `python app.py "URL" -name ep1 -mode 3 --auto-continue` |
| **`-mode 4`** | **Video + Audio + BGM + Transcript** | Muted Original Video | TTS Voiceover + Isolated BGM | Burned Subtitles | 🐢 CPU Software Encode | `python app.py "URL" -name ep1 -mode 4 --auto-continue` |

---

## ⚡ Parallel Per-File TTS Generation (`generate_tts_chunks.py`)

When you split large subtitle files into multiple `.vtt` chunks inside `Translated/` (e.g., `1_audio_txt.vtt`, `2_audio.txt.vtt`...):

```bash
# Process all translated VTT files in parallel and stitch into master voiceover
python generate_tts_chunks.py output/anime_ep1/Translated --stitch
```

* **What it does**:
  1. Runs parallel worker threads across all split `.vtt` files in `Translated/`.
  2. Generates **1-to-1 matching audio files** (`1_audio_txt.mp3`, `2_audio.txt.mp3`, etc.) with zero per-dialogue file clutter on disk.
  3. Stitches all audio files into `synced_voiceover.mp3` ready for video assembly!

---

## 💻 CLI Options Reference

| Goal | Command |
| :--- | :--- |
| **Run Initial Processing** | `python app.py "https://..." -name project1` |
| **Default Fast Merge (Video + Audio)** | `python app.py "https://..." -name project1 --auto-continue` |
| **Merge Video + Audio + BGM Music** | `python app.py "https://..." -name project1 -mode 2 --auto-continue` |
| **Merge Video + Audio + Burned Transcript** | `python app.py "https://..." -name project1 -mode 3 --auto-continue` |
| **Merge Video + Audio + BGM + Burned Transcript** | `python app.py "https://..." -name project1 -mode 4 --auto-continue` |
| **Set TTS Concurrency Workers** | `python app.py "https://..." -w 10` |
| **Set Whisper AI Model** | `python app.py "https://..." -m large-v3-turbo` |
| **Set AI Hardware Device** | `python app.py "https://..." -d cuda` |
| **Force Re-Run (Bypass Cache)** | `python app.py "https://..." --force` |
| **Choose Narrator Voice** | `python app.py "https://..." -v en-US-ChristopherNeural` |
| **Generate Chunks Per Translated VTT File** | `python generate_tts_chunks.py output/project1/Translated --stitch` |

