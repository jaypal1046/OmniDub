#!/usr/bin/env python3
"""
=============================================================================
             AI RECAP VIDEO GENERATOR - SOFTWARE ENGINE (v1.5)
=============================================================================
Modular, commercial-grade software engine with full State Management, Caching, 
and Multi-File Subtitle Support in Translated/ subfolder.

Structure per Project:
  output/<project_name>/
    ├── video.mp4               (Original MP4 video)
    ├── audio.mp3               (Original audio track)
    ├── audio.vtt               (Original transcribed subtitles from Whisper)
    ├── bgm_music.mp3           (Isolated background music/SFX)
    ├── synced_voiceover.mp3    (Generated frame-synced voiceover)
    ├── FINAL_RECAP.mp4         (Final redubbed video)
    └── Translated/             📁 Dedicated folder for translated subtitles
        ├── 1_audio_txt.vtt     📝 Chunked subtitle files (1, 2, 3...) for fast parallel translation
        ├── 2_audio_txt.vtt
        └── ...
"""

import os
import sys
import argparse
from core.state_manager import StateManager, extract_video_id
from core.downloader import download_media
from core.transcriber import transcribe_media
from core.separator import separate_bgm
from core.tts_engine import generate_voiceover
from core.video_merger import merge_project_video

def get_translated_subtitle_path(project_dir):
    """
    Checks for Translated/ or translated/ subfolders containing .vtt or .srt files.
    Returns directory path if multiple files exist, or single file path, or None.
    """
    possible_dirs = [
        os.path.join(project_dir, "Translated"),
        os.path.join(project_dir, "translated")
    ]
    for t_dir in possible_dirs:
        if os.path.exists(t_dir) and os.path.isdir(t_dir):
            files = [f for f in os.listdir(t_dir) if f.endswith(".vtt") or f.endswith(".srt")]
            if files:
                return t_dir
    return None

def process_recap_project(source_input, project_name=None, voice="en-US-GuyNeural", 
                          source_lang="Chinese", bgm_volume=0.4, workers=10, 
                          burn_subtitles=False, force=False, pause_after_transcribe=True,
                          auto_continue=False, model="medium", device=None, mode=1,
                          compute_type=None, vad_filter=True, batched=True, threads=None):
    """
    State-managed master controller for the AI Recap pipeline with GPU acceleration & 4 output merge modes.
    """
    # 1. Resolve project name & directory
    if not project_name or project_name == "my_recap_project":
        project_name = extract_video_id(source_input)

    project_dir = os.path.join("output", project_name)
    os.makedirs(project_dir, exist_ok=True)

    # 2. Initialize State Manager
    state_mgr = StateManager(project_dir, source=source_input, force=force)

    print("=========================================================================")
    print(f"       AI RECAP PROJECT: {project_name}")
    print(f"       Project Path: {os.path.abspath(project_dir)}")
    print("=========================================================================")

    video_path = os.path.join(project_dir, "video.mp4")
    audio_path = os.path.join(project_dir, "audio.mp3")
    bgm_path = os.path.join(project_dir, "bgm_music.mp3")
    voiceover_path = os.path.join(project_dir, "synced_voiceover.mp3")
    final_video_path = os.path.join(project_dir, "FINAL_RECAP.mp4")

    orig_sub_path = os.path.join(project_dir, "audio.vtt")

    # Step 1: Download Video & Extract Audio
    if state_mgr.is_step_completed("download", [video_path, audio_path]):
        print(f"\n⏩ [1/5] Step 'download' already COMPLETED (cached). Skipping.")
    else:
        video_path, audio_path = download_media(source_input, project_dir)
        state_mgr.mark_step_completed("download", [video_path, audio_path])

    # Step 2: Transcribe Audio to Subtitles with Timestamps
    transcribe_just_completed = False
    if state_mgr.is_step_completed("transcribe", [orig_sub_path]):
        print(f"\n⏩ [2/5] Step 'transcribe' already COMPLETED (cached). Skipping.")
    else:
        orig_sub_path, _ = transcribe_media(
            audio_path, project_dir, source_lang=source_lang, model=model, device=device,
            compute_type=compute_type, vad_filter=vad_filter, batched=batched, threads=threads
        )
        state_mgr.mark_step_completed("transcribe", [orig_sub_path])
        transcribe_just_completed = True

    # Step 3: AI Audio Separation (Isolate Background Music)
    if state_mgr.is_step_completed("separate_bgm", [bgm_path]):
        print(f"\n⏩ [3/5] Step 'separate_bgm' already COMPLETED (cached). Skipping.")
    else:
        bgm_path = separate_bgm(audio_path, project_dir, device=device)
        state_mgr.mark_step_completed("separate_bgm", [bgm_path])

    # PAUSE FOR SUBTITLE TRANSLATION CHECK
    translated_sub_input = get_translated_subtitle_path(project_dir)
    if transcribe_just_completed and pause_after_transcribe and not auto_continue:
        state_mgr.set_project_status("AWAITING_TRANSLATION")
        print("\n=========================================================================")
        print("⏸️ PIPELINE PAUSED FOR SUBTITLE TRANSLATION")
        print("=========================================================================")
        print(f"Steps 1, 2, and 3 (Download, Transcription, and BGM Separation) are COMPLETE!\n")
        print(f"📄 Original Subtitles: {os.path.abspath(orig_sub_path)}")
        print(f"📁 Translated Folder:  {os.path.abspath(os.path.join(project_dir, 'Translated'))}")
        print("\n📝 NEXT STEPS:")
        print("1. Add or edit your translated subtitle files inside 'Translated/' (e.g. 1_audio_txt.vtt, 2_audio_txt.vtt...).")
        print("2. Save the files.")
        print(f"3. Re-run this command to generate your voiceover & final video:")
        print(f"   python app.py \"{source_input}\" -name {project_name} --auto-continue")
        print("=========================================================================\n")
        return translated_sub_input or orig_sub_path

    # Step 4: Time-Synced TTS Voiceover Generation
    active_sub_path = translated_sub_input if translated_sub_input else orig_sub_path
    print(f"\n[4/5] Using subtitle source for narration: {active_sub_path}")

    if state_mgr.is_step_completed("voiceover", [voiceover_path]):
        print(f"⏩ Step 'voiceover' already COMPLETED (cached). Skipping.")
    else:
        voiceover_path = generate_voiceover(active_sub_path, project_dir, voice=voice, workers=workers)
        state_mgr.mark_step_completed("voiceover", [voiceover_path])

    # Step 5: Final Video Assembly
    if state_mgr.is_step_completed("merge_video", [final_video_path]):
        print(f"\n⏩ [5/5] Step 'merge_video' already COMPLETED (cached). Skipping.")
    else:
        final_video_path = merge_project_video(
            video_path, voiceover_path, bgm_path, project_dir,
            sub_path=active_sub_path, bgm_volume=bgm_volume, burn_subtitles=burn_subtitles, mode=mode
        )
        state_mgr.mark_step_completed("merge_video", [final_video_path])
        state_mgr.set_project_status("COMPLETED")

    print(f"\n=========================================================================")
    print(f"🎉 PROJECT READY AT: {os.path.abspath(final_video_path)}")
    print(f"=========================================================================\n")

    return final_video_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="State-Managed AI Recap Video Generator Engine")
    parser.add_argument("source", help="YouTube URL or local input video path")
    parser.add_argument("-name", "--project-name", help="Project name (defaults to video ID/name under output/)")
    parser.add_argument("-v", "--voice", default="en-US-GuyNeural", help="Edge-TTS narrator voice name")
    parser.add_argument("-l", "--lang", default="Chinese", help="Source video language")
    parser.add_argument("-w", "--workers", type=int, default=10, help="Number of parallel TTS workers")
    parser.add_argument("-m", "--model", default="medium", help="Whisper model name (e.g. medium, large-v3-turbo, small)")
    parser.add_argument("-d", "--device", default=None, help="Device to use for AI inference ('cuda' or 'cpu')")
    parser.add_argument("--compute-type", default=None, help="Quantization type (e.g. int8, float16)")
    parser.add_argument("--no-vad", dest="vad_filter", action="store_false", help="Disable VAD silence filtering")
    parser.add_argument("--no-batched", dest="batched", action="store_false", help="Disable batched decoding")
    parser.add_argument("-t", "--threads", type=int, default=None, help="Number of threads for CPU inference")
    parser.add_argument("-mode", "--mode", type=int, choices=[1, 2, 3, 4], default=1,
                        help="Output mode: 1=Video+Audio (DEFAULT), 2=Video+Audio+BGM, 3=Video+Audio+Transcript, 4=Video+Audio+BGM+Transcript")
    parser.add_argument("--bgm-volume", type=float, default=0.4, help="BGM volume multiplier (0.0 to 1.0)")
    parser.add_argument("--burn-subtitles", action="store_true", help="Burn subtitles onto the final video (maps to Mode 3/4)")
    parser.add_argument("--force", action="store_true", help="Force re-run all steps without using cached state")
    parser.add_argument("--no-pause", dest="pause_after_transcribe", action="store_false", help="Do not pause for translation")
    parser.add_argument("--auto-continue", action="store_true", help="Automatically continue to voiceover generation")

    args = parser.parse_args()

    process_recap_project(
        source_input=args.source,
        project_name=args.project_name,
        voice=args.voice,
        source_lang=args.lang,
        bgm_volume=args.bgm_volume,
        workers=args.workers,
        burn_subtitles=args.burn_subtitles,
        force=args.force,
        pause_after_transcribe=args.pause_after_transcribe,
        auto_continue=args.auto_continue,
        model=args.model,
        device=args.device,
        mode=args.mode,
        compute_type=args.compute_type,
        vad_filter=args.vad_filter,
        batched=args.batched,
        threads=args.threads
    )
