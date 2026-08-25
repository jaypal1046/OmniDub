import os
import sys
import argparse
from app_manhwa import process_manhwa_recap_project

def main():
    parser = argparse.ArgumentParser(description="OmniDub 6-Step Manhwa & Comic Recap Generator (Download -> OCR -> Gemini -> Script -> TTS -> Video Sync)")
    parser.add_argument("input", help="URL or Path to PDF file / directory of Manhwa/Comic images")
    parser.add_argument("-name", "--project-name", help="Custom project folder name under output/", default=None)
    parser.add_argument("-o", "--output", help="Output MP4 file path", default=None)
    parser.add_argument("--mode", choices=["manhwa", "comic"], help="Recap style mode (default: manhwa)", default="manhwa")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR text extraction step")
    parser.add_argument("--voice", help="Edge-TTS voice ID (default: en-US-ChristopherNeural)", default="en-US-ChristopherNeural")
    parser.add_argument("--force", action="store_true", help="Force re-run all steps bypassing state cache")
    parser.add_argument("--width", type=int, help="Video width (default: 1080)", default=1080)
    parser.add_argument("--height", type=int, help="Video height (default: 1920)", default=1920)
    parser.add_argument("--fps", type=int, help="Video FPS (default: 30)", default=30)
    parser.add_argument("--prompt", help="Custom prompt style instructions for Gemini script writer", default=None)

    args = parser.parse_args()

    input_str = args.input.strip()

    try:
        process_manhwa_recap_project(
            source_input=input_str,
            project_name=args.project_name,
            voice=args.voice,
            width=args.width,
            height=args.height,
            fps=args.fps,
            force=args.force,
            mode=args.mode,
            enable_ocr=not args.no_ocr,
            custom_prompt=args.prompt
        )
    except Exception as e:
        print(f"❌ Failed to generate {args.mode} recap: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
