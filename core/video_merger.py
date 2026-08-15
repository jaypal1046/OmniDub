import os
import time
import subprocess
from core.tts_engine import export_combined_vtt

def merge_project_video(video_path, voiceover_path, bgm_path, project_dir, sub_path=None, bgm_volume=0.4, burn_subtitles=False):
    """
    Merges video, voiceover, and BGM into project_dir/FINAL_RECAP.mp4
    Supports single subtitle files as well as directories with multiple chunked subtitle files.
    """
    print(f"\n[5/5] Assembling Final Redubbed Recap Video...")
    final_output = os.path.join(project_dir, "FINAL_RECAP.mp4")

    # Resolve master subtitle file if burning subtitles is enabled
    actual_sub_file = None
    if burn_subtitles and sub_path and os.path.exists(sub_path):
        if os.path.isdir(sub_path):
            combined_vtt = os.path.join(project_dir, "master_translated.vtt")
            print(f"Combining multiple subtitle files in {sub_path} into master VTT...")
            export_combined_vtt(sub_path, combined_vtt)
            actual_sub_file = combined_vtt
        else:
            actual_sub_file = sub_path

    if actual_sub_file and os.path.exists(actual_sub_file):
        print(f"Burning Subtitles ({os.path.basename(actual_sub_file)}) onto Video...")
        clean_sub_path = actual_sub_file.replace("\\", "/").replace(":", "\\:")
        vf_filter = f"subtitles='{clean_sub_path}':force_style='FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3'"

        if bgm_path and os.path.exists(bgm_path):
            filter_complex = f"[1:a]volume=1.0[voice];[2:a]volume={bgm_volume}[bgm];[voice][bgm]amix=inputs=2:duration=first[aout]"
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", voiceover_path,
                "-i", bgm_path,
                "-vf", vf_filter,
                "-filter_complex", filter_complex,
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "aac", "-b:a", "192k",
                final_output
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", voiceover_path,
                "-vf", vf_filter,
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "aac", "-b:a", "192k",
                final_output
            ]
    else:
        # Fast copy merge without video re-encoding
        if bgm_path and os.path.exists(bgm_path):
            filter_complex = f"[1:a]volume=1.0[voice];[2:a]volume={bgm_volume}[bgm];[voice][bgm]amix=inputs=2:duration=first[aout]"
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", voiceover_path,
                "-i", bgm_path,
                "-filter_complex", filter_complex,
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                final_output
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", voiceover_path,
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                final_output
            ]

    subprocess.run(cmd, check=True)

    print(f"\n=========================================================================")
    print(f"🎉 FINAL RECAP VIDEO READY AT: {final_output}")
    print(f"=========================================================================\n")
    return final_output
