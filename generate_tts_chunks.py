#!/usr/bin/env python3
"""
=============================================================================
         CHUNKED VTT/SRT TEXT-TO-SPEECH (TTS) GENERATOR WITH CACHING
=============================================================================
Parses .vtt/.srt subtitle files or folders of subtitle files into individual cues,
generates timestamp-matched audio clips (e.g. chunk_001.mp3, chunk_002.mp3),
caches completed chunks to prevent re-processing, logs manifests, and optionally
stitches all clips into a frame-synced master audio timeline.
"""

import os
import re
import json
import csv
import sys
import asyncio
import argparse
import subprocess
import shutil
import tempfile
from pydub import AudioSegment
import edge_tts

def parse_time_to_ms(time_str):
    """Parses VTT/SRT timestamp strings to milliseconds."""
    time_str = time_str.replace(",", ".").strip()
    parts = time_str.split(":")
    
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h = "0"
        m, s = parts
    else:
        return 0

    seconds = float(s)
    return int((int(h) * 3600 + int(m) * 60 + seconds) * 1000)

def ms_to_timestamp(ms):
    """Converts milliseconds to HH:MM:SS.mmm string."""
    seconds, milliseconds = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

def parse_single_sub_file(file_path):
    """Parses a single .vtt or .srt file returning timed text entries."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        r"(?:(\d+)\n)?((\d{1,2}:)?\d{2}:\d{2}[\.,]\d{3})\s*-->\s*((\d{1,2}:)?\d{2}:\d{2}[\.,]\d{3})\n(.*?)(?=\n\n|\Z)",
        re.DOTALL
    )

    entries = []
    for match in pattern.finditer(content):
        start_str = match.group(2)
        end_str = match.group(4)
        text_block = match.group(6).strip()
        
        # Remove HTML-like tags (e.g. <i>...</i>) if present
        text_clean = re.sub(r"<[^>]+>", "", text_block)
        text = " ".join([line.strip() for line in text_clean.splitlines() if line.strip()])
        if not text:
            continue

        start_ms = parse_time_to_ms(start_str)
        end_ms = parse_time_to_ms(end_str)

        entries.append({
            "start_time": ms_to_timestamp(start_ms),
            "end_time": ms_to_timestamp(end_ms),
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": max(end_ms - start_ms, 100),
            "text": text,
            "source_file": os.path.basename(file_path)
        })

    return entries

def parse_subtitles(file_or_dir_path):
    """
    Parses a single VTT/SRT file OR a directory containing chunked VTT/SRT files.
    Combines, sorts, and indexes all entries naturally.
    """
    all_entries = []

    if os.path.isdir(file_or_dir_path):
        sub_files = []
        for f in os.listdir(file_or_dir_path):
            if f.lower().endswith((".vtt", ".srt")):
                sub_files.append(os.path.join(file_or_dir_path, f))
        
        # Natural sort order (e.g. 1_..., 2_..., 10_...)
        sub_files.sort(key=lambda x: [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', os.path.basename(x))])

        print(f"Detected {len(sub_files)} subtitle files in folder '{file_or_dir_path}':")
        for sf in sub_files:
            parsed = parse_single_sub_file(sf)
            print(f"  └─ {os.path.basename(sf)} ({len(parsed)} cues)")
            all_entries.extend(parsed)
    else:
        all_entries = parse_single_sub_file(file_or_dir_path)

    # Sort entries strictly by start time
    all_entries.sort(key=lambda x: x["start_ms"])

    # Re-index 1..N
    for i, entry in enumerate(all_entries, 1):
        entry["index"] = i
        entry["chunk_filename"] = f"chunk_{i:03d}.mp3"

    return all_entries

async def async_stretch_audio_to_duration(input_path, output_path, target_duration_ms):
    """
    Adjusts audio playback speed via FFmpeg atempo filter if clip duration
    exceeds target scene window. Non-blocking & fast copy fallback.
    """
    if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
        await asyncio.to_thread(
            lambda: AudioSegment.silent(duration=max(target_duration_ms, 500)).export(output_path, format="mp3")
        )
        return

    clip = await asyncio.to_thread(AudioSegment.from_file, input_path)
    actual_duration_ms = len(clip)

    if actual_duration_ms > target_duration_ms and target_duration_ms > 200:
        speed_ratio = min(actual_duration_ms / target_duration_ms, 2.0)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", input_path,
            "-filter:a", f"atempo={speed_ratio:.4f}",
            output_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        await proc.communicate()
    else:
        await asyncio.to_thread(shutil.copyfile, input_path, output_path)

async def generate_single_chunk_tts(entry, voice, output_dir, semaphore, retries=3, force=False):
    """
    Generates TTS for a single subtitle chunk with retry logic, caching, and non-blocking audio processing.
    """
    async with semaphore:
        chunk_file = entry["chunk_filename"]
        final_chunk_path = os.path.join(output_dir, chunk_file)
        raw_clip_path = os.path.join(output_dir, f"raw_{chunk_file}")

        # Check caching
        if not force and os.path.exists(final_chunk_path) and os.path.getsize(final_chunk_path) > 0:
            try:
                clip = await asyncio.to_thread(AudioSegment.from_file, final_chunk_path)
                entry["audio_duration_ms"] = len(clip)
                entry["status"] = "COMPLETED"
                entry["audio_path"] = final_chunk_path
                return entry, True  # Cached
            except Exception:
                pass  # Fallback to re-generating if file is corrupt

        print(f"🎙️ Generating [{entry['index']}/{entry['total']}] {chunk_file}: \"{entry['text'][:35]}...\"")

        success = False
        last_error = ""

        for attempt in range(1, retries + 1):
            try:
                communicate = edge_tts.Communicate(entry['text'], voice)
                await communicate.save(raw_clip_path)

                if os.path.exists(raw_clip_path) and os.path.getsize(raw_clip_path) > 0:
                    success = True
                    break
            except Exception as e:
                last_error = str(e)
                if attempt < retries:
                    await asyncio.sleep(0.5 * attempt)

        if success:
            await async_stretch_audio_to_duration(raw_clip_path, final_chunk_path, entry['duration_ms'])
            if os.path.exists(raw_clip_path):
                try:
                    os.remove(raw_clip_path)
                except OSError:
                    pass

            clip = await asyncio.to_thread(AudioSegment.from_file, final_chunk_path)
            entry["audio_duration_ms"] = len(clip)
            entry["status"] = "COMPLETED"
            entry["audio_path"] = final_chunk_path
            print(f"  └─ ✅ Saved {chunk_file} ({entry['audio_duration_ms']}ms)", flush=True)
        else:
            print(f"  └─ ❌ FAILED [{chunk_file}] after {retries} retries: {last_error}", flush=True)
            entry["status"] = f"FAILED: {last_error}"
            entry["audio_duration_ms"] = 0
            entry["audio_path"] = None

        return entry, False

async def generate_chunks_parallel(entries, voice, output_dir, max_workers=10, retries=3, force=False):
    """Runs parallel async tasks for chunk audio generation."""
    semaphore = asyncio.Semaphore(max_workers)
    total = len(entries)
    for entry in entries:
        entry["total"] = total

    tasks = [
        generate_single_chunk_tts(entry, voice, output_dir, semaphore, retries=retries, force=force)
        for entry in entries
    ]

    results = await asyncio.gather(*tasks)

    cached_count = sum(1 for _, cached in results if cached)
    generated_count = sum(1 for _, cached in results if not cached)
    failed_count = sum(1 for entry in entries if entry["status"].startswith("FAILED"))

    return cached_count, generated_count, failed_count

def save_manifests(entries, output_dir):
    """Exports machine-readable JSON manifest, CSV log, and text summary."""
    json_path = os.path.join(output_dir, "manifest.json")
    csv_path = os.path.join(output_dir, "manifest.csv")
    log_path = os.path.join(output_dir, "timestamp_log.txt")

    # 1. JSON Manifest
    manifest_data = {
        "total_chunks": len(entries),
        "completed_chunks": sum(1 for e in entries if e.get("status") == "COMPLETED"),
        "failed_chunks": sum(1 for e in entries if str(e.get("status")).startswith("FAILED")),
        "chunks": entries
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    # 2. CSV Manifest
    fieldnames = ["index", "chunk_filename", "start_time", "end_time", "start_ms", "end_ms", "duration_ms", "audio_duration_ms", "status", "text", "source_file"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            row = {k: entry.get(k, "") for k in fieldnames}
            writer.writerow(row)

    # 3. Human-Readable Timestamp Log
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=====================================================================\n")
        f.write("                 TTS AUDIO CHUNK TIMESTAMP LOG                       \n")
        f.write("=====================================================================\n\n")
        for entry in entries:
            f.write(f"[{entry['chunk_filename']}] {entry['start_time']} --> {entry['end_time']} ({entry['duration_ms']}ms)\n")
            f.write(f"Status: {entry['status']} | Audio Length: {entry.get('audio_duration_ms', 0)}ms\n")
            f.write(f"Text:   {entry['text']}\n")
            f.write("-" * 65 + "\n")

    print(f"📊 Manifest files written to '{output_dir}':")
    print(f"  ├─ JSON Manifest:    {json_path}")
    print(f"  ├─ CSV Manifest:     {csv_path}")
    print(f"  └─ Timestamp Log:    {log_path}")

def stitch_chunks_to_master(entries, output_audio_path):
    """
    Stitches individual chunk audio clips into a single master audio track
    synced to exact VTT cue timestamps. Optimized with single-allocation master timeline.
    """
    print(f"\n🧩 Stitching {len(entries)} audio chunks into master audio file...")
    
    valid_entries = [
        e for e in entries 
        if e.get("audio_path") and os.path.exists(e["audio_path"]) and os.path.getsize(e["audio_path"]) > 0
    ]
    if not valid_entries:
        print("Warning: No valid audio chunks found to stitch.")
        return output_audio_path

    # Preallocate master audio segment matching subtitle timestamps or reference original audio duration
    max_duration_ms = max(e["start_ms"] + e.get("audio_duration_ms", 5000) for e in valid_entries) + 1000

    # Match exact video/audio duration if audio.mp3 is available in project folder
    project_dir = os.path.dirname(os.path.abspath(output_audio_path))
    ref_audio = os.path.join(project_dir, "audio.mp3")
    if os.path.exists(ref_audio) and os.path.getsize(ref_audio) > 0:
        try:
            ref_clip = AudioSegment.from_file(ref_audio)
            max_duration_ms = max(max_duration_ms, len(ref_clip))
        except Exception:
            pass

    master_audio = AudioSegment.silent(duration=max_duration_ms)

    success_count = 0
    for entry in valid_entries:
        try:
            clip_path = entry["audio_path"]
            clip = AudioSegment.from_file(clip_path)
            master_audio = master_audio.overlay(clip, position=entry["start_ms"])
            success_count += 1
        except Exception as e:
            print(f"Warning: Failed to overlay chunk {entry.get('chunk_filename')}: {e}")

    os.makedirs(os.path.dirname(os.path.abspath(output_audio_path)), exist_ok=True)
    master_audio.export(output_audio_path, format="mp3")
    total_sec = len(master_audio) / 1000.0
    print(f"🎉 Master synced voiceover ({total_sec:.2f}s) exported to: {output_audio_path}")
    return output_audio_path

async def process_sub_file_to_audio_async(sub_file_path, voice, output_mp3_path, cue_semaphore, force=False):
    """
    Synthesizes all cues for a single VTT/SRT file directly in memory/temp buffer
    and exports EXACTLY ONE matching MP3 audio file. No per-cue MP3s are left on disk!
    """
    base_name = os.path.basename(sub_file_path)

    if not force and os.path.exists(output_mp3_path) and os.path.getsize(output_mp3_path) > 0:
        entries = parse_single_sub_file(sub_file_path)
        min_start = min(e["start_ms"] for e in entries) if entries else 0
        print(f"⏩ [File Worker] '{base_name}' already COMPLETED (cached). Skipping.")
        return output_mp3_path, min_start, entries

    entries = parse_single_sub_file(sub_file_path)
    if not entries:
        return output_mp3_path, 0, []

    print(f"🎙️ [File Worker] Processing '{base_name}' ({len(entries)} cues)...")

    min_start = min(e["start_ms"] for e in entries)
    max_end = max(e["end_ms"] for e in entries)
    file_duration_ms = max(max_end - min_start + 1000, 1000)

    with tempfile.TemporaryDirectory() as temp_dir:
        async def fetch_cue(idx, entry):
            async with cue_semaphore:
                raw_clip_path = os.path.join(temp_dir, f"raw_{idx}.mp3")
                adj_clip_path = os.path.join(temp_dir, f"adj_{idx}.mp3")
                try:
                    comm = edge_tts.Communicate(entry["text"], voice)
                    await comm.save(raw_clip_path)
                    if os.path.exists(raw_clip_path) and os.path.getsize(raw_clip_path) > 0:
                        clip = await asyncio.to_thread(AudioSegment.from_file, raw_clip_path)
                        if len(clip) > entry["duration_ms"] and entry["duration_ms"] > 200:
                            speed_ratio = min(len(clip) / entry["duration_ms"], 2.0)
                            proc = await asyncio.create_subprocess_exec(
                                "ffmpeg", "-y", "-i", raw_clip_path,
                                "-filter:a", f"atempo={speed_ratio:.4f}",
                                adj_clip_path,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                            await proc.communicate()
                            if os.path.exists(adj_clip_path):
                                res_clip = await asyncio.to_thread(AudioSegment.from_file, adj_clip_path)
                                return entry["start_ms"], res_clip
                        return entry["start_ms"], clip
                except Exception as e:
                    print(f"Warning: TTS failed for cue '{entry['text'][:20]}...': {e}")
                return entry["start_ms"], AudioSegment.silent(duration=max(entry["duration_ms"], 500))

        tasks = [fetch_cue(i, entry) for i, entry in enumerate(entries, 1)]
        cue_results = await asyncio.gather(*tasks)

        # Assemble single audio track for this subtitle file
        file_audio = AudioSegment.silent(duration=file_duration_ms)
        for abs_start_ms, clip in cue_results:
            rel_pos = abs_start_ms - min_start
            file_audio = file_audio.overlay(clip, position=rel_pos)

        os.makedirs(os.path.dirname(os.path.abspath(output_mp3_path)), exist_ok=True)
        await asyncio.to_thread(file_audio.export, output_mp3_path, format="mp3")
        print(f"  └─ 🎵 Exported '{os.path.basename(output_mp3_path)}' ({len(entries)} cues, {len(file_audio)/1000.0:.1f}s)")
        return output_mp3_path, min_start, entries

async def generate_file_level_tts_parallel(sub_files, voice, output_dir, max_workers=10, force=False):
    """
    Multiprocessing engine that generates 1 matching MP3 file per input VTT file in parallel.
    NO per-cue chunk files are created on disk!
    """
    cue_semaphore = asyncio.Semaphore(max_workers)
    
    file_tasks = []
    for sf in sub_files:
        base_name = os.path.splitext(os.path.basename(sf))[0]
        out_mp3 = os.path.join(output_dir, f"{base_name}.mp3")
        file_tasks.append(process_sub_file_to_audio_async(sf, voice, out_mp3, cue_semaphore, force=force))

    file_results = await asyncio.gather(*file_tasks)
    return file_results

def stitch_file_mp3s_to_master(file_results, output_audio_path):
    """Stitches the per-file MP3 outputs into the single master voiceover track."""
    print(f"\n🧩 Stitching {len(file_results)} per-file MP3 outputs into master voiceover...")
    valid_results = [r for r in file_results if r[0] and os.path.exists(r[0])]
    if not valid_results:
        return output_audio_path

    # Determine total master duration
    max_end_ms = 0
    for mp3_path, min_start, entries in valid_results:
        clip = AudioSegment.from_file(mp3_path)
        end_ms = min_start + len(clip)
        if end_ms > max_end_ms:
            max_end_ms = end_ms

    master_audio = AudioSegment.silent(duration=max_end_ms + 1000)
    for mp3_path, min_start, _ in valid_results:
        clip = AudioSegment.from_file(mp3_path)
        master_audio = master_audio.overlay(clip, position=min_start)

    os.makedirs(os.path.dirname(os.path.abspath(output_audio_path)), exist_ok=True)
    master_audio.export(output_audio_path, format="mp3")
    print(f"🎉 Master synced voiceover ({len(master_audio)/1000.0:.2f}s) exported to: {output_audio_path}")
    return output_audio_path

def process_vtt_tts_chunks(input_path, output_dir=None, voice="en-US-GuyNeural", 
                           workers=10, retries=5, force=False, stitch=True, master_output=None):
    """
    Main entry point for parallel VTT Text-to-Speech (TTS) generation with persistent chunk caching.
    Supports single VTT file or folder of split VTT files.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    # Determine output directory
    if not output_dir:
        if os.path.isdir(input_path):
            output_dir = os.path.join(input_path, "tts_chunks")
        else:
            output_dir = os.path.join(os.path.dirname(os.path.abspath(input_path)), "tts_chunks")

    os.makedirs(output_dir, exist_ok=True)

    print("=====================================================================")
    print("      PARALLEL VTT TEXT-TO-SPEECH (TTS) GENERATOR                   ")
    print("=====================================================================")
    print(f"Subtitle Input: {os.path.abspath(input_path)}")
    print(f"Output Folder:  {os.path.abspath(output_dir)}")
    print(f"Voice Engine:   {voice}")
    print(f"Concurrency:    {workers} parallel workers")
    print("=====================================================================\n")

    master_path = master_output or os.path.join(os.path.dirname(output_dir), "synced_voiceover.mp3")

    entries = parse_subtitles(input_path)
    if not entries:
        print("Warning: No subtitle entries found to generate TTS.")
        return output_dir, master_path

    print(f"Parsed {len(entries)} subtitle cues. Starting persistent TTS chunk generation...\n")

    cached_count, generated_count, failed_count = asyncio.run(
        generate_chunks_parallel(entries, voice, output_dir, max_workers=workers, retries=retries, force=force)
    )

    save_manifests(entries, output_dir)

    # Stitch all chunks into master voiceover track
    master_path = stitch_chunks_to_master(entries, master_path)

    return output_dir, master_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parallel Per-File VTT Text-to-Speech (TTS) Engine")
    parser.add_argument("input_path", help="Path to .vtt/.srt subtitle file OR folder of split subtitles (e.g. Translated/)")
    parser.add_argument("-o", "--output-dir", help="Directory to save generated audio files (default: <input>/tts_chunks)")
    parser.add_argument("-v", "--voice", default="en-US-GuyNeural", help="Edge-TTS voice (default: en-US-GuyNeural)")
    parser.add_argument("-w", "--workers", type=int, default=10, help="Parallel worker concurrency (default: 10)")
    parser.add_argument("-r", "--retries", type=int, default=3, help="Max retries per chunk on failure (default: 3)")
    parser.add_argument("--force", action="store_true", help="Force re-generating all files ignoring cache")
    parser.add_argument("--stitch", action="store_true", help="Stitch audio files into master synced voiceover file after generation")
    parser.add_argument("--master-output", help="Custom output filepath for stitched master audio")

    args = parser.parse_args()

    process_vtt_tts_chunks(
        input_path=args.input_path,
        output_dir=args.output_dir,
        voice=args.voice,
        workers=args.workers,
        retries=args.retries,
        force=args.force,
        stitch=args.stitch,
        master_output=args.master_output
    )
