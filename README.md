# 🎙️ OmniDub AI - Manhwa, Comic & Video Recap Generator

An automated, commercial-grade software engine for creating high-quality **16:9 Landscape YouTube Video Recaps** and **Video Redubbing** with AI Vision storytelling, speech-bubble OCR, frame-synced AI narration, and dynamic Ken Burns animations.

---

## 🎨 Feature 1: Manhwa & Comic Recap Generator (`app_manhwa.py`)

Turn vertical webtoons (AsuraScans, Manga, Comics, PDFs) into stunning **16:9 Landscape YouTube Recap Videos**!

### 🌟 Key Highlights:
1. **Smart OpenCV Comic Panel Isolation (`cv2.findContours`)**:
   - Detects exact drawn comic panel boxes and cuts along natural frame borders instead of fixed aspect heights.
   - Automatically crops out pure white (`RGB > 240`) and dark (`RGB < 18`) empty top/bottom margins.

2. **Page-Level Minimal AI Scripting (20x Faster)**:
   - Groups sliced panels into parent chapter pages.
   - Sends **only 38 main page images to Gemini Vision AI** per chapter instead of 800+ slice requests, eliminating API rate limit stalls completely!

3. **16:9 YouTube Landscape Video Canvas**:
   - Renders `1920x1080` YouTube landscape resolution with a styled blurred background fill (`boxblur=25:10`) overlaying sharp centered panel artwork.

4. **Multi-Threaded Parallel Execution**:
   - Speech bubble OCR, Edge-TTS audio synthesis, and FFmpeg video segment rendering execute concurrently across **8 worker threads**.

### 🚀 Quick Run Command:
```bash
python app_manhwa.py "https://asurascans.com/comics/30-years-since-the-prologue-b57aa235/chapter/1" -o my_ch1_recap
```

---

## 🎥 Feature 2: Video Redubbing Engine (`app_retimed.py` & `app.py`)

Redub foreign videos (Anime, Bilibili, YouTube) into **natural English speech speed** with frame-synced audio and background music.

```bash
# Natural speech retimed video recap
python app_retimed.py "https://www.bilibili.com/video/BV1kqMF64Ego/" -name anime_ep1 -v en-US-AriaNeural --burn-subtitles --auto-continue -mode 4
```

---

## 🛠️ Setup & Installation Guide

### Step 1: Prerequisites
1. **Python 3.9+**: Download and install from [python.org](https://www.python.org/downloads/).
   > ⚠️ **Windows Users**: Ensure you check **"Add Python to PATH"** during installation.

2. **FFmpeg**: Essential for video rendering and audio processing.
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

---

## 💻 CLI Command Options (`app_manhwa.py`)

| Goal | Command |
| :--- | :--- |
| **Standard 16:9 YouTube Recap** | `python app_manhwa.py "URL"` |
| **Custom Project Name** | `python app_manhwa.py "URL" -o my_project` |
| **9:16 Vertical Reel / Shorts** | `python app_manhwa.py "URL" -o my_shorts --aspect 9:16` |
| **Custom Parallel Worker Threads** | `python app_manhwa.py "URL" -w 12` |
| **Custom Voice Narrator** | `python app_manhwa.py "URL" -v en-US-ChristopherNeural` |
| **Force Re-Run (Bypass Cache)** | `python app_manhwa.py "URL" --force` |

---

## 📁 Output Directory Architecture

Each project generates clean, organized output artifacts under `output/<project_name>/`:

```text
output/<project_name>/
├── FINAL_MANHWA_RECAP.mp4     <-- 🎉 Final 16:9 Landscape Video File
├── master_audio.mp3           <-- 🎙️ Full Narration Audio Track
├── master_script.txt          <-- 📝 Full Story Script
├── ocr_results.json           <-- 🔤 Extracted Speech Bubble Text
├── raw_pages/                 📁 Downloaded Chapter Pages (38 pages)
├── images/manhwa_slices/      📁 Smart OpenCV Cropped Comic Panels
└── audio/                     📁 Individual Panel TTS Audio Clips
```
