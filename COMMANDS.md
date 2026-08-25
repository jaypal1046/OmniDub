# 📜 CLI Commands Reference & Cheat Sheet

This guide explains **when to run which command** and provides copy-paste ready examples for all recap workflows.

---

## 🧭 Engine Overview: Which Engine Should I Use?

| Engine | Command | Description | Best Used For |
| :--- | :--- | :--- | :--- |
| **Engine 1: Manhwa 16:9 Recap Engine** *(Recommended)* | `python app_manhwa.py ...` | Smart OpenCV comic panel slicing (`cv2.findContours`), page-level minimal AI Vision scripting (38 calls max), 16:9 landscape video layout (`1920x1080`) with blurred background canvas, and parallel TTS audio/video rendering. | **AsuraScans / Webtoon / Comic Recap Videos** for YouTube. |
| **Engine 2: Retimed Video Engine** | `python app_retimed.py ...` | **100% Natural English speech speed**. Video motion dynamically retimes (stretches/pauses smoothly) so the story flows comfortably without rushed speech. | Comfortable, high-quality video storytelling where narration sounds natural. |
| **Engine 3: Standard Video Recap Engine** | `python app.py ...` | Fast stream-copy merge. Original video duration **never changes**. Speech audio is fitted to original timestamps. | Quick recaps where exact video length must be preserved. |

---

## 🎨 Manhwa & Webtoon Recap Generator Commands (`app_manhwa.py`)

### 1. Basic 16:9 Landscape YouTube Video (Default)
```bash
python app_manhwa.py "https://asurascans.com/comics/30-years-since-the-prologue-b57aa235/chapter/1"
```

### 2. Custom Output Folder Name (`-o`)
```bash
python app_manhwa.py "https://asurascans.com/comics/30-years-since-the-prologue-b57aa235/chapter/1" -o my_ch1_recap
```

### 3. 9:16 Vertical Reel / Shorts Aspect Ratio (`--aspect 9:16`)
```bash
python app_manhwa.py "https://asurascans.com/comics/30-years-since-the-prologue-b57aa235/chapter/1" -o ch1_reels --aspect 9:16
```

### 4. Custom Parallel Worker Threads (`-w`)
```bash
python app_manhwa.py "https://asurascans.com/comics/30-years-since-the-prologue-b57aa235/chapter/1" -w 12
```

### 5. Custom Narrator Voice (`-v`)
```bash
python app_manhwa.py "https://asurascans.com/comics/30-years-since-the-prologue-b57aa235/chapter/1" -v en-US-AriaNeural
```

### 6. Force Re-run All Pipeline Steps (`--force`)
```bash
python app_manhwa.py "https://asurascans.com/comics/30-years-since-the-prologue-b57aa235/chapter/1" -o my_ch1_recap --force
```

---

## 🛠️ Step-by-Step Video Production Workflow (`app_retimed.py` & `app.py`)

### Step 1: Initial Processing (Download & Transcribe)
Run either engine to download the video, extract audio, and generate original subtitles.

```bash
python app.py "https://www.bilibili.com/video/BV1kqMF64Ego/" -name bilibili_anime_5
```

> **Note:** The pipeline will pause automatically after Step 1/2 so you can translate your subtitles.

---

### Step 2: Add or Edit Translations
Add your translated subtitle files inside the `output/<project_name>/Translated/` folder (e.g. `1_audio_txt.vtt`, `2_audio_txt.vtt`, or a single `audio.vtt`).

---

### Step 3: Generate Final Video

#### Option A: Natural Audio-Driven Retimed Video *(RECOMMENDED)*
Use `app_retimed.py` for comfortable natural voiceover and smooth video retiming.

* **Video + Voiceover + Burned Subtitles (NO BGM):**
  ```bash
  python app_retimed.py "https://www.bilibili.com/video/BV1kqMF64Ego/" -name bilibili_anime_5 -v en-US-AriaNeural --burn-subtitles --auto-continue -mode 3
  ```

* **Video + Voiceover + BGM + Burned Subtitles:**
  ```bash
  python app_retimed.py "https://www.bilibili.com/video/BV1kqMF64Ego/" -name bilibili_anime_5 -v en-US-AriaNeural --burn-subtitles --auto-continue -mode 4
  ```

---

#### Option B: Fast Standard Fixed-Duration Video
Use `app.py` for fast processing where video duration remains identical to original.

* **Video + Voiceover + Burned Subtitles (NO BGM):**
  ```bash
  python app.py "https://www.bilibili.com/video/BV1kqMF64Ego/" -name bilibili_anime_5 -v en-US-AriaNeural --burn-subtitles --auto-continue -mode 3
  ```

* **Video + Voiceover + BGM + Burned Subtitles:**
  ```bash
  python app.py "https://www.bilibili.com/video/BV1kqMF64Ego/" -name bilibili_anime_5 -v en-US-AriaNeural --burn-subtitles --auto-continue -mode 4
  ```

---

## 🎛️ Output Modes Reference (`-mode`)

| Mode | What it Includes | FFmpeg Speed |
| :--- | :--- | :--- |
| `-mode 1` | Video + Voiceover Audio *(Default)* | Fast Stream Copy (~5s) |
| `-mode 2` | Video + Voiceover Audio + Isolated BGM Music | Audio Re-mix (~10s) |
| **`-mode 3`** | **Video + Voiceover Audio + Burned Subtitles (NO BGM)** | Subtitle Re-encode |
| `-mode 4` | Video + Voiceover Audio + Isolated BGM + Burned Subtitles | Audio Re-mix + Subtitle Re-encode |

---

## 🎙️ Popular Narrator Voice Choices (`-v`)

- `en-US-AriaNeural` (Female - Natural, expressive storyteller)
- `en-US-GuyNeural` (Male - Deep, natural narrator)
- `en-US-ChristopherNeural` (Male - Energetic recap style)
- `en-US-JennyNeural` (Female - Clear & polite)
- `en-GB-SoniaNeural` (British Female)
