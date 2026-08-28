import os
import re
import asyncio
import tempfile
import subprocess
import shutil
from pydub import AudioSegment
import edge_tts
from core.tts_engine import parse_subtitle_file

def ms_to_vtt_timestamp(ms):
    """Converts milliseconds to VTT timestamp string (HH:MM:SS.mmm)."""
    seconds, milliseconds = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

def get_media_duration_ms(file_path):
    """Gets total duration of audio/video file in milliseconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        dur_sec = float(res.stdout.strip())
        return int(dur_sec * 1000)
    except Exception:
        # Fallback to AudioSegment if ffprobe fails
        try:
            clip = AudioSegment.from_file(file_path)
            return len(clip)
        except Exception:
            return 0

def export_retimed_vtt(retimed_entries, output_vtt):
    """Writes retimed subtitle entries to a WebVTT file."""
    os.makedirs(os.path.dirname(os.path.abspath(output_vtt)), exist_ok=True)
    lines = ["WEBVTT\n"]
    for entry in retimed_entries:
        start_ts = ms_to_vtt_timestamp(entry["start_ms"])
        end_ts = ms_to_vtt_timestamp(entry["end_ms"])
        lines.append(f"\n{start_ts} --> {end_ts}\n{entry['text']}\n")

    with open(output_vtt, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return output_vtt

async def generate_natural_tts_clips_async(entries, tts_cache_dir, voice="en-US-AriaNeural", max_workers=10):
    """
    Synthesizes Edge-TTS audio clips at 100% natural, uncompressed speed with persistent disk caching.
    Skips synthesizing any clip that already exists in voice-specific tts_cache_dir.
    """
    safe_voice = re.sub(r"[^\w\-]", "_", voice)
    voice_cache_dir = os.path.join(tts_cache_dir, safe_voice)
    os.makedirs(voice_cache_dir, exist_ok=True)
    semaphore = asyncio.Semaphore(max_workers)
    total = len(entries)
    completed = 0
    cached_count = 0
    results = [None] * total

    async def synth(idx, entry):
        nonlocal completed, cached_count
        async with semaphore:
            text = entry["text"]
            raw_path = os.path.join(voice_cache_dir, f"nat_{idx}.mp3")

            if not (os.path.exists(raw_path) and os.path.getsize(raw_path) > 0):
                for attempt in range(4):
                    try:
                        comm = edge_tts.Communicate(text, voice)
                        await comm.save(raw_path)
                        if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
                            break
                    except Exception:
                        await asyncio.sleep(0.5 * (attempt + 1))
            else:
                cached_count += 1

            completed += 1
            if completed % 50 == 0 or completed == total or completed == 1:
                percent = (completed / total) * 100
                print(f"🎙️ Natural TTS Progress ({voice}): [{completed}/{total}] ({percent:.1f}%) [Cached: {cached_count}]...", flush=True)

            if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
                clip = await asyncio.to_thread(AudioSegment.from_file, raw_path)
                dur = len(clip)
            else:
                dur = entry["duration_ms"]
                clip = None

            results[idx] = {
                "entry": entry,
                "clip_path": raw_path,
                "clip": clip,
                "actual_duration_ms": dur
            }

    tasks = [synth(i, e) for i, e in enumerate(entries)]
    await asyncio.gather(*tasks)
    return results

def process_audio_driven_retiming(video_path, sub_path, project_dir, voice="en-US-AriaNeural", 
                                 bgm_path=None, bgm_volume=0.4, burn_subtitles=True, mode=3, max_workers=10, state_mgr=None):
    """
    Audio-Driven Video Retiming Controller:
    1. Synthesizes Edge-TTS at 100% natural speed with persistent disk caching.
    2. Calculates retimed timeline for video segments and subtitles.
    3. Assembles retimed video clips using FFmpeg (slow-mo + freeze-frame).
    4. Merges retimed video + natural voiceover + retimed burned subtitles into FINAL_RECAP.mp4.
    """
    print(f"\n=========================================================================")
    print(f"🎬 STARTING AUDIO-DRIVEN VIDEO RETIMING PIPELINE")
    print(f"   Original Video: {os.path.basename(video_path)}")
    print(f"   Voice: {voice} | Output Mode: {mode}")
    print(f"=========================================================================\n")

    entries = parse_subtitle_file(sub_path)
    if not entries:
        raise ValueError("No subtitle entries found for retiming process.")

    total_video_ms = get_media_duration_ms(video_path)
    print(f"📹 Original Video Duration: {total_video_ms / 1000.0:.2f}s | Subtitle Cues: {len(entries)}")

    tts_cache_dir = os.path.join(project_dir, "tts_cache")

    with tempfile.TemporaryDirectory() as temp_dir:
        # Step 1: Generate natural TTS clips with persistent caching
        print(f"\n[1/4] Generating natural, uncompressed TTS audio clips for voice '{voice}'...")
        synth_results = asyncio.run(generate_natural_tts_clips_async(entries, tts_cache_dir, voice=voice, max_workers=max_workers))
        if state_mgr:
            state_mgr.mark_step_completed("tts_clips", [tts_cache_dir], params={"voice": voice})

        # Step 2: Build Seamless Retimed Timeline Mapping
        print("\n[2/4] Computing seamless retimed video timeline & subtitle mapping...")
        retimed_entries = []
        # Ensure synth_results are chronologically ordered by start_ms
        synth_results = sorted(synth_results, key=lambda x: x["entry"]["start_ms"])

        video_segments = []
        curr_orig_ms = 0
        curr_new_ms = 0

        for item in synth_results:
            entry = item["entry"]
            start_ms = max(entry["start_ms"], curr_orig_ms)
            end_ms = max(entry["end_ms"], start_ms + 100)
            orig_dur_ms = max(end_ms - start_ms, 100)
            actual_audio_ms = item["actual_duration_ms"]

            # If there is a silence gap before this cue, check if we need it or can absorb/trim it
            if start_ms > curr_orig_ms:
                gap_dur_ms = start_ms - curr_orig_ms
                if gap_dur_ms > 0:
                    video_segments.append({
                        "type": "gap",
                        "orig_start_ms": curr_orig_ms,
                        "orig_end_ms": start_ms,
                        "target_dur_ms": gap_dur_ms,
                        "ratio": 1.0
                    })
                    curr_new_ms += gap_dur_ms
                curr_orig_ms = start_ms

            # Match cue video segment duration EXACTLY to natural audio duration
            cue_target_dur_ms = max(actual_audio_ms, 200)
            ratio = cue_target_dur_ms / orig_dur_ms

            retimed_entries.append({
                "start_ms": curr_new_ms,
                "end_ms": curr_new_ms + cue_target_dur_ms,
                "text": entry["text"]
            })

            video_segments.append({
                "type": "cue",
                "index": entry["index"],
                "orig_start_ms": start_ms,
                "orig_end_ms": end_ms,
                "orig_dur_ms": orig_dur_ms,
                "target_dur_ms": cue_target_dur_ms,
                "ratio": ratio,
                "actual_audio_ms": actual_audio_ms
            })

            item["new_start_ms"] = curr_new_ms
            curr_new_ms += cue_target_dur_ms
            curr_orig_ms = end_ms

        # Final gap after last cue
        if total_video_ms > curr_orig_ms:
            final_gap_ms = total_video_ms - curr_orig_ms
            if final_gap_ms > 0:
                video_segments.append({
                    "type": "gap",
                    "orig_start_ms": curr_orig_ms,
                    "orig_end_ms": total_video_ms,
                    "target_dur_ms": final_gap_ms,
                    "ratio": 1.0
                })
                curr_new_ms += final_gap_ms

        retimed_total_duration_s = curr_new_ms / 1000.0
        print(f"⏱️ Retimed Total Video Duration: {retimed_total_duration_s:.2f}s (adjusted by +{(curr_new_ms - total_video_ms)/1000.0:.2f}s for seamless speech)")

        # Save retimed master audio & retimed VTT
        voiceover_path = os.path.join(project_dir, "retimed_voiceover.mp3")
        retimed_vtt_path = os.path.join(project_dir, "master_retimed.vtt")

        print("\n[3/4] Exporting retimed audio track & subtitle file...")
        export_retimed_vtt(retimed_entries, retimed_vtt_path)

        total_clips = len(synth_results)
        print(f"🎵 Stitching {total_clips} audio clips into master voiceover timeline ({retimed_total_duration_s/60.0:.1f} mins total)...", flush=True)

        master_audio = AudioSegment.silent(duration=curr_new_ms + 1000)
        for i, item in enumerate(synth_results, 1):
            if item["clip"] is not None and len(item["clip"]) > 0:
                master_audio = master_audio.overlay(item["clip"], position=item["new_start_ms"])
            if i % 100 == 0 or i == total_clips:
                percent = (i / total_clips) * 100
                print(f"🎵 Master Audio Assembly: [{i}/{total_clips}] clips overlaid ({percent:.1f}%)...", flush=True)

        print(f"💾 Exporting master voiceover file ({voiceover_path})...", flush=True)
        master_audio.export(voiceover_path, format="mp3")
        if state_mgr:
            state_mgr.mark_step_completed("retimed_voiceover", [voiceover_path, retimed_vtt_path])

        # Step 3: Render Retimed Video Clips & Concat (Optimized Parallel Execution - Smooth Motion Only)
        print("\n[4/4] Rendering retimed video clips in parallel & assembling final video...")
        seg_dir = os.path.join(temp_dir, "segments")
        os.makedirs(seg_dir, exist_ok=True)
        concat_file = os.path.join(temp_dir, "concat_list.txt")

        # Combine adjacent unstretched segments (ratio == 1.0) to reduce total segment count
        merged_segments = []
        for seg in video_segments:
            if seg["orig_end_ms"] <= seg["orig_start_ms"]:
                continue

            if merged_segments and abs(merged_segments[-1]["ratio"] - 1.0) <= 0.01 and abs(seg["ratio"] - 1.0) <= 0.01:
                merged_segments[-1]["orig_end_ms"] = max(merged_segments[-1]["orig_end_ms"], seg["orig_end_ms"])
                merged_segments[-1]["target_dur_ms"] += seg["target_dur_ms"]
                merged_segments[-1]["orig_dur_ms"] = merged_segments[-1]["orig_end_ms"] - merged_segments[-1]["orig_start_ms"]
                merged_segments[-1]["ratio"] = 1.0
            else:
                merged_segments.append(dict(seg))

        print(f"🧩 Optimized timeline into {len(merged_segments)} video rendering chunks (from {len(video_segments)} original segments).")

        concat_lines = [None] * len(merged_segments)

        def render_segment(idx, seg):
            seg_out = os.path.join(seg_dir, f"seg_{idx:04d}.mp4")
            start_s = seg["orig_start_ms"] / 1000.0
            end_s = seg["orig_end_ms"] / 1000.0

            if end_s <= start_s + 0.01:
                end_s = start_s + 0.1

            ratio = seg["ratio"]

            # Pure continuous motion setpts filter (NO static tpad frame freezing!)
            if abs(ratio - 1.0) <= 0.01:
                vf_str = "null"
            else:
                vf_str = f"setpts={ratio:.6f}*PTS"

            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{start_s:.4f}",
                "-to", f"{end_s:.4f}",
                "-i", video_path,
                "-vf", vf_str,
                "-an",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
                "-avoid_negative_ts", "make_zero",
                "-threads", "1",
                seg_out
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return idx, f"file '{seg_out.replace('\\', '/')}'\n"

        from concurrent.futures import ThreadPoolExecutor, as_completed
        num_threads = min(8, os.cpu_count() or 4)
        print(f"🚀 Rendering video segments using {num_threads} parallel CPU workers...")

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(render_segment, i, s) for i, s in enumerate(merged_segments)]
            rendered_count = 0
            for future in as_completed(futures):
                idx, line_str = future.result()
                concat_lines[idx] = line_str
                rendered_count += 1
                if rendered_count % 50 == 0 or rendered_count == len(merged_segments):
                    print(f"🎥 Rendered [{rendered_count}/{len(merged_segments)}] video chunks ({(rendered_count/len(merged_segments))*100:.1f}%)...")

        with open(concat_file, "w", encoding="utf-8") as f:
            f.writelines(concat_lines)

        # Merge segments into raw retimed video
        raw_retimed_video = os.path.join(temp_dir, "raw_retimed_video.mp4")
        cmd_concat = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            raw_retimed_video
        ]
        subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # Final Assembly with Audio & Burned Subtitles
        final_output = os.path.join(project_dir, "FINAL_RECAP.mp4")
        clean_sub_path = retimed_vtt_path.replace("\\", "/").replace(":", "\\:")

        include_subs = burn_subtitles or (mode in [3, 4])
        use_bgm = (mode in [2, 4]) and bgm_path and os.path.exists(bgm_path)

        cmd_final = ["ffmpeg", "-y", "-i", raw_retimed_video, "-i", voiceover_path]
        if use_bgm:
            cmd_final.extend(["-i", bgm_path])

        filter_complex = []
        if include_subs:
            vf = f"subtitles='{clean_sub_path}':force_style='FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3'"
            cmd_final.extend(["-vf", vf])

        if use_bgm:
            filter_complex.append(f"[1:a]volume=1.0[v];[2:a]volume={bgm_volume}[b];[v][b]amix=inputs=2:duration=first[aout]")
            cmd_final.extend(["-filter_complex", "".join(filter_complex), "-map", "0:v", "-map", "[aout]"])
        else:
            cmd_final.extend(["-map", "0:v", "-map", "1:a"])

        cmd_final.extend([
            "-c:v", "libx264", "-preset", "fast", "-crf", "24",
            "-c:a", "aac", "-b:a", "192k",
            final_output
        ])

        subprocess.run(cmd_final, check=True)

        print(f"\n=========================================================================")
        print(f"🎉 RETIMED RECAP VIDEO READY AT: {final_output}")
        print(f"=========================================================================\n")
        return final_output
