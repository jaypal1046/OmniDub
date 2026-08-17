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

        def _cleanup_part_files():
            if os.path.exists(project_dir):
                for f in os.listdir(project_dir):
                    if f.endswith(".part"):
                        try:
                            os.remove(os.path.join(project_dir, f))
                        except Exception:
                            pass

        _cleanup_part_files()

        # JS challenge solver flags to handle YouTube n-challenge and prevent 403 Forbidden errors
        js_solver_args = ["--remote-components", "ejs:github", "--js-runtimes", "deno"]
        format_spec = "bv*[height<=1080]+ba/b[height<=1080]/bestvideo+bestaudio/best"

        # Try clean download without cookies first (avoids invalid session/cookie 403 errors)
        cmd_video = [
            "yt-dlp", "-o", video_path,
            "-f", format_spec,
            "--merge-output-format", "mp4"
        ] + js_solver_args + [source_url_or_path]

        try:
            subprocess.run(cmd_video, check=True)
        except subprocess.CalledProcessError:
            print("Primary download failed. Cleaning partial files and trying fallback options...")
            _cleanup_part_files()
            # Fallback 1: Try with cookies if cookies.txt exists and --no-continue
            fallback_cmd = [
                "yt-dlp", "-o", video_path,
                "-f", format_spec,
                "--merge-output-format", "mp4",
                "--no-continue"
            ] + js_solver_args + cookies_arg + [source_url_or_path]
            try:
                subprocess.run(fallback_cmd, check=True)
            except subprocess.CalledProcessError:
                print("Fallback 1 failed. Trying basic yt-dlp download...")
                _cleanup_part_files()
                fallback_cmd2 = ["yt-dlp", "-o", video_path, "--no-continue"] + js_solver_args + [source_url_or_path]
                subprocess.run(fallback_cmd2, check=True)

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
