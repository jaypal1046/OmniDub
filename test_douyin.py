import urllib.request
import re
import os

def fetch_douyin_mp4(modal_id="7664739506322509066", output_path="video/douyin_video.mp4"):
    url = f"https://www.douyin.com/video/{modal_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.douyin.com/'
    }
    
    print(f"Fetching webpage: {url}")
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode('utf-8', errors='ignore')

    video_urls = re.findall(r'\"play_addr\":\{\"url_list\":\[\"(https?:[^\"]+)\"', html)
    if not video_urls:
        # Fallback regex for video src
        video_urls = re.findall(r'\"src\":\"(https?:[^\"]+)\"', html)

    if video_urls:
        direct_url = video_urls[0].replace('\\u0026', '&').replace('\\/', '/')
        print(f"Found MP4 URL: {direct_url}")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        print(f"Downloading to: {output_path}")
        dl_req = urllib.request.Request(direct_url, headers=headers)
        with urllib.request.urlopen(dl_req) as dl_resp, open(output_path, 'wb') as out_f:
            out_f.write(dl_resp.read())
        print("Download complete!")
    else:
        print("Could not find direct video URL in page HTML.")

if __name__ == "__main__":
    fetch_douyin_mp4()
