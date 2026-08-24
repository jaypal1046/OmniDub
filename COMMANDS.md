# 📜 CLI Commands Reference & Cheat Sheet

This guide explains **when to run which command** and provides copy-paste ready examples for all recap workflows.

---

## 🧭 Engine Overview: Which Engine Should I Use?

| Engine | Command | Description | Best Used For |
| :--- | :--- | :--- | :--- |
| **Command 1: Standard Recap Engine** | `python app.py ...` | Fast stream-copy merge. Original video duration **never changes**. Speech audio is fitted to original timestamps. | Quick recaps where exact video length must be preserved. |
| **Command 2: Retimed Engine** *(Recommended)* | `python app_retimed.py ...` | **100% Natural English speech speed**. Video motion dynamically retimes (stretches/pauses smoothly) so the story flows comfortably without rushed speech. | Comfortable, high-quality storytelling where narration sounds natural and clear. |

---

## 🛠️ Step-by-Step Production Workflow

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

## ⚡ Useful Options & Flags

| Flag | Purpose | Example |
| :--- | :--- | :--- |
| `-v <voice>` | Change Edge-TTS Narrator Voice | `-v en-US-ChristopherNeural` or `-v en-US-AriaNeural` |
| `-w <num>` | Parallel TTS Concurrency Workers | `-w 15` (Faster TTS generation) |
| `-m <model>` | Whisper Speech Recognition Model | `-m large-v3-turbo` or `-m medium` |
| `-d <device>` | AI Acceleration Hardware | `-d cuda` (Use NVIDIA GPU) or `-d cpu` |
| `--force` | Bypass cached state and force re-run all steps | `--force` |
| `--auto-continue` | Skip manual pause prompt and continue to video merge | `--auto-continue` |

---

## 🎙️ Popular Narrator Voice Choices (`-v`)

- `en-US-AriaNeural` (Female - Natural, expressive storyteller)
- `en-US-GuyNeural` (Male - Deep, natural narrator)
- `en-US-ChristopherNeural` (Male - Energetic recap style)
- `en-US-JennyNeural` (Female - Clear & polite)
- `en-GB-SoniaNeural` (British Female)
