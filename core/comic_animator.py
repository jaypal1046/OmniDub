import os
import math
import subprocess
import tempfile
import textwrap
from PIL import Image
from typing import List, Optional
from .beat_analyzer import PanelBeat
from .render_cache import get_render_cache


def get_audio_duration_sec(audio_path: str) -> float:
    """
    Retrieves duration of audio file in seconds using ffprobe.
    """
    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        raise ValueError(f"Audio file is missing or empty: {audio_path}")
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        dur = float(result.stdout.strip())
        if not math.isfinite(dur) or dur <= 0:
            raise ValueError("Invalid audio duration")
        return max(1.0, dur)
    except Exception as exc:
        raise RuntimeError(f"Could not determine audio duration: {audio_path}") from exc


def select_preset_for_beat(beat_type: str, framing_mode: str) -> str:
    """
    Select animation preset based on beat type and framing mode.
    Replaces round-robin with content-aware selection.
    """
    # Beat-type driven preset selection
    beat_presets = {
        "hook": "zoom_in",
        "exposition": "contain",
        "action": "zoom_in",
        "reveal": "zoom_out",
        "cliffhanger": "zoom_in",
        "breather": "pan_right"
    }

    # Framing mode constraints
    if framing_mode == "vertical_pan":
        return "vertical_pan"  # Only valid preset for tall strips
    elif framing_mode == "crop":
        # Crop mode works well with zoom/pan
        return beat_presets.get(beat_type, "zoom_in")
    else:  # contain
        return beat_presets.get(beat_type, "contain")


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
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                wav_path = os.path.join(temp_dir, "narration.wav")
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                stream = win32com.client.Dispatch("SAPI.SpFileStream")
                stream.Open(wav_path, 3, False)
                try:
                    speaker.AudioOutputStream = stream
                    speaker.Speak(clean_text)
                finally:
                    stream.Close()
                subprocess.run(["ffmpeg", "-y", "-i", wav_path, output_audio_path],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        finally:
            pythoncom.CoUninitialize()
    return output_audio_path


def get_image_dimensions(image_path: str) -> tuple:
    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception:
        return (800, 1200)


def _build_filter_complex(
    image_path: str,
    audio_path: str,
    subtitle_text: str,
    preset: str,
    framing_mode: str,
    width: int,
    height: int,
    duration: float
) -> str:
    """Build FFmpeg filter complex for Ken Burns animation."""
    img_w, img_h = get_image_dimensions(image_path)
    aspect_ratio = img_h / float(max(1, img_w))

    # Auto-select scroll mode for tall vertical strips (aspect ratio > 1.35)
    is_tall_strip = (framing_mode == "vertical_pan" or aspect_ratio > 1.35)

    if is_tall_strip:
        # SCROLL APPROACH FOR TALL VERTICAL IMAGES (Zero Distortion)
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
            f"[bg][fg]overlay=x=(W-w)/2:y='if(lte(h,{height}), ({height}-h)/2, -min(h-{height}, (h-{height})*(t/{duration:.3f})))':eval=frame[base]"
        )
    else:
        # CONTAIN APPROACH FOR STANDARD & SMALL PANELS (Zero Distortion)
        # Apply preset-based animation for contain mode
        if preset == "zoom_in":
            fg_scale = f"scale={width}:{height}:force_original_aspect_ratio=decrease,zoompan=z='if(lte(zoom,1.0),1.0,min(zoom+0.001,1.3))':d=1:x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':s={width}x{height}"
        elif preset == "zoom_out":
            fg_scale = f"scale={width}:{height}:force_original_aspect_ratio=decrease,zoompan=z='if(lte(zoom,1.3),1.3,max(zoom-0.001,1.0))':d=1:x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':s={width}x{height}"
        elif preset == "pan_right":
            fg_scale = f"scale={width}:{height}:force_original_aspect_ratio=decrease,zoompan=z='1.2':x='(iw-iw/zoom)/2+min(on*{width}*0.1/{max(1, duration * 30):.1f},{width}*0.1)':y='(ih-ih/zoom)/2':s={width}x{height}"
        elif preset == "pan_left":
            fg_scale = f"scale={width}:{height}:force_original_aspect_ratio=decrease,zoompan=z='1.2':x='(iw-iw/zoom)/2-min(on*{width}*0.1/{max(1, duration * 30):.1f},{width}*0.1)':y='(ih-ih/zoom)/2':s={width}x{height}"
        else:  # contain (static)
            fg_scale = f"scale={width}:{height}:force_original_aspect_ratio=decrease"

        filter_complex = (
            # 1. Dark Frosted Glass Canvas
            f"[0:v]scale=480:270:force_original_aspect_ratio=increase,crop=480:270,"
            f"boxblur=10:5,colorchannelmixer=rr=0.30:gg=0.30:bb=0.30,scale={width}:{height}[bg];"
            # 2. Foreground with preset animation
            f"[0:v]{fg_scale}[fg];"
            # 3. Centered overlay
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base]"
        )

    lines = textwrap.wrap(subtitle_text, width=55, break_long_words=False) or [""]
    for index, line in enumerate(lines):
        clean = (line.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:")
                 .replace('"', '\\"').replace("%", "\\%"))
        source = "base" if index == 0 else f"sub{index}"
        target = "v" if index == len(lines) - 1 else f"sub{index + 1}"
        offset = 70 + (len(lines) - 1 - index) * 52
        filter_complex += (f";[{source}]drawtext=text='{clean}':fontcolor=white:fontsize=36:"
                           f"box=1:boxcolor=black@0.75:boxborderw=10:x=(w-text_w)/2:"
                           f"y=h-text_h-{offset}:fix_bounds=true[{target}]")
    return filter_complex


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
    project_dir: str = None,
    beat_type: str = "action",
    use_cache: bool = True
) -> str:
    """
    Renders an undistorted video segment:
    - 'contain': Fits the full image in the center with dark frosted glass background (Zero distortion).
    - 'vertical_pan' / 'scroll': For tall vertical strips, scrolls from top to bottom smoothly without stretching width.
    - 'crop': Validated safe crop with Ken Burns presets.

    Supports content-aware preset selection via beat_type.
    Supports render caching via project_dir.
    """
    duration = get_audio_duration_sec(audio_path)
    total_frames = int(duration * fps)
    if total_frames < 1:
        total_frames = int(3.0 * fps)
        duration = 3.0

    os.makedirs(os.path.dirname(os.path.abspath(output_video_path)), exist_ok=True)

    # Check cache first
    if use_cache and project_dir:
        cache = get_render_cache(project_dir)
        cached_path = cache.get(
            image_path=image_path,
            audio_path=audio_path,
            preset=preset,
            framing_mode=framing_mode,
            width=width,
            height=height,
            fps=fps,
            subtitle_text=subtitle_text
        )
        if cached_path:
            import shutil
            shutil.copy2(cached_path, output_video_path)
            return output_video_path

    # Auto-select preset if not explicitly set and beat_type provided
    if preset == "zoom_in" and beat_type != "action":
        preset = select_preset_for_beat(beat_type, framing_mode)

    filter_complex = _build_filter_complex(
        image_path, audio_path, subtitle_text,
        preset, framing_mode, width, height, duration
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

    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        raise RuntimeError(f"FFmpeg failed for {image_path}: {result.stderr[-1200:]}")

    # Store in cache
    if use_cache and project_dir:
        cache = get_render_cache(project_dir)
        cache.put(
            image_path=image_path,
            audio_path=audio_path,
            preset=preset,
            framing_mode=framing_mode,
            output_path=output_video_path,
            width=width,
            height=height,
            fps=fps,
            subtitle_text=subtitle_text,
            duration=duration
        )

    return output_video_path


def concatenate_video_segments(
    segment_paths: list,
    output_master_path: str,
    transitions: List[dict] = None
) -> str:
    """
    Concatenates individual page video clips into a final master video file.

    Args:
        segment_paths: List of video segment paths
        output_master_path: Output path for final video
        transitions: Optional list of transition dicts per segment boundary:
            {"type": "crossfade", "duration": 0.5} or {"type": "hard_cut"}
            Length should be len(segment_paths) - 1
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_master_path)), exist_ok=True)

    if not transitions:
        # Simple concat (existing behavior)
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

    # With transitions - need filter_complex
    # This is more complex, using concat with crossfade filter
    inputs = []
    filter_parts = []

    for i, path in enumerate(segment_paths):
        if os.path.exists(path) and os.path.getsize(path) > 0:
            inputs.extend(["-i", path])
            filter_parts.append(f"[{i}:v][{i}:a]")

    if len(filter_parts) < 2:
        # Fallback to simple concat
        return concatenate_video_segments(segment_paths, output_master_path)

    # Build crossfade chain
    # For simplicity, use xfade filter between consecutive segments
    # Note: xfade requires re-encode
    prev_label = "0v"
    prev_audio = "0a"

    for i in range(1, len(filter_parts)):
        trans = transitions[i-1] if i-1 < len(transitions) else {"type": "hard_cut"}

        if trans.get("type") == "crossfade" and i < len(filter_parts):
            dur = trans.get("duration", 0.5)
            out_label = f"v{i}"
            out_audio = f"a{i}"
            filter_parts.append(
                f"[{prev_label}][{i}:v]xfade=transition=fade:duration={dur}:offset={0}[{out_label}];"
                f"[{prev_audio}][{i}:a]acrossfade=d={dur}[{out_audio}]"
            )
            prev_label = out_label
            prev_audio = out_audio
        else:
            # Hard cut - just concat
            filter_parts.append(f"[{prev_label}][{i}:v]concat=n=2:v=1:a=0[v{i}];")
            filter_parts.append(f"[{prev_audio}][{i}:a]concat=n=2:v=0:a=1[a{i}]")
            prev_label = f"v{i}"
            prev_audio = f"a{i}"

    filter_complex = "".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{prev_label}]", "-map", f"[{prev_audio}]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "24",
        "-c:a", "aac", "-b:a", "128k",
        output_master_path
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return output_master_path


def build_transitions_from_beats(
    panel_beats: List[PanelBeat],
    default_crossfade_dur: float = 0.4
) -> List[dict]:
    """
    Generate transition list from panel beats.
    Crossfade within scenes, hard cut at scene boundaries.
    """
    if not panel_beats:
        return []

    transitions = []
    for i in range(len(panel_beats) - 1):
        curr = panel_beats[i]
        next_beat = panel_beats[i + 1]

        # Scene boundary detection
        is_boundary = False
        if curr.beat_type in ("cliffhanger", "hook") and next_beat.beat_type != curr.beat_type:
            is_boundary = True
        elif curr.beat_type == "reveal" and next_beat.beat_type in ("exposition", "breather"):
            is_boundary = True

        if is_boundary:
            transitions.append({"type": "hard_cut"})
        else:
            transitions.append({"type": "crossfade", "duration": default_crossfade_dur})

    return transitions
