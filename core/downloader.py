import os
import shutil
import subprocess

def fetch_free_proxies():
    """Fetches a list of active free public HTTP proxies for fallback downloading of geo-restricted videos."""
    import urllib.request
    urls = [
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=4000&country=all&ssl=all&anonymity=all",
        "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"
    ]
    proxies = []
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                text = resp.read().decode('utf-8', errors='ignore')
                lines = [line.strip() for line in text.splitlines() if line.strip() and ":" in line]
                proxies.extend(lines[:10])
                if proxies:
                    break
        except Exception:
            continue
    return proxies

def download_media(source_url_or_path, project_dir):
    """
    Downloads video & extracts audio into the project output folder.
    Supports YouTube, Bilibili, Douyin, TikTok, Vimeo, Direct MP4 URLs, and local files.
    Includes automated free proxy rotation fallback for geo-restricted videos.
    Returns (video_path, audio_path).
    """
    os.makedirs(project_dir, exist_ok=True)
    video_path = os.path.join(project_dir, "video.mp4")
    audio_path = os.path.join(project_dir, "audio.mp3")

    if source_url_or_path.startswith("http://") or source_url_or_path.startswith("https://"):
        # Check if video.mp4 & audio.mp3 already exist in project_dir
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            print(f"\n⏩ [1/5] Reusing existing video file at: {video_path}")
            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                print(f"[1/5] Extracting Audio from Video to: {audio_path}")
                subprocess.run([
                    "ffmpeg", "-y", "-i", video_path,
                    "-vn", "-acodec", "libmp3lame", audio_path
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return video_path, audio_path

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

        # JS challenge solver flags and anti-bot headers for Bilibili/YouTube
        js_solver_args = [
            "--remote-components", "ejs:github",
            "--js-runtimes", "deno",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "--add-header", "Referer:https://www.bilibili.com/"
        ]
        format_spec = "bv*[height<=1080]+ba/b[height<=1080]/bestvideo+bestaudio/best"

        # Try clean download first with headers
        cmd_video = [
            "yt-dlp", "-o", video_path,
            "-f", format_spec,
            "--merge-output-format", "mp4"
        ] + js_solver_args + [source_url_or_path]

        try:
            subprocess.run(cmd_video, check=True)
        except subprocess.CalledProcessError:
            print("Primary download failed. Cleaning partial files and trying fallback options with cookies...")
            _cleanup_part_files()
            # Fallback 1: Try with cookies.txt or browser cookies
            if cookies_arg:
                fallback_cmd = [
                    "yt-dlp", "-o", video_path,
                    "-f", format_spec,
                    "--merge-output-format", "mp4",
                    "--no-continue"
                ] + js_solver_args + cookies_arg + [source_url_or_path]
            else:
                fallback_cmd = [
                    "yt-dlp", "-o", video_path,
                    "-f", format_spec,
                    "--merge-output-format", "mp4",
                    "--no-continue",
                    "--cookies-from-browser", "chrome"
                ] + js_solver_args + [source_url_or_path]

            try:
                subprocess.run(fallback_cmd, check=True)
            except subprocess.CalledProcessError:
                print("\n🌐 Direct & Cookie download failed. Attempting Free Proxy Auto-Rotation for Geo-Restricted Video...")
                _cleanup_part_files()
                free_proxies = fetch_free_proxies()
                success = False
                for i, proxy in enumerate(free_proxies[:8], 1):
                    print(f"🌐 [Proxy Fallback {i}/{len(free_proxies[:8])}] Trying download via proxy: {proxy}...")
                    proxy_cmd = [
                        "yt-dlp", "-o", video_path,
                        "-f", format_spec,
                        "--merge-output-format", "mp4",
                        "--proxy", f"http://{proxy}"
                    ] + js_solver_args + [source_url_or_path]
                    try:
                        subprocess.run(proxy_cmd, check=True)
                        success = True
                        print(f"✅ Successfully downloaded geo-restricted video using proxy {proxy}!")
                        break
                    except subprocess.CalledProcessError:
                        _cleanup_part_files()
                        continue

                if not success:
                    print("Fallback 2 failed. Attempting final basic yt-dlp download...")
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
