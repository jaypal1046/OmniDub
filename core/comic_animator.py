import os
import subprocess
import tempfile
from PIL import Image

def get_audio_duration_sec(audio_path):
    """
    Retrieves duration of audio file in seconds using ffprobe.
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:
        return 3.0

def generate_page_tts(script_text, output_audio_path, voice="en-US-ChristopherNeural"):
    """
    Generates synthesized speech audio clip using edge-tts CLI.
    """
    if os.path.exists(output_audio_path) and os.path.getsize(output_audio_path) > 0:
        return output_audio_path

    cmd = [
        "edge-tts",
        "--voice", voice,
        "--text", script_text,
        "--write-media", output_audio_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return output_audio_path

def build_ken_burns_video_segment(image_path, audio_path, subtitle_text, output_video_path,
                                  preset="zoom_in", width=1920, height=1080, fps=30):
    """
    Renders a synced video segment from a single comic panel image & narration audio clip:
    1. Dark Frosted Glassmorphism Blurred Background Canvas (boxblur=30:15 + colorchannelmixer dark tint)
    2. Sharp centered comic panel artwork with exact aspect ratio
    3. Dynamic Ken Burns camera pan/zoom animation
    4. Burned subtitle caption bar at bottom
    5. High-efficiency H.264 encoding for compact file size (CRF 26, 1200k bitrate)
    """
    duration = get_audio_duration_sec(audio_path)
    total_frames = int(duration * fps)
    if total_frames < 1:
        total_frames = int(3.0 * fps)
        duration = 3.0

    if preset == "zoom_in":
        zoom_expr = f"min(1.0+0.15*(on/{total_frames}),1.15)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif preset == "zoom_out":
        zoom_expr = f"max(1.15-0.15*(on/{total_frames}),1.0)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif preset == "pan_down":
        zoom_expr = "1.15"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-(ih/zoom))*(on/{total_frames})"
    elif preset == "pan_right":
        zoom_expr = "1.15"
        x_expr = f"(iw-(iw/zoom))*(on/{total_frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        zoom_expr = "1.0"
        x_expr = "0"
        y_expr = "0"

    clean_sub = subtitle_text.replace("'", "'\\''").replace(":", "\\:").replace('"', '\\"')

    # FFmpeg Filter Complex:
    # [0:v] -> Scale & BoxBlur + Dark Colorchannelmixer for Frosted Glass Background
    # [0:v] -> Scale sharp panel to fit canvas without distortion
    # Overlay sharp panel centered on frosted glass background -> Zoompan -> Burned Subtitles
    filter_complex = (
        f"[0:v]scale=480:270:force_original_aspect_ratio=increase,crop=480:270,"
        f"boxblur=10:5,colorchannelmixer=rr=0.35:gg=0.35:bb=0.35,scale={width}:{height}[bg];"
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base]zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={total_frames}:s={width}x{height}:fps={fps},"
        f"drawtext=text='{clean_sub}':fontcolor=white:fontsize=36:box=1:boxcolor=black@0.75:boxborderw=10:"
        f"x=(w-text_w)/2:y=h-text_h-50:fix_bounds=true[v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "26", "-b:v", "1200k", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-t", f"{duration:.3f}",
        output_video_path
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return output_video_path

def concatenate_video_segments(segment_paths, output_master_path):
    """
    Concatenates individual page video clips into a final master video file using FFmpeg concat demuxer.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        list_file_path = f.name
        for path in segment_paths:
            safe_path = path.replace("\\", "/")
            f.write(f"file '{safe_path}'\n")

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file_path,
            "-c", "copy",
            output_master_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    finally:
        if os.path.exists(list_file_path):
            os.remove(list_file_path)

    return output_master_path
