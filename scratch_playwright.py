import time
from playwright.sync_api import sync_playwright

url = "https://kingofshojo.cc/manga/vy5evrpl60cfvyzi/chapter-1/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 1000},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3000)

    print("Initial height:", page.evaluate("document.body.scrollHeight"))

    # Scroll down thoroughly
    for i in range(15):
        page.evaluate("window.scrollBy(0, 2000)")
        page.wait_for_timeout(600)

    print("Scrolled height:", page.evaluate("document.body.scrollHeight"))

    imgs = page.query_selector_all("img")
    print("Found img elements in Playwright:", len(imgs))

    urls = []
    for i, img in enumerate(imgs):
        src = img.get_attribute("src") or ""
        srcset = img.get_attribute("srcset") or ""
        alt = img.get_attribute("alt") or ""
        print(f"Img #{i+1}: src={src[:60]} | srcset={srcset[:60]} | alt={alt}")

    browser.close()
