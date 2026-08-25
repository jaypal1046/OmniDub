#!/usr/bin/env python3
"""
=============================================================================
         MANHWA & COMIC RECAP ENGINE - 6-STEP PIPELINE CONTROLLER
=============================================================================
Pipeline Steps:
1) Download Manhwa chapter images (or load local directory/PDF) & trim blank margins
2) Run OCR on panel images in parallel & export results to ocr_results.json / txt
3) Group panels by page & send 38 main page images to Gemini Vision for fast storytelling
4) Consolidate all panel scripts into master_script.txt & recap_script.json
5) Synthesize Edge-TTS Audio & Render 16:9 Landscape / 9:16 Video Clips IN PARALLEL
6) Stitch all synced video clips into FINAL_MANHWA_RECAP.mp4
"""

import os
import sys
import json
import shutil
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.state_manager import StateManager, extract_video_id
from core.manhwa_downloader import download_webtoon_url
from core.comic_pdf import load_comic_images
from core.manhwa_slicer import process_manhwa_images
from core.comic_ocr import extract_ocr_text_from_panel
from core.comic_script import generate_script_for_page
from core.comic_animator import generate_page_tts, build_ken_burns_video_segment, concatenate_video_segments, get_audio_duration_sec
from pydub import AudioSegment

PRESETS = ["pan_down", "zoom_in", "pan_right", "zoom_out"]

def process_manhwa_recap_project(source_input, project_name=None, voice="en-US-ChristopherNeural", 
                                 width=1920, height=1080, fps=30, force=False, mode="manhwa",
                                 enable_ocr=True, custom_prompt=None, workers=8, aspect="16:9"):
    """
    Main controller for the 6-Step Manhwa Recap Video Generator.
    Optimized: Page-Level Gemini Scripting (38 requests max) + 16:9 Landscape Layout + Parallel OCR & Video Rendering.
    """
    if aspect == "16:9":
        width, height = 1920, 1080
    elif aspect == "9:16":
        width, height = 1080, 1920

    if not project_name:
        project_name = extract_video_id(source_input)

    project_dir = os.path.abspath(os.path.join("output", project_name))
    os.makedirs(project_dir, exist_ok=True)

    state_mgr = StateManager(project_dir, source=source_input, force=force)

    print("=========================================================================")
    print(f"       🎨 MANHWA RECAP ENGINE (6-STEP PIPELINE): {project_name}")
    print(f"       Resolution: {width}x{height} ({aspect}) | Parallel Workers: {workers}")
    print(f"       Project Path: {project_dir}")
    print("=========================================================================")

    # Directories and key file paths
    images_dir = os.path.join(project_dir, "images")
    raw_images_dir = os.path.join(project_dir, "raw_pages")
    ocr_json_path = os.path.join(project_dir, "ocr_results.json")
    ocr_txt_path = os.path.join(project_dir, "ocr_results.txt")
    recap_script_json_path = os.path.join(project_dir, "recap_script.json")
    master_script_txt_path = os.path.join(project_dir, "master_script.txt")
    audio_dir = os.path.join(project_dir, "audio")
    master_audio_path = os.path.join(project_dir, "master_audio.mp3")
    final_video_path = os.path.join(project_dir, "FINAL_MANHWA_RECAP.mp4")

    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(raw_images_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # STEP 1: DOWNLOAD / LOAD MANHWA CHAPTER IMAGES & TRIM MARGINS
    # -------------------------------------------------------------------------
    print(f"\n📥 [1/6] Step 'download': Downloading & Loading Manhwa Chapter Images...")
    if state_mgr.is_step_completed("download"):
        print(f"⏩ [1/6] Step 'download' already COMPLETED (cached). Skipping.")
    else:
        if source_input.startswith("http://") or source_input.startswith("https://"):
            raw_images = download_webtoon_url(source_input, raw_images_dir)
            if not raw_images:
                raise ValueError(f"Failed to download chapter images from URL: {source_input}")
        else:
            local_src = os.path.abspath(source_input)
            if not os.path.exists(local_src):
                local_src = os.path.join(os.getcwd(), "output", source_input)
            if not os.path.exists(local_src):
                raise ValueError(f"Local input path does not exist: {source_input}")
            
            raw_images = load_comic_images(local_src, raw_images_dir)
            copied_raw = []
            for img_p in raw_images:
                if os.path.dirname(os.path.abspath(img_p)) != os.path.abspath(raw_images_dir):
                    dest = os.path.join(raw_images_dir, os.path.basename(img_p))
                    shutil.copy2(img_p, dest)
                    copied_raw.append(dest)
                else:
                    copied_raw.append(img_p)
            raw_images = copied_raw

        # Slice tall vertical strips into OpenCV viewport frames & trim blank borders
        panel_images = process_manhwa_images(raw_images, images_dir)
        state_mgr.mark_step_completed("download", result_files=panel_images)

    # Collect sliced panel images (excluding raw strips)
    panel_images = []
    sliced_subfolder = os.path.join(images_dir, "manhwa_slices")
    search_target = sliced_subfolder if (os.path.exists(sliced_subfolder) and len(os.listdir(sliced_subfolder)) > 0) else images_dir

    for root, _, files in os.walk(search_target):
        for f in sorted(files):
            if any(f.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                panel_images.append(os.path.join(root, f))

    import re
    def natural_sort_key(s):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]

    panel_images = sorted(list(set(panel_images)), key=natural_sort_key)
    total_panels = len(panel_images)

    if total_panels == 0:
        raise ValueError(f"No valid image panels found in: {search_target}")

    # Collect raw chapter pages for minimal Gemini Vision requests (38 pages max)
    raw_pages = []
    if os.path.exists(raw_images_dir):
        for f in sorted(os.listdir(raw_images_dir)):
            full_p = os.path.join(raw_images_dir, f)
            if os.path.isfile(full_p) and any(f.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                raw_pages.append(full_p)
    raw_pages = sorted(list(set(raw_pages)), key=natural_sort_key)

    print(f"🖼️ Total Sliced Panel Clips: {total_panels} | Raw Chapter Pages for AI Scripting: {len(raw_pages)}")

    # -------------------------------------------------------------------------
    # STEP 2: PARALLEL OCR TEXT EXTRACTION & EXPORT
    # -------------------------------------------------------------------------
    print(f"\n🔤 [2/6] Step 'ocr': Extracting Speech Bubble Text in Parallel ({workers} workers)...")
    ocr_results = {}
    if state_mgr.is_step_completed("ocr", [ocr_json_path, ocr_txt_path]):
        print(f"⏩ [2/6] Step 'ocr' already COMPLETED (cached). Skipping.")
        with open(ocr_json_path, "r", encoding="utf-8") as f:
            ocr_results = json.load(f)
    else:
        def process_panel_ocr(args):
            idx, img_path = args
            panel_num = idx + 1
            fname = os.path.basename(img_path)
            ocr_text = ""
            if enable_ocr:
                ocr_text = extract_ocr_text_from_panel(img_path)
            if ocr_text:
                print(f"  ⚡ [OCR {panel_num}/{total_panels}] {fname}: \"{ocr_text[:60]}\"", flush=True)
            return fname, {
                "panel": panel_num,
                "file": fname,
                "ocr_text": ocr_text
            }

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(process_panel_ocr, (idx, img_path)) for idx, img_path in enumerate(panel_images)]
            for future in as_completed(futures):
                fname, data = future.result()
                ocr_results[fname] = data

        # Write sorted OCR Export Files
        sorted_ocr = sorted(ocr_results.values(), key=lambda x: x["panel"])
        txt_lines = [f"Panel {item['panel']:03d} [{item['file']}]: {item['ocr_text'] if item['ocr_text'] else '(No Dialogue Text Detected)'}" for item in sorted_ocr]

        with open(ocr_json_path, "w", encoding="utf-8") as f:
            json.dump(ocr_results, f, indent=2, ensure_ascii=False)

        with open(ocr_txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(txt_lines))

        state_mgr.mark_step_completed("ocr", result_files=[ocr_json_path, ocr_txt_path])
        print(f"✅ OCR results exported to:\n  📄 {ocr_json_path}\n  📄 {ocr_txt_path}")

    # -------------------------------------------------------------------------
    # STEP 3: PAGE-LEVEL MINIMAL GEMINI AI SCRIPT GENERATION (38 requests max)
    # -------------------------------------------------------------------------
    print(f"\n🤖 [3/6] Step 'gemini_script': Generating Story Scripts per Page ({len(raw_pages) if raw_pages else total_panels} AI calls max)...")
    script_items = []
    if state_mgr.is_step_completed("gemini_script"):
        print(f"⏩ [3/6] Step 'gemini_script' already COMPLETED (cached). Skipping.")
        if os.path.exists(recap_script_json_path):
            with open(recap_script_json_path, "r", encoding="utf-8") as f:
                script_items = json.load(f)
    else:
        # Map panel images to their page key
        page_to_panels = defaultdict(list)
        for idx, img_path in enumerate(panel_images):
            fname = os.path.basename(img_path)
            # Find matching page prefix (e.g., page_002 in slice_page_002_001.jpg)
            match = re.search(r'(page_\d+)', fname)
            page_key = match.group(1) if match else f"page_{idx+1:03d}"
            page_to_panels[page_key].append((idx + 1, fname, img_path))

        # Generate 1 script per raw page (or page group) to minimize API calls
        page_scripts = {}
        pages_to_process = raw_pages if raw_pages else [panel_images[0]]
        total_pages_count = len(pages_to_process)

        for p_idx, page_img_path in enumerate(pages_to_process):
            p_num = p_idx + 1
            pfname = os.path.basename(page_img_path)
            match = re.search(r'(page_\d+)', pfname)
            page_key = match.group(1) if match else f"page_{p_num:03d}"

            # Combine OCR dialogue for all slices in this page
            combined_ocr = []
            for panel_num, fname, img_p in page_to_panels.get(page_key, []):
                t = ocr_results.get(fname, {}).get("ocr_text", "")
                if t:
                    combined_ocr.append(t)
            page_ocr_text = " ".join(combined_ocr)

            print(f"  [AI Script Page {p_num}/{total_pages_count}] Analyzing {pfname}...", flush=True)
            script_data = generate_script_for_page(
                image_path=page_img_path,
                page_num=p_num,
                total_pages=total_pages_count,
                ocr_text=page_ocr_text,
                custom_prompt=custom_prompt,
                mode=mode
            )

            narrator_text = script_data.get("narrator_text", "")
            page_scripts[page_key] = narrator_text

        # Distribute page scripts across sliced panel clips
        for idx, img_path in enumerate(panel_images):
            panel_num = idx + 1
            fname = os.path.basename(img_path)
            match = re.search(r'(page_\d+)', fname)
            page_key = match.group(1) if match else f"page_{panel_num:03d}"
            panel_ocr = ocr_results.get(fname, {}).get("ocr_text", "")

            script_text = page_scripts.get(page_key, f"Kim Seonwoo reacts to panel {panel_num}.")
            script_items.append({
                "panel": panel_num,
                "file": fname,
                "image_path": img_path,
                "ocr_text": panel_ocr,
                "script": script_text,
                "summary": f"Panel {panel_num} scene."
            })

        state_mgr.mark_step_completed("gemini_script")

    # -------------------------------------------------------------------------
    # STEP 4: CONSOLIDATE SCRIPTS INTO MASTER FILE
    # -------------------------------------------------------------------------
    print(f"\n📝 [4/6] Step 'consolidate_script': Consolidating Scripts into Master Files...")
    if state_mgr.is_step_completed("consolidate_script", [recap_script_json_path, master_script_txt_path]):
        print(f"⏩ [4/6] Step 'consolidate_script' already COMPLETED (cached). Skipping.")
    else:
        with open(recap_script_json_path, "w", encoding="utf-8") as f:
            json.dump(script_items, f, indent=2, ensure_ascii=False)

        master_paragraphs = [f"# 📜 MANHWA RECAP MASTER SCRIPT: {project_name}\n"]
        for item in script_items:
            master_paragraphs.append(f"--- Panel {item['panel']:03d} ({item['file']}) ---")
            if item.get("ocr_text"):
                master_paragraphs.append(f"OCR Dialogue: \"{item['ocr_text']}\"")
            master_paragraphs.append(f"Narrator Script: {item['script']}\n")

        with open(master_script_txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(master_paragraphs))

        state_mgr.mark_step_completed("consolidate_script", result_files=[recap_script_json_path, master_script_txt_path])
        print(f"✅ Consolidated Master Script saved to:\n  📄 {recap_script_json_path}\n  📄 {master_script_txt_path}")

    # -------------------------------------------------------------------------
    # STEP 5 & 6: PARALLEL TTS AUDIO + VIDEO CLIP RENDERING
    # -------------------------------------------------------------------------
    print(f"\n🎙️🎬 [5/6 & 6/6] Steps 'audio_and_video_render': Parallel TTS Audio & Video Clip Rendering ({workers} workers)...")
    if state_mgr.is_step_completed("video_render", [final_video_path, master_audio_path], current_params={"aspect": aspect, "voice": voice}):
        print(f"⏩ [5/6 & 6/6] Steps already COMPLETED (cached). Skipping.")
    else:
        def process_panel_audio_and_video(args):
            idx, item = args
            panel_num = item["panel"]
            img_path = item["image_path"]
            narrator_text = item["script"]
            segment_audio_path = os.path.join(audio_dir, f"audio_{panel_num:03d}.mp3")
            segment_video_path = os.path.join(project_dir, f"clip_{panel_num:03d}.mp4")
            anim_preset = PRESETS[idx % len(PRESETS)]

            print(f"  ⚡ [TTS & Render {panel_num}/{total_panels}] Preset: {anim_preset}...", flush=True)

            # 1. Synthesize TTS Audio clip
            generate_page_tts(narrator_text, segment_audio_path, voice=voice)

            # 2. Render Synced Video Segment with 16:9 / 9:16 Blurred Canvas
            build_ken_burns_video_segment(
                image_path=img_path,
                audio_path=segment_audio_path,
                subtitle_text=narrator_text,
                output_video_path=segment_video_path,
                preset=anim_preset,
                width=width,
                height=height,
                fps=fps
            )
            return panel_num, segment_audio_path, segment_video_path

        rendered_clips = {}
        audio_clips_map = {}

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(process_panel_audio_and_video, (idx, item)) for idx, item in enumerate(script_items)]
            for future in as_completed(futures):
                p_num, a_path, v_path = future.result()
                rendered_clips[p_num] = v_path
                audio_clips_map[p_num] = a_path

        # Order clips by panel index
        ordered_clips = [rendered_clips[item["panel"]] for item in sorted(script_items, key=lambda x: x["panel"])]

        # Combine audio clips sequentially into Master Audio Track
        combined_audio = AudioSegment.empty()
        for item in sorted(script_items, key=lambda x: x["panel"]):
            segment_audio_path = audio_clips_map[item["panel"]]
            if os.path.exists(segment_audio_path) and os.path.getsize(segment_audio_path) > 0:
                clip = AudioSegment.from_file(segment_audio_path)
                combined_audio += clip

        combined_audio.export(master_audio_path, format="mp3", bitrate="192k")

        # Concatenate Video Clips into Master Video
        print(f"🧩 Stitching {len(ordered_clips)} synced video clips into master video...")
        concatenate_video_segments(ordered_clips, final_video_path)

        # Clean up temporary clip segments
        for seg in ordered_clips:
            if os.path.exists(seg):
                try:
                    os.remove(seg)
                except Exception:
                    pass

        state_mgr.mark_step_completed("video_render", result_files=[final_video_path, master_audio_path], params={"aspect": aspect, "voice": voice})

    state_mgr.set_project_status("COMPLETED")
    print("\n=========================================================================")
    print("🎉 MANHWA RECAP PROJECT COMPLETED SUCCESSFULLY!")
    print(f"📹 Master Video: {os.path.abspath(final_video_path)}")
    print(f"🎙️ Master Audio: {os.path.abspath(master_audio_path)}")
    print(f"📝 Master Script: {os.path.abspath(master_script_txt_path)}")
    print(f"🔤 OCR Results:   {os.path.abspath(ocr_txt_path)}")
    print("=========================================================================\n")
    return final_video_path

def main():
    parser = argparse.ArgumentParser(description="OmniDub 6-Step Manhwa & Comic Recap Generator (Download -> OCR -> Page-Level Gemini -> Script -> TTS/Video Parallel Sync)")
    parser.add_argument("input", nargs="?", help="Manhwa chapter URL or path to local image directory / PDF file", default=None)
    parser.add_argument("--url", help="Manhwa chapter URL (alternative to positional argument)", default=None)
    parser.add_argument("-o", "-name", "--project-name", "--output", help="Custom project folder name under output/", default=None)
    parser.add_argument("-v", "--voice", help="Edge-TTS Narrator Voice (default: en-US-ChristopherNeural)", default="en-US-ChristopherNeural")
    parser.add_argument("--aspect", choices=["16:9", "9:16"], help="Video aspect ratio (default: 16:9 landscape)", default="16:9")
    parser.add_argument("-w", "--workers", type=int, help="Parallel processing threads (default: 8)", default=8)
    parser.add_argument("--mode", choices=["manhwa", "comic"], help="Recap style mode (default: manhwa)", default="manhwa")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR speech bubble text extraction")
    parser.add_argument("--force", action="store_true", help="Force re-run all steps bypassing state cache")
    parser.add_argument("--fps", type=int, help="Video FPS (default: 30)", default=30)
    parser.add_argument("--prompt", help="Custom prompt instructions for Gemini Vision script writer", default=None)

    args = parser.parse_args()

    source_input = args.input or args.url
    if not source_input:
        parser.error("Please provide a chapter URL or local folder path as positional argument or via --url flag.")

    try:
        process_manhwa_recap_project(
            source_input=args.input.strip(),
            project_name=args.project_name,
            voice=args.voice,
            aspect=args.aspect,
            workers=args.workers,
            fps=args.fps,
            force=args.force,
            mode=args.mode,
            enable_ocr=not args.no_ocr,
            custom_prompt=args.prompt
        )
    except Exception as e:
        print(f"\n❌ Error executing Manhwa Recap engine: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
