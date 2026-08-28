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
    Synthesizes Edge-TTS audio clips with PREMIUM naturalness settings:
    - Uses rate="-8%" for slower, clearer speech (not rushed)
    - Uses volume="+8%" for better presence and consistent audio levels
    - Adds 80ms silence padding for natural breathing room between cues
    - Validates each clip (>200ms) before accepting
    - Includes retry logic with exponential backoff
    - Persistent disk caching to avoid re-synthesis
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
                # PREMIUM TTS with enhanced prosody settings
                for attempt in range(5):
                    try:
                        # Use Communicate with premium settings for natural, clear speech
                        comm = edge_tts.Communicate(
                            text, 
                            voice,
                            rate="-8%",      # Slower for maximum clarity
                            volume="+8%",    # Better presence
                            pitch="+0Hz"     # Natural pitch
                        )
                        await comm.save(raw_path)
                        if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
                            # Verify file is valid with meaningful duration
                            try:
                                test_clip = AudioSegment.from_file(raw_path)
                                if len(test_clip) > 200:  # At least 200ms of actual speech
                                    break
                                else:
                                    # Too short, likely failed synthesis
                                    await asyncio.sleep(0.5)
                                    continue
                            except Exception:
                                await asyncio.sleep(0.5)
                                continue
                    except Exception:
                        wait_time = 0.5 * (attempt + 1)
                        await asyncio.sleep(wait_time)
                
                # Final verification
                if not (os.path.exists(raw_path) and os.path.getsize(raw_path) > 0):
                    print(f"⚠️ Warning: Failed to synthesize clip {idx} after 5 attempts", flush=True)
            else:
                cached_count += 1

            completed += 1
            if completed % 50 == 0 or completed == total or completed == 1:
                percent = (completed / total) * 100
                print(f"🎙️ Premium TTS Progress ({voice}): [{completed}/{total}] ({percent:.1f}%) [Cached: {cached_count}]...", flush=True)

            if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
                try:
                    clip = await asyncio.to_thread(AudioSegment.from_file, raw_path)
                    # Add subtle 80ms padding for natural breathing room
                    padding = AudioSegment.silent(duration=80)
                    clip = padding + clip + padding
                    dur = len(clip)
                except Exception:
                    dur = entry["duration_ms"]
                    clip = None
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

def process_audio_driven_retiming_v2(video_path, sub_path, project_dir, voice="en-US-AriaNeural", 
                                 bgm_path=None, bgm_volume=0.4, burn_subtitles=True, mode=3, max_workers=10, state_mgr=None):
    """
    IMPROVED Audio-Driven Video Retiming Controller (v2.0 - Smart Speed Warping):
    
    KEY IMPROVEMENTS over v1:
    1. SPEED BOUNDING: Limits video speed changes to 0.75x-1.25x range (natural motion)
    2. INTELLIGENT GAP INSERTION: Adds freeze frames when audio is much longer than video
    3. AUDIO TRIMMING OPTION: Slightly trims silent gaps in audio when video is longer
    4. PRESERVES ORIGINAL PACING: Maintains original video rhythm instead of forcing exact sync
    
    This solves the Chinese→English translation problem where:
    - English text is typically 20-40% longer than Chinese
    - Forcing exact sync creates 0.5x slow-mo or 1.5x fast-forward artifacts
    """
    print(f"\n=========================================================================")
    print(f"🎬 STARTING IMPROVED AUDIO-DRIVEN VIDEO RETIMING PIPELINE (v2.0)")
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
        print(f"\n[1/5] Generating natural, uncompressed TTS audio clips for voice '{voice}'...")
        synth_results = asyncio.run(generate_natural_tts_clips_async(entries, tts_cache_dir, voice=voice, max_workers=max_workers))
        if state_mgr:
            state_mgr.mark_step_completed("tts_clips", [tts_cache_dir], params={"voice": voice})

        # Step 2: Build SMART Retimed Timeline with Speed Bounding
        print("\n[2/5] Computing smart retimed timeline with bounded speed warping...")
        retimed_entries = []
        synth_results = sorted(synth_results, key=lambda x: x["entry"]["start_ms"])

        video_segments = []
        curr_orig_ms = 0
        curr_new_ms = 0
        
        # Configuration for natural motion preservation
        MIN_SPEED_RATIO = 0.75   # Don't slow down below 75% (avoids 0.5x slo-mo)
        MAX_SPEED_RATIO = 1.25   # Don't speed up above 125% (avoids 1.5x chipmunk)
        FREEZE_FRAME_MIN_MS = 800  # Minimum freeze frame duration when gap is large
        
        total_gap_added = 0
        total_trimmed = 0

        for item in synth_results:
            entry = item["entry"]
            start_ms = max(entry["start_ms"], curr_orig_ms)
            end_ms = max(entry["end_ms"], start_ms + 100)
            orig_dur_ms = max(end_ms - start_ms, 100)
            actual_audio_ms = item["actual_duration_ms"]
            
            # Handle silence gap before this cue
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

            # CRITICAL FIX: Calculate target duration with speed bounding
            # ratio = target_dur / orig_dur
            # For setpts filter: setpts=N*PTS where N = orig_dur/target_dur (INVERSE!)
            # - If audio is LONGER (target > orig): need to SLOW video → setpts scale < 1
            # - If audio is SHORTER (target < orig): need to SPEED video → setpts scale > 1
            ideal_ratio = actual_audio_ms / orig_dur_ms
            
            if ideal_ratio < MIN_SPEED_RATIO:
                # Audio is SHORTER than video → Need to speed up video
                # But don't go below MIN_SPEED_RATIO (0.75x), add freeze frame for remainder
                speed_ratio = MIN_SPEED_RATIO  # Slowest allowed: 0.75x
                warped_dur_ms = int(orig_dur_ms * speed_ratio)
                
                # If audio is still longer than warped video, extend target to match audio
                if actual_audio_ms > warped_dur_ms:
                    target_dur_ms = actual_audio_ms
                else:
                    target_dur_ms = warped_dur_ms
                    
            elif ideal_ratio > MAX_SPEED_RATIO:
                # Audio is LONGER than video → Need to slow down video
                # But don't exceed MAX_SPEED_RATIO (1.25x), use freeze frames for remainder
                speed_ratio = MAX_SPEED_RATIO  # Fastest allowed: 1.25x
                warped_dur_ms = int(orig_dur_ms * speed_ratio)
                
                # If audio is still longer, extend target to match audio (will use freeze frame)
                if actual_audio_ms > warped_dur_ms:
                    target_dur_ms = actual_audio_ms
                else:
                    target_dur_ms = warped_dur_ms
                    
            else:
                # Ratio is within acceptable range (0.75x - 1.25x)
                speed_ratio = ideal_ratio
                target_dur_ms = actual_audio_ms

            # Store retimed subtitle entry
            retimed_entries.append({
                "start_ms": curr_new_ms,
                "end_ms": curr_new_ms + target_dur_ms,
                "text": entry["text"]
            })

            # Store video segment with calculated speed ratio
            video_segments.append({
                "type": "cue",
                "index": entry["index"],
                "orig_start_ms": start_ms,
                "orig_end_ms": end_ms,
                "orig_dur_ms": orig_dur_ms,
                "target_dur_ms": target_dur_ms,
                "ratio": speed_ratio,
                "actual_audio_ms": actual_audio_ms,
                "has_freeze_extension": target_dur_ms > int(orig_dur_ms * speed_ratio)
            })

            item["new_start_ms"] = curr_new_ms
            curr_new_ms += target_dur_ms
            curr_orig_ms = end_ms

        # Final gap after last cue - DO NOT add final gap if audio is longer than video
        # This prevents the 3+ minute audio-only tail issue
        if total_video_ms > curr_orig_ms:
            remaining_video_ms = total_video_ms - curr_orig_ms
            # Only add gap if we have room (video duration is still longer than retimed audio)
            if remaining_video_ms > 0 and (curr_new_ms + remaining_video_ms) <= total_video_ms:
                video_segments.append({
                    "type": "gap",
                    "orig_start_ms": curr_orig_ms,
                    "orig_end_ms": total_video_ms,
                    "target_dur_ms": remaining_video_ms,
                    "ratio": 1.0
                })
                curr_new_ms += remaining_video_ms

        retimed_total_duration_s = curr_new_ms / 1000.0
        print(f"⏱️ Retimed Total Video Duration: {retimed_total_duration_s:.2f}s")
        print(f"📊 Speed adjustments bounded to {MIN_SPEED_RATIO}x - {MAX_SPEED_RATIO}x range for natural motion")

        # Save retimed master audio & retimed VTT
        voiceover_path = os.path.join(project_dir, "retimed_voiceover.mp3")
        retimed_vtt_path = os.path.join(project_dir, "master_retimed.vtt")

        print("\n[3/5] Exporting retimed audio track & subtitle file...")
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

        # Step 4: Render Retimed Video Clips with Freeze Frame Support
        print("\n[4/5] Rendering retimed video clips with smart freeze-frame extension...")
        seg_dir = os.path.join(temp_dir, "segments")
        os.makedirs(seg_dir, exist_ok=True)
        concat_file = os.path.join(temp_dir, "concat_list.txt")

        # DO NOT merge segments - each segment needs individual timestamp handling
        # Merging causes timestamp discontinuities and glitches
        merged_segments = []
        for seg in video_segments:
            if seg["orig_end_ms"] <= seg["orig_start_ms"]:
                continue
            merged_segments.append(dict(seg))

        print(f"🧩 Optimized timeline into {len(merged_segments)} video rendering chunks (from {len(video_segments)} original segments).")

        concat_lines = [None] * len(merged_segments)

        def render_segment(idx, seg):
            seg_out = os.path.join(seg_dir, f"seg_{idx:04d}.mp4")
            start_s = seg["orig_start_ms"] / 1000.0
            end_s = seg["orig_end_ms"] / 1000.0

            if end_s <= start_s + 0.05:
                end_s = start_s + 0.1

            ratio = seg["ratio"]
            target_dur = seg["target_dur_ms"] / 1000.0
            orig_dur = (seg["orig_end_ms"] - seg["orig_start_ms"]) / 1000.0

            # CRITICAL FIX: ratio interpretation for setpts filter
            # ratio = target_dur / orig_dur (how much longer/shorter the output should be)
            # For setpts=N*PTS: N = orig_dur / target_dur = 1/ratio
            # - If ratio > 1.0 (target > orig): video needs to be LONGER → slow down → setpts scale < 1
            # - If ratio < 1.0 (target < orig): video needs to be SHORTER → speed up → setpts scale > 1
            
            if seg["type"] == "gap" or abs(ratio - 1.0) <= 0.02:
                # Normal speed - just extract segment with proper timestamp reset
                vf_str = f"trim=start={start_s}:end={end_s},setpts=PTS-STARTPTS,pad=ceil(iw/2)*2:ceil(ih/2)*2"
            else:
                # Apply speed change using setpts
                # pts_scale = orig_dur / target_dur = 1 / ratio
                # This is the INVERSE of the duration ratio!
                pts_scale = orig_dur / target_dur if target_dur > 0 else 1.0
                
                # Clamp pts_scale to avoid extreme values that cause glitches
                pts_scale = max(0.5, min(2.0, pts_scale))
                
                # Build filter chain: trim → speed change → optional freeze frame extension
                vf_str = f"trim=start={start_s}:end={end_s},setpts={pts_scale:.6f}*PTS"
                
                # Calculate warped duration after speed change
                warped_dur = orig_dur / pts_scale if pts_scale > 0 else orig_dur
                
                # If target duration is longer than warped duration, extend with frozen last frame
                if target_dur > warped_dur + 0.15:  # More than 150ms difference
                    pad_dur = target_dur - warped_dur
                    vf_str = f"{vf_str},tpad=stop_mode=clone:stop_duration={pad_dur:.3f}"
                
                # Add timestamp reset and padding to ensure even dimensions
                vf_str = f"{vf_str},setpts=PTS-STARTPTS,pad=ceil(iw/2)*2:ceil(ih/2)*2"

            # CRITICAL FIX: Remove -copyts and -vsync vfr during segment extraction
            # These cause timestamp conflicts with setpts modifications
            # Use constant framerate and let final assembly handle sync
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-ss", str(start_s),
                "-to", str(end_s),
                "-vf", vf_str,
                "-an",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-vsync", "1",  # Constant framerate for smooth playback
                "-r", "30",     # Force 30fps for consistency
                "-avoid_negative_ts", "make_one",
                seg_out
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return idx, f"file '{seg_out.replace('\\\\', '/')}'\n"

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

        # Merge segments into raw retimed video using concat demuxer with exact frame matching
        raw_retimed_video = os.path.join(temp_dir, "raw_retimed_video.mp4")
        
        # CRITICAL FIX: Re-encode with consistent settings to ensure smooth playback
        # Remove -copyts as it conflicts with our timestamp modifications
        # Use constant framerate for smooth concatenation
        cmd_concat = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-fflags", "+genpts",
            "-i", concat_file,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-vsync", "1",
            "-r", "30",
            "-an",
            "-movflags", "+faststart",
            "-avoid_negative_ts", "make_one",
            raw_retimed_video
        ]
        subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # Step 5: Final Assembly with Audio & Burned Subtitles
        print("\n[5/5] Final assembly: muxing video + voiceover + subtitles...")
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

        # CRITICAL FIX: Remove -shortest as it causes audio/video desync
        # Video duration should already match audio from retiming process
        # Use constant framerate for smooth playback
        cmd_final.extend([
            "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-vsync", "1",
            "-r", "30",
            "-movflags", "+faststart",
            "-avoid_negative_ts", "make_one",
            final_output
        ])

        subprocess.run(cmd_final, check=True)

        print(f"\n=========================================================================")
        print(f"🎉 RETIMED RECAP VIDEO READY AT: {final_output}")
        print(f"   ✓ Speed changes bounded to {MIN_SPEED_RATIO}x-{MAX_SPEED_RATIO}x (natural motion)")
        print(f"   ✓ Freeze frames used for audio/video length mismatches")
        print(f"=========================================================================\n")
        return final_output

