import os
import re
import asyncio
import tempfile
import subprocess
import shutil
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

def ms_to_vtt_timestamp(ms):
    """Converts milliseconds to VTT timestamp string (HH:MM:SS.mmm)."""
    seconds, milliseconds = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

def parse_single_sub_file(file_path):
    """Parses a single .vtt or .srt file returning timed text entries with automatic repetition deduplication."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(
        r"(?:(\d+)\n)?((\d{1,2}:)?\d{2}:\d{2}[\.,]\d{3})\s*-->\s*((\d{1,2}:)?\d{2}:\d{2}[\.,]\d{3})\n(.*?)(?=\n\n|\Z)",
        re.DOTALL
    )

    raw_entries = []
    for match in pattern.finditer(content):
        start_str = match.group(2)
        end_str = match.group(4)
        text_block = match.group(6).strip()
        
        text_clean = re.sub(r"<[^>]+>", "", text_block)
        text = " ".join([line.strip() for line in text_clean.splitlines() if line.strip()])
        if not text:
            continue

        start_ms = parse_time_to_ms(start_str)
        end_ms = parse_time_to_ms(end_str)

        raw_entries.append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": max(end_ms - start_ms, 100),
            "text": text,
            "source_file": os.path.basename(file_path)
        })

    # Deduplicate consecutive identical text cues (Whisper repetition hallucination filter)
    entries = []
    for entry in raw_entries:
        if entries:
            last = entries[-1]
            norm_last = re.sub(r"[^\w]", "", last["text"].lower())
            norm_curr = re.sub(r"[^\w]", "", entry["text"].lower())
            if norm_last and norm_last == norm_curr:
                last["end_ms"] = max(last["end_ms"], entry["end_ms"])
                last["duration_ms"] = max(last["end_ms"] - last["start_ms"], 100)
                continue
        entries.append(entry)

    return entries

def clean_subtitle_file(file_path):
    """
    Cleans a VTT/SRT file by merging consecutive duplicate subtitle cues.
    Overwrites the file on disk.
    """
    if not os.path.exists(file_path):
        return file_path

    entries = parse_single_sub_file(file_path)
    lines = ["WEBVTT\n"]
    for entry in entries:
        start_ts = ms_to_vtt_timestamp(entry["start_ms"])
        end_ts = ms_to_vtt_timestamp(entry["end_ms"])
        lines.append(f"\n{start_ts} --> {end_ts}\n{entry['text']}\n")

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"🧹 Cleaned duplicate subtitle hallucinations in: {file_path}")
    return file_path

def parse_subtitle_file(file_or_dir_path):
    """
    Parses a single VTT/SRT file OR a directory containing multiple chunked VTT/SRT files.
    Combines and sorts all subtitle scenes by start time.
    """
    all_entries = []

    if os.path.isdir(file_or_dir_path):
        sub_files = []
        for f in os.listdir(file_or_dir_path):
            if f.lower().endswith((".vtt", ".srt")):
                sub_files.append(os.path.join(file_or_dir_path, f))
        
        sub_files.sort(key=lambda x: [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', os.path.basename(x))])

        for sf in sub_files:
            all_entries.extend(parse_single_sub_file(sf))
    else:
        all_entries = parse_single_sub_file(file_or_dir_path)

    all_entries.sort(key=lambda x: x["start_ms"])

    for i, entry in enumerate(all_entries, 1):
        entry["index"] = i

    return all_entries

def export_combined_vtt(file_or_dir_path, output_vtt):
    """Merges single or multiple subtitle files into one master WEBVTT file for video burning."""
    entries = parse_subtitle_file(file_or_dir_path)
    os.makedirs(os.path.dirname(output_vtt), exist_ok=True)

    def ms_to_vtt_timestamp(ms):
        seconds, milliseconds = divmod(ms, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

    lines = ["WEBVTT\n"]
    for entry in entries:
        start_ts = ms_to_vtt_timestamp(entry["start_ms"])
        end_ts = ms_to_vtt_timestamp(entry["end_ms"])
        lines.append(f"\n{start_ts} --> {end_ts}\n{entry['text']}\n")

    with open(output_vtt, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return output_vtt

async def process_synced_redub_direct_async(subtitle_path, output_mp3, voice="en-US-GuyNeural", max_workers=10):
    """
    Direct 1-pass synthesis into the master audio track with exact VTT timeline spacing.
    No persistent chunk files left on disk!
    """
    entries = parse_subtitle_file(subtitle_path)
    if not entries:
        print("Warning: No subtitle entries found to generate TTS.")
        return output_mp3

    project_dir = os.path.dirname(os.path.abspath(output_mp3))
    ref_audio = os.path.join(project_dir, "audio.mp3")
    
    max_duration_ms = max(e["end_ms"] for e in entries) + 1000
    if os.path.exists(ref_audio) and os.path.getsize(ref_audio) > 0:
        try:
            ref_clip = AudioSegment.from_file(ref_audio)
            max_duration_ms = max(max_duration_ms, len(ref_clip))
        except Exception:
            pass

    print(f"\n🎙️ Synthesizing {len(entries)} subtitle cues directly into master voiceover...")
    print(f"Timeline Duration: {max_duration_ms / 1000.0:.2f}s | Voice: {voice} | Concurrency: {max_workers} workers\n")

    with tempfile.TemporaryDirectory() as temp_dir:
        semaphore = asyncio.Semaphore(max_workers)
        completed_count = 0
        total_cues = len(entries)

        async def synthesize_entry(entry):
            nonlocal completed_count
            async with semaphore:
                text = entry["text"]
                start_ms = entry["start_ms"]
                duration_ms = entry["duration_ms"]
                idx = entry["index"]
                
                raw_path = os.path.join(temp_dir, f"raw_{idx}.mp3")
                adj_path = os.path.join(temp_dir, f"adj_{idx}.mp3")
                
                for attempt in range(4):
                    try:
                        comm = edge_tts.Communicate(text, voice)
                        await comm.save(raw_path)
                        if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
                            break
                    except Exception:
                        await asyncio.sleep(0.5 * (attempt + 1))

                completed_count += 1
                if completed_count % 20 == 0 or completed_count == total_cues or completed_count == 1:
                    percent = (completed_count / total_cues) * 100
                    print(f"🎙️ Progress: [{completed_count}/{total_cues}] cues synthesized ({percent:.1f}%)...", flush=True)

                if not os.path.exists(raw_path) or os.path.getsize(raw_path) == 0:
                    return start_ms, None

                try:
                    clip = await asyncio.to_thread(AudioSegment.from_file, raw_path)
                    if len(clip) > duration_ms and duration_ms > 200:
                        target_speed = len(clip) / duration_ms
                        # Chain atempo filters if target_speed > 2.0 (FFmpeg limit per atempo filter)
                        atempo_filters = []
                        rem_speed = target_speed
                        while rem_speed > 2.0:
                            atempo_filters.append("atempo=2.0")
                            rem_speed /= 2.0
                        if rem_speed > 1.0:
                            atempo_filters.append(f"atempo={rem_speed:.4f}")
                        filter_str = ",".join(atempo_filters) if atempo_filters else "anull"

                        proc = await asyncio.create_subprocess_exec(
                            "ffmpeg", "-y", "-i", raw_path,
                            "-filter:a", filter_str,
                            adj_path,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        await proc.communicate()
                        if os.path.exists(adj_path):
                            clip = await asyncio.to_thread(AudioSegment.from_file, adj_path)
                    return start_ms, clip
                except Exception:
                    return start_ms, None

        tasks = [synthesize_entry(e) for e in entries]
        results = await asyncio.gather(*tasks)

        print("\n🧩 Stitching audio clips into master voiceover timeline...", flush=True)
        master_audio = AudioSegment.silent(duration=max_duration_ms)
        success_count = 0
        for start_ms, clip in results:
            if clip is not None and len(clip) > 0:
                master_audio = master_audio.overlay(clip, position=start_ms)
                success_count += 1

        os.makedirs(os.path.dirname(os.path.abspath(output_mp3)), exist_ok=True)
        await asyncio.to_thread(master_audio.export, output_mp3, format="mp3")
        print(f"🎉 Master synced voiceover ({success_count}/{len(entries)} cues, {len(master_audio)/1000.0:.2f}s) exported to: {output_mp3}")
        return output_mp3

def process_synced_redub(sub_file_or_dir, output_mp3, voice="en-US-GuyNeural", max_workers=10):
    """Master time-synced TTS generator."""
    asyncio.run(process_synced_redub_direct_async(sub_file_or_dir, output_mp3, voice=voice, max_workers=max_workers))

def generate_voiceover(subtitle_path, project_dir, voice="en-US-GuyNeural", workers=10):
    """Wrapper function for project output folder."""
    output_voiceover = os.path.join(project_dir, "synced_voiceover.mp3")
    process_synced_redub(subtitle_path, output_voiceover, voice=voice, max_workers=workers)
    return output_voiceover
