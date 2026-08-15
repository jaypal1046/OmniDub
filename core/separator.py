import os
import shutil
import subprocess

def separate_bgm(audio_path, project_dir):
    """
    Isolates background music (BGM/SFX) using Demucs AI and moves output into project_dir.
    Returns path to isolated BGM audio file.
    """
    print(f"\n[3/5] Separating Dialogue & Background Music using Demucs AI...")
    temp_sep_dir = os.path.join(project_dir, "sep_temp")
    
    subprocess.run([
        "demucs", "--two-stems", "vocals",
        audio_path, "-o", temp_sep_dir, "--mp3"
    ], check=True)

    # Locate generated no_vocals.mp3 file
    bgm_target = os.path.join(project_dir, "bgm_music.mp3")
    
    for root, dirs, files in os.walk(temp_sep_dir):
        if "no_vocals.mp3" in files:
            src_path = os.path.join(root, "no_vocals.mp3")
            shutil.move(src_path, bgm_target)
            break

    # Clean up temporary demucs folder
    if os.path.exists(temp_sep_dir):
        shutil.rmtree(temp_sep_dir, ignore_errors=True)

    if os.path.exists(bgm_target):
        print(f"Isolated Background Music Saved to: {bgm_target}")
        return bgm_target
    else:
        print("Warning: Background music file not found.")
        return None
