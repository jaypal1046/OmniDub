import os
import sys
import argparse
from core.manhwa_downloader import download_webtoon_url

def main():
    parser = argparse.ArgumentParser(description="OmniDub Webtoon & Manhwa Chapter Downloader")
    parser.add_argument("url", help="Webtoon / Manhwa chapter URL (e.g., https://www.webtoons.com/... or Tappytoon URL)")
    parser.add_argument("-o", "--output-dir", help="Output directory to save downloaded chapter images", default=None)

    args = parser.parse_args()
    url = args.url.strip()

    if not args.output_dir:
        output_dir = os.path.abspath("./output/downloads/manhwa_chapter")
    else:
        output_dir = os.path.abspath(args.output_dir)

    print(f"🚀 Launching Manhwa Web Downloader...")
    print(f"URL: {url}")
    print(f"Target Directory: {output_dir}\n")

    files = download_webtoon_url(url, output_dir)

    if files:
        print(f"🎉 Success! {len(files)} chapter image files saved to: {output_dir}")
    else:
        print("❌ Download failed or no chapter images found.")
        sys.exit(1)

if __name__ == "__main__":
    main()
