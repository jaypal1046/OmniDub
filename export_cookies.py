import os
import subprocess
import sys

def export_bilibili_cookies():
    browsers = ["chrome", "edge", "firefox", "brave", "opera", "vivaldi"]
    target_cookie_file = os.path.abspath("cookies.txt")
    print(f"🔍 Searching for logged-in Bilibili browser session to export to: {target_cookie_file}\n")
    
    success = False
    for browser in browsers:
        print(f"⏳ Attempting cookie extraction from [{browser.upper()}]...")
        cmd = [
            "yt-dlp",
            "--cookies-from-browser", browser,
            "--cookies", target_cookie_file,
            "--skip-download",
            "https://www.bilibili.com"
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if os.path.exists(target_cookie_file) and os.path.getsize(target_cookie_file) > 100:
                print(f"✅ SUCCESS! Exported Bilibili cookies from {browser.upper()} to: {target_cookie_file} ({os.path.getsize(target_cookie_file)} bytes)\n")
                success = True
                break
            else:
                print(f"   (No active cookies found in {browser.upper()})")
        except Exception as e:
            print(f"   (Error checking {browser.upper()}: {e})")

    if not success:
        print("\n❌ Could not export cookies automatically.")
        print("Tip: Make sure you are logged into Bilibili in Chrome or Edge, and close the browser before running this command if database is locked.")
    return success

if __name__ == "__main__":
    export_bilibili_cookies()
