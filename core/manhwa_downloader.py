import os
import re
import time
import requests
from bs4 import BeautifulSoup

def download_with_playwright(url, output_dir):
    """
    Uses Playwright headless browser to render any dynamic Webtoon / Manhwa website,
    scroll down to lazy-load all vertical panels, and save all chapter images to disk.
    """
    os.makedirs(output_dir, exist_ok=True)
    print(f"🌐 Launching headless browser for Manhwa chapter URL: {url}")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("⚠️ Playwright not found. Falling back to HTTP requests scraper...")
        return []

    downloaded_files = []

    try:
        with sync_playwright() as p:
            # Launch Chromium browser with desktop viewport and anti-bot headers
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 2000},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            print("🌐 Navigating to website...")
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)

            # Auto-scroll down the page to trigger lazy-loaded images
            print("📜 Scrolling vertical Manhwa strip to load all images...")
            for _ in range(12):
                page.evaluate("window.scrollBy(0, 1500)")
                page.wait_for_timeout(800)

            # Scroll back up slightly or wait for network idle
            page.wait_for_timeout(2000)

            # Extract image element URLs using smart manhwa panel filtering
            img_elements = page.query_selector_all("img")
            img_urls = []

            for img in img_elements:
                src = (
                    img.get_attribute("src") or 
                    img.get_attribute("data-src") or 
                    img.get_attribute("data-url") or 
                    img.get_attribute("data-original") or ""
                )
                if not src:
                    continue

                alt = img.get_attribute("alt") or ""
                data_page_index = img.get_attribute("data-page-index") or img.get_attribute("data-page") or ""

                if not any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    continue

                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = page.url.split("/")[0] + "//" + page.url.split("/")[2] + src

                # 1. Exclude UI elements, header, footer, comments section, avatars, widgets
                is_excluded = img.evaluate("""el => {
                    const badContainer = el.closest('#comments, .comments, [class*="comment"], [id*="comment"], [class*="avatar"], [class*="disqus"], #disqus_thread, footer, header, nav, .sidebar, #sidebar, [class*="recommend"], [class*="related"], [class*="widget"], [class*="profile"]');
                    if (badContainer) return true;
                    // Check bounding dimensions if available
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.width < 100 && rect.height > 0 && rect.height < 100) return true;
                    return false;
                }""")

                if is_excluded:
                    continue

                if any(bad in src.lower() for bad in ["logo", "avatar", "icon", "banner", "favicon", "ad-", "button", "badge", "emotes", "sticker", "discord", "patreon"]):
                    continue

                # 2. Check positive indicators for Manhwa panel images
                has_parent_datapage = img.evaluate("""el => el.closest('[data-page], #readerarea, .rdcontainer, .reading-content, .chapter-content, [class*="reader"], [id*="reader"]') !== null""")
                
                is_valid_panel = (
                    has_parent_datapage or
                    bool(data_page_index) or
                    ("page" in alt.lower() and ("chapter" in alt.lower() or "manhwa" in alt.lower() or "comic" in alt.lower())) or
                    any(k in src.lower() for k in ["/chapters/", "/chapter/", "/pages/", "/page/", "/uploads/manga/", "/uploads/series/"])
                )

                if is_valid_panel:
                    img_urls.append(src)

            # Deduplicate URLs
            unique_urls = []
            for u in img_urls:
                if u not in unique_urls:
                    unique_urls.append(u)

            print(f"📸 Smart identified {len(unique_urls)} high-resolution panel image URLs on page.")

            # Download extracted image files
            for i, img_url in enumerate(unique_urls):
                ext = ".jpg"
                if ".png" in img_url.lower():
                    ext = ".png"
                elif ".webp" in img_url.lower():
                    ext = ".webp"

                filename = f"page_{i+1:03d}{ext}"
                filepath = os.path.join(output_dir, filename)

                try:
                    # Download image using browser context to retain cookies/headers
                    response = page.request.get(img_url)
                    if response.ok and len(response.body()) > 5000:
                        with open(filepath, "wb") as f:
                            f.write(response.body())
                        downloaded_files.append(filepath)
                except Exception as e:
                    print(f"⚠️ Failed downloading image {i+1}: {e}")

            browser.close()

    except Exception as e:
        print(f"❌ Playwright download error: {e}")

    return downloaded_files

def download_with_requests(url, output_dir):
    """
    Fallback HTTP scraper using Requests + BeautifulSoup for static Manhwa sites.
    """
    os.makedirs(output_dir, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": url
    }

    downloaded_files = []
    try:
        response = requests.get(url, headers=headers, timeout=25)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        img_urls = []

        # Find main reader container if present
        reader_container = (
            soup.find(id="readerarea") or 
            soup.find(class_=re.compile(r"reader|rdcontainer|chapter-content|reading-content", re.I)) or 
            soup
        )

        for img in reader_container.find_all("img"):
            src = img.get("data-src") or img.get("data-url") or img.get("src") or ""
            if not src:
                continue

            alt = img.get("alt", "")
            data_page = img.get("data-page") or img.get("data-page-index") or ""

            if not any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                continue

            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = url.split("/")[0] + "//" + url.split("/")[2] + src

            # Exclude bad non-panel URLs
            if any(bad in src.lower() for bad in ["logo", "avatar", "icon", "banner", "favicon", "ad-", "button", "badge", "emotes", "disqus", "discord"]):
                continue

            # Check if parent is comment section
            parent_classes = " ".join([c for c in (img.parent.get("class") or [])]) if img.parent else ""
            if any(c in parent_classes.lower() for c in ["comment", "avatar", "profile", "sidebar", "footer", "header"]):
                continue

            if (
                data_page or
                reader_container != soup or
                ("page" in alt.lower()) or
                any(k in src.lower() for k in ["/chapters/", "/chapter/", "/pages/", "/page/", "/uploads/manga/"])
            ):
                img_urls.append(src)

        unique_urls = list(dict.fromkeys(img_urls))

        for i, img_url in enumerate(unique_urls):
            ext = ".jpg"
            if ".png" in img_url.lower():
                ext = ".png"
            elif ".webp" in img_url.lower():
                ext = ".webp"

            filepath = os.path.join(output_dir, f"page_{i+1:03d}{ext}")
            try:
                img_res = requests.get(img_url, headers=headers, timeout=20)
                if img_res.status_code == 200 and len(img_res.content) > 5000:
                    with open(filepath, "wb") as f:
                        f.write(img_res.content)
                    downloaded_files.append(filepath)
            except Exception:
                pass

    except Exception:
        pass

    return downloaded_files

def download_webtoon_url(url, output_dir):
    """
    Main Downloader entrypoint for any Webtoon / Manhwa chapter URL.
    Tries Playwright headless browser first for dynamic rendering,
    falling back to HTTP requests if needed.
    """
    os.makedirs(output_dir, exist_ok=True)
    print(f"\n📥 Step 1: Downloading Manhwa chapter from website: {url}")
    
    # Try Playwright first for full JavaScript lazy-loading support
    files = download_with_playwright(url, output_dir)
    
    # Fallback to requests if Playwright produced no images
    if not files:
        print("⚠️ Retrying download using fallback HTTP scraper...")
        files = download_with_requests(url, output_dir)

    if files:
        print(f"✅ Download complete! Saved {len(files)} chapter images to: {output_dir}\n")
    else:
        print(f"❌ Failed to download images from URL: {url}\n")

    return files
