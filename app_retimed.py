#!/usr/bin/env python3
"""
=============================================================================
         AI RECAP VIDEO GENERATOR - AUDIO-DRIVEN RETIMED ENGINE (v1.5)
=============================================================================
Command 2: Natural Speech & Audio-Driven Video Retiming Engine.

Synthesizes Edge-TTS audio at 100% natural, uncompressed speaking speed.
Dynamically retimes (stretches/pauses) video clips & recalculates subtitle
timestamps so the story flows comfortably without rushed narration.
"""

import os
import sys
import argparse
from core.state_manager import StateManager, extract_video_id
from core.downloader import download_media
from core.transcriber import transcribe_media
from core.separator import separate_bgm
from core.video_retimer import process_audio_driven_retiming
from app import get_translated_subtitle_path

def process_retimed_recap_project(source_input, project_name=None, voice="en-US-GuyNeural", 
                                 source_lang="Chinese", bgm_volume=0.4, workers=10, 
                                 burn_subtitles=False, force=False, pause_after_transcribe=True,
                                 auto_continue=False, model="medium", device=None, mode=1,
                                 compute_type=None, vad_filter=True, batched=True, threads=None):
    """
    Audio-driven retimed recap controller.
    """
    if not project_name or project_name == "my_recap_project":
        project_name = extract_video_id(source_input)

    project_dir = os.path.join("output", project_name)
    os.makedirs(project_dir, exist_ok=True)

    state_mgr = StateManager(project_dir, source=source_input, force=force)

    print("=========================================================================")
    print(f"       AI RECAP PROJECT (AUDIO-DRIVEN RETIMED): {project_name}")
    print(f"       Project Path: {os.path.abspath(project_dir)}")
    print("=========================================================================")

    video_path = os.path.join(project_dir, "video.mp4")
    audio_path = os.path.join(project_dir, "audio.mp3")
    bgm_path = os.path.join(project_dir, "bgm_music.mp3")
    final_video_path = os.path.join(project_dir, "FINAL_RECAP.mp4")
    orig_sub_path = os.path.join(project_dir, "audio.vtt")

    # Step 1: Download Video & Extract Audio
    if state_mgr.is_step_completed("download", [video_path, audio_path]):
        print(f"\n⏩ [1/4] Step 'download' already COMPLETED (cached). Skipping.")
    else:
        video_path, audio_path = download_media(source_input, project_dir)
        state_mgr.mark_step_completed("download", [video_path, audio_path])

    # Step 2: Transcribe Audio to Subtitles with Timestamps
    transcribe_just_completed = False
    if state_mgr.is_step_completed("transcribe", [orig_sub_path]):
        print(f"\n⏩ [2/4] Step 'transcribe' already COMPLETED (cached). Skipping.")
    else:
        orig_sub_path, _ = transcribe_media(
            audio_path, project_dir, source_lang=source_lang, model=model, device=device,
            compute_type=compute_type, vad_filter=vad_filter, batched=batched, threads=threads
        )
        state_mgr.mark_step_completed("transcribe", [orig_sub_path])
        transcribe_just_completed = True

    # Step 3: AI Audio Separation (if BGM needed)
    if mode in [1, 3]:
        print(f"\n⏩ [3/4] Mode {mode} does not require Background Music. Skipping AI Audio Separation.")
        bgm_path = None
        if not state_mgr.is_step_completed("separate_bgm"):
            state_mgr.mark_step_completed("separate_bgm", [])
    elif state_mgr.is_step_completed("separate_bgm", [bgm_path]):
        print(f"\n⏩ [3/4] Step 'separate_bgm' already COMPLETED (cached). Skipping.")
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
        print(f"Steps 1, 2, and 3 are COMPLETE!\n")
        print(f"📄 Original Subtitles: {os.path.abspath(orig_sub_path)}")
        print(f"📁 Translated Folder:  {os.path.abspath(os.path.join(project_dir, 'Translated'))}")
        print("\n📝 NEXT STEPS:")
        print("1. Add or edit your translated subtitle files inside 'Translated/'.")
        print("2. Save the files.")
        print(f"3. Re-run this command to generate your retimed voiceover & video:")
        print(f"   python app_retimed.py \"{source_input}\" -name {project_name} --auto-continue")
        print("=========================================================================\n")
        return translated_sub_input or orig_sub_path

    # Step 4: Audio-Driven Video Retiming & Synthesis
    active_sub_path = translated_sub_input if translated_sub_input else orig_sub_path
    print(f"\n[4/4] Generating natural speech narration & retiming video: {active_sub_path}")

    current_merge_params = {"voice": voice, "mode": mode, "burn_subtitles": burn_subtitles, "active_sub_path": active_sub_path}
    if state_mgr.is_step_completed("merge_video", [final_video_path], current_params=current_merge_params):
        print(f"\n⏩ [4/4] Step 'merge_video' already COMPLETED (cached for voice '{voice}'). Skipping.")
    else:
        state_mgr.set_project_status("PROCESSING_RETIMED_RECAP")
        final_video_path = process_audio_driven_retiming(
            video_path=video_path,
            sub_path=active_sub_path,
            project_dir=project_dir,
            voice=voice,
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
            burn_subtitles=burn_subtitles,
            mode=mode,
            max_workers=workers,
            state_mgr=state_mgr
        )
        state_mgr.mark_step_completed("merge_video", [final_video_path], params=current_merge_params)
        state_mgr.set_project_status("COMPLETED")

    print(f"\n=========================================================================")
    print(f"🎉 RETIMED RECAP PROJECT READY AT: {os.path.abspath(final_video_path)}")
    print(f"=========================================================================\n")

    return final_video_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audio-Driven Retimed AI Recap Video Generator Engine")
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

    process_retimed_recap_project(
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
