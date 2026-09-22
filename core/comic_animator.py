import os
import subprocess
import tempfile
from PIL import Image

def get_audio_duration_sec(audio_path: str) -> float:
    """
    Retrieves duration of audio file in seconds using ffprobe.
    """
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        return 3.0
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        dur = float(result.stdout.strip())
        return max(1.0, dur)
    except Exception:
        return 3.0


def generate_page_tts(script_text: str, output_audio_path: str, voice: str = "en-US-ChristopherNeural") -> str:
    """
    Generates synthesized speech audio clip using edge-tts CLI.
    """
    if os.path.exists(output_audio_path) and os.path.getsize(output_audio_path) > 0:
        return output_audio_path

    os.makedirs(os.path.dirname(os.path.abspath(output_audio_path)), exist_ok=True)
    clean_text = script_text.strip()
    if not clean_text:
        clean_text = "The story continues as the tension builds."

    cmd = [
        "edge-tts",
        "--voice", voice,
        "--text", clean_text,
        "--write-media", output_audio_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return output_audio_path


def get_image_dimensions(image_path: str) -> tuple:
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception:
        return (800, 1200)


def build_ken_burns_video_segment(
    image_path: str,
    audio_path: str,
    subtitle_text: str,
    output_video_path: str,
    preset: str = "zoom_in",
    framing_mode: str = "contain",
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> str:
    """
    Renders an undistorted video segment:
    - 'contain': Fits the full image in the center with dark frosted glass background (Zero distortion).
    - 'vertical_pan' / 'scroll': For tall vertical strips, scrolls from top to bottom smoothly without stretching width.
    """
    duration = get_audio_duration_sec(audio_path)
    total_frames = int(duration * fps)
    if total_frames < 1:
        total_frames = int(3.0 * fps)
        duration = 3.0

    os.makedirs(os.path.dirname(os.path.abspath(output_video_path)), exist_ok=True)

    img_w, img_h = get_image_dimensions(image_path)
    aspect_ratio = img_h / float(max(1, img_w))

    # Auto-select scroll mode for tall vertical strips (aspect ratio > 1.35)
    is_tall_strip = (framing_mode == "vertical_pan" or aspect_ratio > 1.35)

    # Subtitle sanitization for drawtext filter
    clean_sub = (
        subtitle_text.replace("\\", "\\\\")
        .replace("'", "'\\''")
        .replace(":", "\\:")
        .replace('"', '\\"')
        .replace("%", "\\%")
    )

    if is_tall_strip:
        # -------------------------------------------------------------
        # SCROLL APPROACH FOR TALL VERTICAL IMAGES (Zero Distortion)
        # -------------------------------------------------------------
        # Foreground width is kept crisp (scaled to fit nicely in 16:9 canvas without stretching)
        # Height is allowed to exceed 1080 so it scrolls smoothly from y=0 to y=-(h-1080)
        fg_target_w = min(width - 80, int(height * (img_w / float(img_h)) * 1.5)) if aspect_ratio > 2.0 else min(width - 100, int(img_w * 1.1))
        fg_target_w = max(400, fg_target_w)
        # Ensure even width for h264 encoder
        if fg_target_w % 2 != 0:
            fg_target_w += 1

        filter_complex = (
            # 1. Dark Frosted Glass Canvas
            f"[0:v]scale=480:270:force_original_aspect_ratio=increase,crop=480:270,"
            f"boxblur=10:5,colorchannelmixer=rr=0.30:gg=0.30:bb=0.30,scale={width}:{height}[bg];"
            # 2. Crisp Undistorted Foreground scaled proportionally
            f"[0:v]scale={fg_target_w}:-2[fg];"
            # 3. Smooth Vertical Camera Scroll over exact narration duration
            f"[bg][fg]overlay=x=(W-w)/2:y='if(lte(h,{height}), ({height}-h)/2, -min(h-{height}, (h-{height})*(t/{duration:.3f})))':eval=frame[base];"
            # 4. Burned Subtitles with clear contrast
            f"[base]drawtext=text='{clean_sub}':fontcolor=white:fontsize=36:box=1:boxcolor=black@0.75:boxborderw=10:"
            f"x=(w-text_w)/2:y=h-text_h-70:fix_bounds=true[v]"
        )
    else:
        # -------------------------------------------------------------
        # CONTAIN APPROACH FOR STANDARD & SMALL PANELS (Zero Distortion)
        # -------------------------------------------------------------
        filter_complex = (
            # 1. Dark Frosted Glass Canvas
            f"[0:v]scale=480:270:force_original_aspect_ratio=increase,crop=480:270,"
            f"boxblur=10:5,colorchannelmixer=rr=0.30:gg=0.30:bb=0.30,scale={width}:{height}[bg];"
            # 2. Foreground completely contained inside canvas without cropping
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
            # 3. Centered overlay with 100% sharp aspect ratio
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
            # 4. Burned Subtitles with clear contrast
            f"[base]drawtext=text='{clean_sub}':fontcolor=white:fontsize=36:box=1:boxcolor=black@0.75:boxborderw=10:"
            f"x=(w-text_w)/2:y=h-text_h-70:fix_bounds=true[v]"
        )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "24", "-b:v", "1500k", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-t", f"{duration:.3f}",
        output_video_path
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return output_video_path


def concatenate_video_segments(segment_paths: list, output_master_path: str) -> str:
    """
    Concatenates individual page video clips into a final master video file using FFmpeg concat demuxer.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_master_path)), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        list_file_path = f.name
        for path in segment_paths:
            if os.path.exists(path) and os.path.getsize(path) > 0:
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
