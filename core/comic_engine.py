import os
import json
import tempfile
from core.manhwa_downloader import download_webtoon_url
from core.comic_pdf import load_comic_images
from core.manhwa_slicer import process_manhwa_images
from core.comic_ocr import extract_ocr_text_from_panel
from core.comic_script import generate_script_for_page
from core.comic_animator import generate_page_tts, build_ken_burns_video_segment, concatenate_video_segments

PRESETS = ["pan_down", "zoom_in", "pan_right", "zoom_out"]

def generate_comic_recap(input_path_or_url, output_mp3_or_mp4, api_key=None, voice="en-US-ChristopherNeural", 
                         width=1080, height=1920, fps=30, custom_prompt=None, mode="manhwa", enable_ocr=True):
    """
    Master pipeline:
    1. Download (if URL) or Load PDF / Images
    2. Slice long vertical Manhwa strips
    3. Perform OCR text extraction on speech bubbles
    4. Generate AI narrator script using OCR + Panel Vision
    5. Synthesize TTS audio & render Ken Burns video
    """
    project_dir = os.path.dirname(os.path.abspath(output_mp3_or_mp4))
    os.makedirs(project_dir, exist_ok=True)
    temp_dir_obj = tempfile.TemporaryDirectory()
    temp_dir = temp_dir_obj.name

    print(f"\n🚀 Starting {mode.upper()} Recap Pipeline (5-Step Engine)...", flush=True)
    print(f"Input: {input_path_or_url}", flush=True)
    print(f"Output: {output_mp3_or_mp4}", flush=True)
    print(f"Voice: {voice} | Mode: {mode} | OCR: {'Enabled' if enable_ocr else 'Disabled'}", flush=True)

    try:
        # STEP 1: DOWNLOAD IF URL
        if input_path_or_url.startswith("http://") or input_path_or_url.startswith("https://"):
            dl_dir = os.path.join(temp_dir, "downloaded_chapter")
            raw_image_paths = download_webtoon_url(input_path_or_url, dl_dir)
            if not raw_image_paths:
                raise ValueError(f"Could not download comic images from URL: {input_path_or_url}")
        else:
            # STEP 1 (Local): Load PDF pages or directory images
            raw_image_paths = load_comic_images(input_path_or_url, temp_dir)

        # STEP 2: SLICE VERTICAL MANHWA STRIPS
        image_paths = process_manhwa_images(raw_image_paths, temp_dir)
        total_pages = len(image_paths)

        if total_pages == 0:
            raise ValueError("No comic/manhwa pages found to process!")

        script_log = []
        segment_video_paths = []

        print(f"\n--- Processing {total_pages} {mode.upper()} Panels (OCR -> AI Script -> TTS -> Animation) ---", flush=True)

        for idx, img_path in enumerate(image_paths):
            page_num = idx + 1
            print(f"\n🎨 Panel [{page_num}/{total_pages}]: {os.path.basename(img_path)}", flush=True)

            # STEP 3: PERFORM OCR TEXT EXTRACTION
            ocr_text = ""
            if enable_ocr:
                ocr_text = extract_ocr_text_from_panel(img_path)

            # STEP 4: GENERATE AI RECAP SCRIPT FROM OCR + PANEL VISION
            script_data = generate_script_for_page(
                image_path=img_path,
                page_num=page_num,
                total_pages=total_pages,
                ocr_text=ocr_text,
                api_key=api_key,
                custom_prompt=custom_prompt,
                mode=mode
            )

            narrator_text = script_data.get("narrator_text", "")
            script_log.append({
                "panel": page_num,
                "image": os.path.basename(img_path),
                "ocr_text": ocr_text,
                "script": narrator_text,
                "summary": script_data.get("page_summary", "")
            })

            # STEP 5: TTS AUDIO & VIDEO ANIMATION ASSEMBLY
            audio_segment_path = os.path.join(temp_dir, f"audio_{page_num:03d}.mp3")
            generate_page_tts(narrator_text, audio_segment_path, voice=voice)

            anim_preset = PRESETS[idx % len(PRESETS)]
            video_segment_path = os.path.join(temp_dir, f"segment_{page_num:03d}.mp4")

            print(f"🎥 Rendering panel video ({anim_preset} animation)...", flush=True)
            build_ken_burns_video_segment(
                image_path=img_path,
                audio_path=audio_segment_path,
                subtitle_text=narrator_text,
                output_video_path=video_segment_path,
                preset=anim_preset,
                width=width,
                height=height,
                fps=fps
            )
            segment_video_paths.append(video_segment_path)

        # Save script JSON artifact
        script_file_path = os.path.join(project_dir, "recap_script.json")
        with open(script_file_path, "w", encoding="utf-8") as f:
            json.dump(script_log, f, indent=2, ensure_ascii=False)
        print(f"📝 Recap script saved to: {script_file_path}", flush=True)

        # Combine panel video segments
        print("\n🧩 Stitching panel clips into final recap video...", flush=True)
        concatenate_video_segments(segment_video_paths, output_mp3_or_mp4)

        print(f"\n🎉 {mode.upper()} RECAP VIDEO GENERATED SUCCESSFULLY!", flush=True)
        print(f"Output File: {output_mp3_or_mp4}", flush=True)
        return output_mp3_or_mp4
        return output_mp3_or_mp4

    finally:
        try:
            temp_dir_obj.cleanup()
        except Exception:
            pass
