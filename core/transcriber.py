import os
import shutil
import subprocess

def transcribe_media(audio_path, project_dir, source_lang="Chinese", model="medium",
                     device=None, compute_type=None, vad_filter=True, batched=True,
                     threads=None, condition_on_previous_text=False, **kwargs):
    """
    Transcribes audio using faster-whisper (whisper-ctranslate2) into project_dir.
    Applies VAD filtering, anti-repetition penalties, and condition_on_previous_text=False
    to eliminate Whisper hallucination loops.
    """
    print(f"\n[2/5] Transcribing Audio ({source_lang}) to Subtitles (Model: {model})...")
    
    cmd = [
        "whisper-ctranslate2", audio_path,
        "--output_dir", project_dir,
        "--language", source_lang,
        "--model", model,
        "--condition_on_previous_text", "True" if condition_on_previous_text else "False",
        "--repetition_penalty", "1.2"
    ]

    if vad_filter:
        cmd.extend(["--vad_filter", "True"])

    if device:
        cmd.extend(["--device", str(device)])

    if compute_type:
        cmd.extend(["--compute_type", str(compute_type)])

    if threads:
        cmd.extend(["--threads", str(threads)])

    print(f"🎙️ Running Whisper command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    raw_vtt = os.path.join(project_dir, f"{base_name}.vtt")
    raw_srt = os.path.join(project_dir, f"{base_name}.srt")

    orig_vtt = os.path.join(project_dir, "audio.vtt")
    orig_srt = os.path.join(project_dir, "audio.srt")

    # Standardize original transcript path
    if os.path.exists(raw_vtt):
        if raw_vtt != orig_vtt:
            shutil.move(raw_vtt, orig_vtt)
        original_sub = orig_vtt
        ext = ".vtt"
    elif os.path.exists(raw_srt):
        if raw_srt != orig_srt:
            shutil.move(raw_srt, orig_srt)
        original_sub = orig_srt
        ext = ".srt"
    else:
        original_sub = orig_vtt
        ext = ".vtt"

    # Clean duplicate Whisper hallucination loops
    if os.path.exists(original_sub):
        from core.tts_engine import clean_subtitle_file
        clean_subtitle_file(original_sub)

    # Setup translated/ subfolder and template file
    translated_dir = os.path.join(project_dir, "translated")
    os.makedirs(translated_dir, exist_ok=True)
    translated_sub = os.path.join(translated_dir, f"audio{ext}")

    # Copy template if translated file doesn't exist yet
    if os.path.exists(original_sub) and not os.path.exists(translated_sub):
        shutil.copy(original_sub, translated_sub)
        print(f"📄 Created translated template in folder: {translated_sub}")

    return original_sub, translated_sub