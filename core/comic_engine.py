import os
import json
import tempfile
from core.manhwa_downloader import download_webtoon_url
from core.comic_pdf import load_comic_images
from core.manhwa_slicer import slice_strip
from core.comic_ocr import extract_ocr_text_from_panel
from core.comic_script import generate_script_for_page
from core.comic_animator import generate_page_tts, build_ken_burns_video_segment, concatenate_video_segments

PRESETS = ["zoom_in", "zoom_out", "pan_right", "pan_down"]

def generate_comic_recap(
    input_path_or_url: str,
    output_mp3_or_mp4: str,
    api_key: str = None,
    voice: str = "en-US-ChristopherNeural", 
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    custom_prompt: str = None,
    mode: str = "manhwa",
    enable_ocr: bool = True,
):
    """
    Master 5-Step AI Manhwa Recap Engine:
    1. Ingestion: Download URL or load local files/PDF.
    2. Object-Aware Slicing: Detect panel gutters + protect faces and OCR text boxes.
    3. Multimodal Vision Scripting: High-retention YouTube recap storyteller.
    4. TTS Synthesis: Synchronized Edge-TTS audio.
    5. Multi-Mode Animation: Contain with frosted glass, smart crop, or continuous vertical pan.
    """
    project_dir = os.path.dirname(os.path.abspath(output_mp3_or_mp4))
    os.makedirs(project_dir, exist_ok=True)
    temp_dir_obj = tempfile.TemporaryDirectory()
    temp_dir = temp_dir_obj.name

    print(f"\n=========================================================================", flush=True)
    print(f"🚀 Starting {mode.upper()} Recap Pipeline (5-Step Production Engine)...", flush=True)
    print(f"Input: {input_path_or_url}", flush=True)
    print(f"Output: {output_mp3_or_mp4}", flush=True)
    print(f"Resolution: {width}x{height} | Voice: {voice} | Mode: {mode}", flush=True)
    print(f"=========================================================================\n", flush=True)

    try:
        # STEP 1: LOAD OR DOWNLOAD
        if input_path_or_url.startswith("http://") or input_path_or_url.startswith("https://"):
            dl_dir = os.path.join(temp_dir, "downloaded_chapter")
            raw_image_paths = download_webtoon_url(input_path_or_url, dl_dir)
            if not raw_image_paths:
                raise ValueError(f"Could not download comic images from URL: {input_path_or_url}")
        else:
            raw_image_paths = load_comic_images(input_path_or_url, temp_dir)

        # STEP 2: OBJECT-AWARE PANEL SLICING WITH FACE/OCR PROTECTION
        sliced_dir = os.path.join(temp_dir, "manhwa_slices")
        all_panel_paths = []
        all_metadata = []

        for raw_img in raw_image_paths:
            _, meta = slice_strip(raw_img, sliced_dir)
            for m in meta:
                panel_file = os.path.join(sliced_dir, m.get("filename", f"panel_{m['index']:03d}.png"))
                all_panel_paths.append(panel_file)
                all_metadata.append(m)

        total_panels = len(all_panel_paths)
        if total_panels == 0:
            raise ValueError("No comic/manhwa pages found to process!")

        script_log = []
        segment_video_paths = []

        print(f"\n--- Processing {total_panels} {mode.upper()} Panels (Script -> TTS -> Safe Animation) ---", flush=True)

        for idx, (img_path, meta) in enumerate(zip(all_panel_paths, all_metadata)):
            page_num = idx + 1
            framing_mode = meta.get("framing_mode", "contain")
            val_score = meta.get("validation_score", 1.0)
            print(f"\n🎨 Panel [{page_num}/{total_panels}]: {os.path.basename(img_path)} | Mode: {framing_mode.upper()} (score: {val_score:.2f})", flush=True)

            # STEP 3: PERFORM OCR TEXT EXTRACTION
            ocr_text = ""
            if enable_ocr:
                ocr_text = extract_ocr_text_from_panel(img_path)

            # STEP 4: GENERATE RECAP SCRIPT
            script_data = generate_script_for_page(
                image_path=img_path,
                page_num=page_num,
                total_pages=total_panels,
                ocr_text=ocr_text,
                api_key=api_key,
                custom_prompt=custom_prompt,
                mode=mode
            )

            narrator_text = script_data.get("narrator_text", "")
            script_log.append({
                "panel": page_num,
                "image": os.path.basename(img_path),
                "framing_mode": framing_mode,
                "validation_score": val_score,
                "ocr_text": ocr_text,
                "script": narrator_text,
                "summary": script_data.get("page_summary", "")
            })

            # STEP 5: TTS AUDIO & VIDEO ANIMATION ASSEMBLY
            audio_segment_path = os.path.join(temp_dir, f"audio_{page_num:03d}.mp3")
            generate_page_tts(narrator_text, audio_segment_path, voice=voice)

            anim_preset = PRESETS[idx % len(PRESETS)]
            video_segment_path = os.path.join(temp_dir, f"segment_{page_num:03d}.mp4")

            print(f"🎥 Rendering panel video clip ({framing_mode} / {anim_preset})...", flush=True)
            build_ken_burns_video_segment(
                image_path=img_path,
                audio_path=audio_segment_path,
                subtitle_text=narrator_text,
                output_video_path=video_segment_path,
                preset=anim_preset,
                framing_mode=framing_mode,
                width=width,
                height=height,
                fps=fps
            )
            segment_video_paths.append(video_segment_path)

        # Save script JSON artifact
        script_file_path = os.path.join(project_dir, "recap_script.json")
        with open(script_file_path, "w", encoding="utf-8") as f:
            json.dump(script_log, f, indent=2, ensure_ascii=False)
        print(f"\n📝 Recap script saved to: {script_file_path}", flush=True)

        # Combine panel video segments
        print(f"🧩 Stitching {len(segment_video_paths)} panel clips into final recap video...", flush=True)
        concatenate_video_segments(segment_video_paths, output_mp3_or_mp4)

        print(f"\n🎉 {mode.upper()} RECAP VIDEO GENERATED SUCCESSFULLY!", flush=True)
        print(f"Output File: {output_mp3_or_mp4}", flush=True)
        return output_mp3_or_mp4

    finally:
        try:
            temp_dir_obj.cleanup()
        except Exception:
            pass
