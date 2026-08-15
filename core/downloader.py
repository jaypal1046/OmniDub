import os
import shutil
import subprocess

def download_media(source_url_or_path, project_dir):
    """
    Downloads video & extracts audio into the project output folder.
    Supports YouTube, Bilibili, Douyin, TikTok, Vimeo, Direct MP4 URLs, and local files.
    Returns (video_path, audio_path).
    """
    os.makedirs(project_dir, exist_ok=True)
    video_path = os.path.join(project_dir, "video.mp4")
    audio_path = os.path.join(project_dir, "audio.mp3")

    if source_url_or_path.startswith("http://") or source_url_or_path.startswith("https://"):
        print(f"\n[1/5] Downloading Online Video to: {video_path}")
        
        # Check if cookies.txt exists in root or project_dir
        cookies_arg = []
        if os.path.exists("cookies.txt"):
            cookies_arg = ["--cookies", "cookies.txt"]
        elif os.path.exists(os.path.join(project_dir, "cookies.txt")):
            cookies_arg = ["--cookies", os.path.join(project_dir, "cookies.txt")]

        cmd_video = [
            "yt-dlp", "-o", video_path,
            "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/mp4/best"
        ] + cookies_arg + [source_url_or_path]

        cmd_audio = [
            "yt-dlp", "-o", audio_path,
            "-x", "--audio-format", "mp3"
        ] + cookies_arg + [source_url_or_path]

        try:
            subprocess.run(cmd_video, check=True)
        except subprocess.CalledProcessError:
            # Fallback for protected video sites (e.g. Douyin / protected streams)
            print("Primary download format failed. Trying fallback format selection...")
            fallback_cmd = ["yt-dlp", "-o", video_path] + cookies_arg + [source_url_or_path]
            subprocess.run(fallback_cmd, check=True)

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            print(f"[1/5] Extracting Audio from Downloaded Video to: {audio_path}")
            subprocess.run([
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "libmp3lame", audio_path
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Local video file
        if not os.path.exists(source_url_or_path):
            raise FileNotFoundError(f"Input file not found: {source_url_or_path}")
        
        print(f"\n[1/5] Copying Local Video to Project Folder...")
        shutil.copy(source_url_or_path, video_path)

        print(f"[1/5] Extracting Audio from Video to: {audio_path}")
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "libmp3lame", audio_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return video_path, audio_path
