# Setup Guide: yt-dlp, Whisper, Coqui TTS, UVR, Spleeter, Shotcut

Most of these are free tools that run on your own computer. A few (Whisper, Coqui TTS, Spleeter) need **Python** installed first since they're Python-based AI tools — that's covered once at the top so you don't repeat it.

---

## 0. One-Time Prerequisite: Install Python

Whisper, Coqui TTS, and Spleeter all run on Python. yt-dlp also installs cleanest via Python's package manager.

1. Go to **python.org/downloads**
2. Download the latest Python 3 installer for your OS (Windows/Mac)
3. **Windows only:** during install, tick the box **"Add Python to PATH"** before clicking Install — this is the step people most often miss
4. Verify it worked: open Terminal (Mac) or Command Prompt (Windows) and type:
   ```
   python --version
   ```
   It should print something like `Python 3.12.x`

You'll also want **FFmpeg** installed — it's a free tool that handles audio/video conversion behind the scenes for Whisper, yt-dlp, and others.
- **Windows:** download from ffmpeg.org, extract it, and add the folder to your system PATH (or easier: `winget install ffmpeg` in Command Prompt if you have winget)
- **Mac:** open Terminal and run `brew install ffmpeg` (requires Homebrew — install from brew.sh first if you don't have it)

---

## 1. yt-dlp (download source videos)

**What it does:** Downloads video files from YouTube, Bilibili, etc. from the command line.

**Install:**
```
pip install yt-dlp
```
Run that in Terminal/Command Prompt. `pip` is Python's package installer — it downloads yt-dlp and makes it available as a command.

**Use it:**
```
yt-dlp "https://www.youtube.com/watch?v=VIDEO_ID"
```
Paste any video URL in place of the link. It downloads the best-quality version into your current folder.

**Common options:**
```
yt-dlp -f mp4 "URL"          # force MP4 format
yt-dlp -x --audio-format mp3 "URL"   # extract audio only, as MP3
```

**Update it later** (sites change often, so update regularly):
```
pip install -U yt-dlp
```

---

## 2. OpenAI Whisper (transcribe Chinese audio to text)

**What it does:** Listens to an audio/video file and outputs a text transcript with timestamps.

**Install:**
```
pip install -U openai-whisper
```
This also needs FFmpeg (installed in Step 0) since Whisper uses it to read audio.

**Use it:**
```
whisper "video.mp4" --language Chinese --model medium
```
- Replace `video.mp4` with your file name
- `--model` controls accuracy vs. speed: `tiny` and `base` are fast but less accurate; `medium` is a good balance; `large` is most accurate but slow and needs a strong GPU
- Output: it creates `.txt`, `.srt` (subtitle format with timestamps), and `.vtt` files in the same folder

**No GPU / slow computer?** Use `--model tiny` or `--model base` first to test the pipeline, then upgrade model size once you confirm everything works. Alternatively, run Whisper for free in **Google Colab** (a free cloud notebook with GPU access) instead of your own machine — search "Whisper Google Colab notebook" for ready-made templates.

---

## 3. Coqui TTS (free English voiceover generation)

**What it does:** Converts your English script text into spoken audio, running entirely on your own computer (no cloud, no character limits).

**Install:**
```
pip install TTS
```

**Use it (basic):**
```
tts --text "Your English script goes here" --out_path output.wav
```
This uses a default voice model. First run will auto-download the model files (can take a few minutes).

**List available voices/models:**
```
tts --list_models
```
Then pick one and use it:
```
tts --text "Your script" --model_name "tts_models/en/vctk/vits" --out_path output.wav
```

**Note:** This is more setup-heavy than a cloud tool like ElevenLabs — expect some trial and error picking a model that sounds natural. A GPU speeds generation up a lot but isn't required for short scripts.

---

## 4. Ultimate Vocal Remover / UVR (remove Chinese dialogue, keep music/SFX)

**What it does:** Splits an audio track into "vocals" and "everything else" (music/sound effects) using AI.

**Install (this one has a proper installer, not pip):**
1. Go to **github.com/Anjok07/ultimatevocalremovergui**
2. Under Releases, download the installer for your OS (Windows `.exe`, or Mac version)
3. Run the installer like any normal program — it bundles Python and everything it needs, so you don't need to configure anything extra

**Use it:**
1. Open the UVR app
2. Load your video/audio file
3. Pick a model — for isolating dialogue from music, use one from the **"MDX-Net"** or **"Demucs"** category (these are pre-trained separation models included with the app)
4. Click **Start Processing**
5. It outputs two files: one with just vocals, one with vocals removed (music/SFX only) — keep the second one

**Tip:** First-time processing downloads the AI model files (a few hundred MB), so the first run takes longer.

---

## 5. Spleeter (alternative free audio separator)

**What it does:** Same job as UVR — separates vocals from music — built by Deezer, simpler but less fine-tuned.

**Install:**
```
pip install spleeter
```

**Use it:**
```
spleeter separate -p spleeter:2stems -o output_folder your_audio.wav
```
- `2stems` means it splits into 2 tracks: vocals and accompaniment (music/effects) — this is what you want
- `-o output_folder` sets where the split files go
- Output: `output_folder/your_audio/vocals.wav` and `accompaniment.wav` — keep the accompaniment one

**Note:** Spleeter needs an audio file (WAV/MP3), not a video file directly — extract audio first with FFmpeg:
```
ffmpeg -i video.mp4 -q:a 0 -map a audio.wav
```

---

## 6. Shotcut (free video editor)

**What it does:** Standard drag-and-drop video editor — assemble your video, sync the new voiceover, add music, export.

**Install:**
1. Go to **shotcut.org**
2. Click **Download**, pick your OS (Windows/Mac/Linux)
3. Run the installer like any normal application — no command line needed, no Python needed

**Basic workflow once installed:**
1. Open Shotcut → **Open File** → load your source video
2. Drag it onto the timeline
3. **Open File** again → load your English voiceover (from Coqui TTS/ElevenLabs) and the music/SFX-only track (from UVR/Spleeter)
4. Drag both onto separate audio tracks on the timeline, lined up under the video
5. Mute or delete the original video's audio track
6. Trim/nudge clips left-right so the voiceover timing matches on-screen action
7. **Export** → choose MP4 → Export File

---

## Quick Reference: Install Commands

```bash
# One-time setup
# Install Python from python.org first, then:

pip install yt-dlp
pip install -U openai-whisper
pip install TTS
pip install spleeter

# UVR and Shotcut: download installers from their websites, no pip needed
```

## Troubleshooting Tips

- **"pip: command not found"** → Python wasn't added to PATH during install; reinstall Python and check that box, or reinstall pip with `python -m ensurepip`
- **Whisper/Spleeter very slow** → these run much faster with an NVIDIA GPU; on a laptop without one, use smaller models (Whisper: `tiny`/`base`) and expect longer processing times, especially for longer videos
- **UVR won't open / crashes on launch** → make sure you downloaded the right installer for your OS version, and that your antivirus isn't blocking it (it's a large open-source app, sometimes falsely flagged)
