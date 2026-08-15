import os
import re
import asyncio
import tempfile
import subprocess
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
        
        text = " ".join([line.strip() for line in text_block.splitlines() if line.strip()])
        if not text:
            continue

        start_ms = parse_time_to_ms(start_str)
        end_ms = parse_time_to_ms(end_str)

        entries.append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": end_ms - start_ms,
            "text": text,
            "source_file": os.path.basename(file_path)
        })

    return entries

def parse_subtitle_file(file_or_dir_path):
    """
    Parses a single VTT/SRT file OR a directory containing multiple chunked VTT/SRT files 
    (e.g., Translated/ 1_audio_txt.vtt, 2_audio.txt.vtt, etc.).
    Combines and sorts all subtitle scenes by start time.
    """
    all_entries = []

    if os.path.isdir(file_or_dir_path):
        sub_files = []
        for f in os.listdir(file_or_dir_path):
            if f.endswith(".vtt") or f.endswith(".srt"):
                sub_files.append(os.path.join(file_or_dir_path, f))
        
        # Sort files naturally (e.g. 1_..., 2_..., 10_...)
        sub_files.sort(key=lambda x: [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', os.path.basename(x))])

        print(f"Detected {len(sub_files)} subtitle files in translated folder:")
        for sf in sub_files:
            print(f"  └─ {os.path.basename(sf)}")
            all_entries.extend(parse_single_sub_file(sf))
    else:
        all_entries = parse_single_sub_file(file_or_dir_path)

    # Sort all entries by start_ms
    all_entries.sort(key=lambda x: x["start_ms"])

    # Re-index 1..N
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

def stretch_audio_to_duration(input_path, output_path, target_duration_ms):
    """Speeds up audio clip via FFmpeg atempo filter if longer than scene window."""
    if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
        AudioSegment.silent(duration=max(target_duration_ms, 500)).export(output_path, format="mp3")
        return

    clip = AudioSegment.from_file(input_path)
    actual_duration_ms = len(clip)

    if actual_duration_ms > target_duration_ms and target_duration_ms > 200:
        speed_ratio = min(actual_duration_ms / target_duration_ms, 2.0)
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-filter:a", f"atempo={speed_ratio:.4f}",
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        clip.export(output_path, format="mp3")

async def generate_single_tts(entry, voice, temp_dir, semaphore, retries=3):
    """Generate TTS clip asynchronously with retry logic & fallback for edge_tts network glitches."""
    async with semaphore:
        raw_clip_path = os.path.join(temp_dir, f"raw_{entry['index']}.mp3")
        adjusted_clip_path = os.path.join(temp_dir, f"adj_{entry['index']}.mp3")

        for attempt in range(retries):
            try:
                communicate = edge_tts.Communicate(entry['text'], voice)
                await communicate.save(raw_clip_path)
                if os.path.exists(raw_clip_path) and os.path.getsize(raw_clip_path) > 0:
                    break
            except Exception as e:
                if attempt == retries - 1:
                    print(f"Warning: TTS failed for line {entry['index']} ('{entry['text'][:20]}...'): {e}")
                await asyncio.sleep(0.5 * (attempt + 1))

        stretch_audio_to_duration(raw_clip_path, adjusted_clip_path, entry['duration_ms'])
        entry['audio_path'] = adjusted_clip_path

async def generate_all_tts_parallel(entries, voice, temp_dir, max_workers=10):
    """Parallel batch generator for subtitle speech clips."""
    semaphore = asyncio.Semaphore(max_workers)
    tasks = [generate_single_tts(entry, voice, temp_dir, semaphore) for entry in entries]
    print(f"Generating {len(entries)} speech clips in parallel (Concurrency: {max_workers})...")
    await asyncio.gather(*tasks)

def process_synced_redub(sub_file_or_dir, output_mp3, voice="en-US-GuyNeural", max_workers=10):
    """Master time-synced TTS generator with persistent chunk caching & manifest logging."""
    from generate_tts_chunks import process_vtt_tts_chunks

    project_dir = os.path.dirname(os.path.abspath(output_mp3))
    chunks_dir = os.path.join(project_dir, "tts_chunks")

    process_vtt_tts_chunks(
        input_path=sub_file_or_dir,
        output_dir=chunks_dir,
        voice=voice,
        workers=max_workers,
        stitch=True,
        master_output=output_mp3
    )

def generate_voiceover(subtitle_path, project_dir, voice="en-US-GuyNeural", workers=10):
    """Wrapper function for project output folder."""
    output_voiceover = os.path.join(project_dir, "synced_voiceover.mp3")
    process_synced_redub(subtitle_path, output_voiceover, voice=voice, max_workers=workers)
    return output_voiceover

