import os
import shutil
import subprocess

def transcribe_media(audio_path, project_dir, source_lang="Chinese", model="medium", **kwargs):
    """
    Transcribes audio using faster-whisper into project_dir.
    Creates original transcript (project_dir/audio.vtt) and template inside
    translated/ subfolder (project_dir/translated/audio.vtt).
    Returns (original_sub_path, translated_sub_path).
    """
    print(f"\n[2/5] Transcribing Audio ({source_lang}) to Subtitles...")
    subprocess.run([
        "whisper-ctranslate2", audio_path,
        "--output_dir", project_dir,
        "--language", source_lang,
        "--model", model
    ], check=True)

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

    # Setup translated/ subfolder and template file
    translated_dir = os.path.join(project_dir, "translated")
    os.makedirs(translated_dir, exist_ok=True)
    translated_sub = os.path.join(translated_dir, f"audio{ext}")

    # Copy template if translated file doesn't exist yet
    if os.path.exists(original_sub) and not os.path.exists(translated_sub):
        shutil.copy(original_sub, translated_sub)
        print(f"📄 Created translated template in folder: {translated_sub}")

    return original_sub, translated_sub