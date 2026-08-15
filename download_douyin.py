import os
import re
import urllib.request
import http.cookiejar

def download_douyin_video(url, output_path="video/douyin_video.mp4"):
    # Extract video ID from URL
    match = re.search(r"(\d{19})", url)
    if not match:
        print("Invalid Douyin URL or ID missing.")
        return False
    
    video_id = match.group(1)
    target_url = f"https://www.douyin.com/video/{video_id}"
    
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.douyin.com/'
    }

    # Request 1: Get initial cookies (__ac_nonce)
    print(f"Step 1: Fetching initial page for cookies ({target_url})...")
    req1 = urllib.request.Request(target_url, headers=headers)
    try:
        with opener.open(req1) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error fetching page: {e}")
        return False

    # Request 2: Fetch detail page with cookies stored
    print("Step 2: Parsing page data for video stream URL...")
    video_urls = re.findall(r'\"play_addr\":\{\"url_list\":\[\"(https?:[^\"]+)\"', html)
    if not video_urls:
        video_urls = re.findall(r'\"src\":\"(https?:[^\"]+)\"', html)

    if not video_urls:
        # Try API endpoint URL extraction
        api_url = f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={video_id}"
        req_api = urllib.request.Request(api_url, headers=headers)
        try:
            with opener.open(req_api) as resp_api:
                data = resp_api.read().decode('utf-8')
                urls = re.findall(r'\"play_addr\":\{\"url_list\":\[\"(https?:[^\"]+)\"', data)
                if urls:
                    video_urls = urls
        except Exception:
            pass

    if video_urls:
        mp4_url = video_urls[0].replace('\\u0026', '&').replace('\\/', '/').replace('playwm', 'play')
        print(f"Found Video MP4 Stream: {mp4_url[:60]}...")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        print(f"Step 3: Downloading MP4 video to {output_path}...")
        req_dl = urllib.request.Request(mp4_url, headers=headers)
        with opener.open(req_dl) as resp_dl, open(output_path, 'wb') as out_f:
            out_f.write(resp_dl.read())
        print(f"✅ Successfully downloaded Douyin video to: {output_path}")
        return True
    else:
        print("❌ Could not extract direct video URL. Douyin requires anti-bot signature.")
        return False

if __name__ == "__main__":
    download_douyin_video("https://www.douyin.com/jingxuan?modal_id=7664739506322509066")
