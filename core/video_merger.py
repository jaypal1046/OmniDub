import os
import time
import subprocess
from core.tts_engine import export_combined_vtt

def merge_project_video(video_path, voiceover_path, bgm_path, project_dir, sub_path=None, bgm_volume=0.4, burn_subtitles=False, mode=1):
    """
    Merges video and voiceover into project_dir/FINAL_RECAP.mp4 using one of 4 output modes:
      Mode 1 (DEFAULT): Video + Audio (Muted original video + TTS synced voiceover, fast stream copy ~5s)
      Mode 2: Video + Audio + BGM (Muted original video + TTS voiceover + isolated BGM, fast stream copy ~5s)
      Mode 3: Video + Audio + Transcript (Muted original video + TTS voiceover + burned subtitles)
      Mode 4: Video + Audio + BGM + Transcript (Muted original video + TTS voiceover + isolated BGM + burned subtitles)
    """
    print(f"\n[5/5] Assembling Final Redubbed Video (Output Mode {mode})...")
    final_output = os.path.join(project_dir, "FINAL_RECAP.mp4")

    # Map legacy flags if mode wasn't explicitly passed
    if mode == 1:
        if burn_subtitles and (bgm_path and os.path.exists(bgm_path)):
            mode = 4
        elif burn_subtitles:
            mode = 3

    actual_sub_file = None
    include_subtitles = (mode in [3, 4])
    if include_subtitles and sub_path and os.path.exists(sub_path):
        if os.path.isdir(sub_path):
            combined_vtt = os.path.join(project_dir, "master_translated.vtt")
            print(f"Combining multiple subtitle files in {sub_path} into master VTT...")
            export_combined_vtt(sub_path, combined_vtt)
            actual_sub_file = combined_vtt
        else:
            actual_sub_file = sub_path

    if mode == 1:
        print("🎬 [Mode 1 DEFAULT] Merging Muted Video + TTS Voiceover Audio (Fast Stream Copy ~5s)...")
        cmd = [
            "ffmpeg", "-y",
            "-fflags", "+genpts+discardcorrupt",
            "-i", video_path,
            "-i", voiceover_path,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            final_output
        ]
    elif mode == 2:
        print("🎬 [Mode 2] Merging Muted Video + TTS Voiceover + Isolated BGM Music...")
        filter_complex = f"[1:a]volume=1.0[voice];[2:a]volume={bgm_volume}[bgm];[voice][bgm]amix=inputs=2:duration=first[aout]"
        cmd = [
            "ffmpeg", "-y",
            "-fflags", "+genpts+discardcorrupt",
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
    elif mode == 3:
        print("🎬 [Mode 3] Merging Video + TTS Voiceover + Burned Subtitles/Transcript...")
        clean_sub_path = actual_sub_file.replace("\\", "/").replace(":", "\\:") if actual_sub_file else ""
        vf_filter = f"subtitles='{clean_sub_path}':force_style='FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3'"
        cmd = [
            "ffmpeg", "-y",
            "-fflags", "+genpts+discardcorrupt",
            "-i", video_path,
            "-i", voiceover_path,
            "-vf", vf_filter,
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            final_output
        ]
    elif mode == 4:
        print("🎬 [Mode 4] Merging Video + TTS Voiceover + Isolated BGM + Burned Subtitles/Transcript...")
        clean_sub_path = actual_sub_file.replace("\\", "/").replace(":", "\\:") if actual_sub_file else ""
        vf_filter = f"subtitles='{clean_sub_path}':force_style='FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3'"
        filter_complex = f"[1:a]volume=1.0[voice];[2:a]volume={bgm_volume}[bgm];[voice][bgm]amix=inputs=2:duration=first[aout]"
        cmd = [
            "ffmpeg", "-y",
            "-fflags", "+genpts+discardcorrupt",
            "-i", video_path,
            "-i", voiceover_path,
            "-i", bgm_path,
            "-vf", vf_filter,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            final_output
        ]
    else:
        raise ValueError(f"Invalid mode {mode}. Expected 1, 2, 3, or 4.")

    subprocess.run(cmd, check=True)

    print(f"\n=========================================================================")
    print(f"🎉 FINAL RECAP VIDEO READY AT: {final_output}")
    print(f"=========================================================================\n")
    return final_output
