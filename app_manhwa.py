#!/usr/bin/env python3
"""
=============================================================================
         AI MANHWA RECAP ENGINE - PRODUCTION PIPELINE CONTROLLER
=============================================================================
Pipeline Steps:
1) Download Manhwa chapter images (or load local directory/PDF)
2) Object-aware panel slicing with face/OCR protection into clean scene panels
3) Parallel OCR text extraction on dialogue bubbles & export to data/ocr.json
4) YouTube Storyteller AI narration script generation (opening hook, suspense, pacing)
5) Multi-mode TTS audio & video rendering (Frosted Contain, Smart Crop, Vertical Pan)
6) Concatenate synchronized clips into FINAL_MANHWA_RECAP.mp4
"""

import os
import sys
import json
import shutil
import argparse
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydub import AudioSegment

from core.state_manager import StateManager, extract_video_id
from core.manhwa_downloader import download_webtoon_url
from core.comic_pdf import load_comic_images
from core.manhwa_slicer import process_manhwa_images
from core.comic_ocr import extract_ocr_text_from_panel
from core.comic_script import generate_script_for_page
from core.comic_animator import (
    generate_page_tts,
    build_ken_burns_video_segment,
    concatenate_video_segments,
    get_audio_duration_sec,
)

PRESETS = ["zoom_in", "zoom_out", "pan_right", "pan_down"]


def natural_sort_key(s):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]


def process_manhwa_recap_project(
    source_input: str,
    project_name: str = None,
    voice: str = "en-US-ChristopherNeural",
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    force: bool = False,
    mode: str = "manhwa",
    enable_ocr: bool = True,
    custom_prompt: str = None,
    workers: int = 8,
    aspect: str = "16:9",
    auto_approve: bool = False,
    re_review: bool = False,
):
    """
    Main controller for the AI Manhwa Recap Production Pipeline.
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
    print(f"       🎨 AI MANHWA RECAP ENGINE: {project_name}")
    print(f"       Resolution: {width}x{height} ({aspect}) | Parallel Workers: {workers}")
    print(f"       Project Path: {project_dir}")
    print("=========================================================================\n")

    # Modular Directory Structure (PDF Architecture Blueprint)
    raw_images_dir = os.path.join(project_dir, "raw_pages")
    panels_dir = os.path.join(project_dir, "images", "panels")
    data_dir = os.path.join(project_dir, "data")
    audio_dir = os.path.join(project_dir, "audio")
    clips_dir = os.path.join(project_dir, "clips")

    os.makedirs(raw_images_dir, exist_ok=True)
    os.makedirs(panels_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(clips_dir, exist_ok=True)

    ocr_json_path = os.path.join(data_dir, "ocr.json")
    ocr_txt_path = os.path.join(data_dir, "ocr_dialogue.txt")
    script_json_path = os.path.join(data_dir, "script.json")
    master_script_txt_path = os.path.join(data_dir, "master_script.txt")
    scene_map_json_path = os.path.join(data_dir, "scene_map.json")
    master_audio_path = os.path.join(project_dir, "master_audio.mp3")
    final_video_path = os.path.join(project_dir, "FINAL_MANHWA_RECAP.mp4")

    # -------------------------------------------------------------------------
    # STEP 1: DOWNLOAD / LOAD CHAPTER IMAGES
    # -------------------------------------------------------------------------
    print(f"📥 [1/6] Step 'download': Downloading & Loading Manhwa Chapter Pages...")
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

        state_mgr.mark_step_completed("download", result_files=raw_images)

    # Collect unique raw pages (filter out duplicate formats)
    raw_pages_map = {}
    if os.path.exists(raw_images_dir):
        for f in sorted(os.listdir(raw_images_dir), key=natural_sort_key):
            full_p = os.path.join(raw_images_dir, f)
            if os.path.isfile(full_p) and any(f.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]):
                base_num = os.path.splitext(f)[0]
                if base_num not in raw_pages_map or f.lower().endswith(".png"):
                    raw_pages_map[base_num] = full_p

    raw_pages = sorted(list(raw_pages_map.values()), key=natural_sort_key)
    print(f"📄 Total Chapter Pages Downloaded: {len(raw_pages)}")

    # -------------------------------------------------------------------------
    # STEP 2: OBJECT-AWARE PANEL SLICING WITH FACE/OCR PROTECTION
    # -------------------------------------------------------------------------
    print(f"\n✂️ [2/6] Step 'slicing': Extracting Clean Story Scenes via Gutter Detection...")
    if state_mgr.is_step_completed("slicing"):
        print(f"⏩ [2/6] Step 'slicing' already COMPLETED (cached). Skipping.")
    else:
        # Clear out old panel slices
        for f in os.listdir(panels_dir):
            try:
                os.remove(os.path.join(panels_dir, f))
            except Exception:
                pass

        panel_paths = process_manhwa_images(raw_pages, panels_dir)
        state_mgr.mark_step_completed("slicing", result_files=panel_paths)

    # Collect all sliced scene panels (excluding any debug images)
    panel_images = []
    for f in sorted(os.listdir(panels_dir), key=natural_sort_key):
        if any(f.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]) and not f.endswith("_debug_cuts.jpg"):
            panel_images.append(os.path.join(panels_dir, f))

    panel_images = sorted(list(set(panel_images)), key=natural_sort_key)

    # Load slicer metadata mapping
    slicer_meta_map = {}
    for f in os.listdir(panels_dir):
        if f.endswith("_metadata.json"):
            try:
                with open(os.path.join(panels_dir, f), "r", encoding="utf-8") as mf:
                    m_list = json.load(mf)
                    for m in m_list:
                        if "filename" in m:
                            slicer_meta_map[m["filename"]] = m
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # STEP 3: PARALLEL OCR TEXT EXTRACTION ON ALL RAW SLICES
    # -------------------------------------------------------------------------
    total_panels = len(panel_images)
    print(f"\n🔤 [3/6] Step 'ocr': Extracting Dialogue from Speech Bubbles ({total_panels} panels, {workers} workers)...")
    ocr_results = {}
    if state_mgr.is_step_completed("ocr", [ocr_json_path, ocr_txt_path]):
        print(f"⏩ [3/6] Step 'ocr' already COMPLETED (cached). Skipping.")
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
                print(f"  ⚡ [OCR] {fname}: \"{ocr_text[:60]}\"", flush=True)
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

        sorted_ocr = sorted(ocr_results.values(), key=lambda x: x["panel"])
        txt_lines = [f"Scene [{item['file']}]: {item['ocr_text'] if item['ocr_text'] else '(No Dialogue Text Detected)'}" for item in sorted_ocr]

        with open(ocr_json_path, "w", encoding="utf-8") as f:
            json.dump(ocr_results, f, indent=2, ensure_ascii=False)

        with open(ocr_txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(txt_lines))

        state_mgr.mark_step_completed("ocr", result_files=[ocr_json_path, ocr_txt_path])
        print(f"✅ OCR results exported to:\n  📄 {ocr_json_path}\n  📄 {ocr_txt_path}")

    # -------------------------------------------------------------------------
    # STEP 3.5: AI/CV AUTO-CLASSIFIER + VISUAL 1-CLICK WEB REVIEW DASHBOARD
    # -------------------------------------------------------------------------
    print(f"\n📋 [3.5/6] Step 'panel_review': Panel Approval & Classification...")
    manifest_json_path = os.path.join(data_dir, "panel_manifest.json")
    manifest_txt_path = os.path.join(data_dir, "panel_manifest.txt")
    from core.panel_classifier import classify_panel_content
    from core.review_server import launch_panel_review_web_ui

    if not force and not re_review and state_mgr.is_step_completed("panel_review", [manifest_json_path]):
        print(f"⏩ [3.5/6] Step 'panel_review' already COMPLETED (cached in state.json). Skipping.")
        with open(manifest_json_path, "r", encoding="utf-8") as f:
            final_manifest = json.load(f)
        active_panels = [p["image_path"] for p in final_manifest if p.get("action") == "INCLUDE"]
        story_context_only = [p["image_path"] for p in final_manifest if p.get("action") == "STORY_ONLY"]
        exc_count = len(final_manifest) - len(active_panels) - len(story_context_only)
        print(f"📋 Loaded Approved Manifest: 🎬 {len(active_panels)} Video Panels | 📖 {len(story_context_only)} Story Context | ❌ {exc_count} Excluded")
    elif auto_approve:
        # Automated classification without browser popup
        active_panels = []
        story_context_only = []
        manifest_items = []
        for idx, img_p in enumerate(panel_images):
            fname = os.path.basename(img_p)
            meta = slicer_meta_map.get(fname, {})
            ocr_text = ocr_results.get(fname, {}).get("ocr_text", "")
            h = meta.get("height", 0)
            cls_res = classify_panel_content(img_p, ocr_text=ocr_text, height_px=h)
            if cls_res.action == "INCLUDE":
                active_panels.append(img_p)
            elif cls_res.action == "STORY_ONLY":
                story_context_only.append(img_p)
            manifest_items.append({
                "panel": idx + 1,
                "file": fname,
                "image_path": img_p,
                "action": cls_res.action,
                "reason": cls_res.reason,
                "is_blank": cls_res.is_blank,
                "is_ad": cls_res.is_ad,
                "ocr_text": ocr_text,
                "height": h,
                "framing_mode": meta.get("framing_mode", "contain")
            })
        with open(manifest_json_path, "w", encoding="utf-8") as f:
            json.dump(manifest_items, f, indent=2)

        txt_lines = ["# Auto-Approved Panel Manifest\n"]
        for item in manifest_items:
            txt_lines.append(f"[{item['action']}] {item['file']}  # {item.get('reason', '')}")
        with open(manifest_txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(txt_lines))

        state_mgr.mark_step_completed("panel_review", result_files=[manifest_json_path, manifest_txt_path])
        print(f"🤖 Auto-Classification Approved & Saved to State: 🎬 {len(active_panels)} Video Panels | 📖 {len(story_context_only)} Story Context | ❌ {len(panel_images) - len(active_panels) - len(story_context_only)} Excluded")
    else:
        active_panels, story_context_only = launch_panel_review_web_ui(
            panels_dir=panels_dir,
            panel_images=panel_images,
            ocr_results=ocr_results,
            slicer_meta_map=slicer_meta_map,
            data_dir=data_dir,
        )
        state_mgr.mark_step_completed("panel_review", result_files=[manifest_json_path, manifest_txt_path])

    panel_images = active_panels
    total_panels = len(panel_images)


    # -------------------------------------------------------------------------
    # STEP 4: YOUTUBE STORYTELLER SCRIPT GENERATION (CHRONOLOGICAL STORY FLOW)
    # -------------------------------------------------------------------------
    with open(manifest_json_path, "r", encoding="utf-8") as f:
        full_manifest_items = json.load(f)

    # Filter out excluded/blank slices and preserve full chronological story flow
    story_flow_items = [item for item in full_manifest_items if item.get("action") in ("INCLUDE", "STORY_ONLY")]
    total_story_steps = len(story_flow_items)
    video_scenes_total = len([item for item in story_flow_items if item.get("action") == "INCLUDE"])

    print(f"\n🤖 [4/6] Step 'story_script': Processing Chronological Story Flow across {total_story_steps} Panels ({video_scenes_total} Video Scenes + {total_story_steps - video_scenes_total} Context Lore)...")
    script_items = []

    def get_file_md5(filepath):
        import hashlib
        if not os.path.exists(filepath):
            return ""
        hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            buf = f.read(65536)
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(65536)
        return hasher.hexdigest()

    cache_json_path = os.path.join(data_dir, "panel_script_cache.json")
    script_cache = {}

    for cache_p in (script_json_path, cache_json_path):
        if os.path.exists(cache_p):
            try:
                with open(cache_p, "r", encoding="utf-8") as f:
                    cached_list = json.load(f)
                    for c_item in cached_list:
                        c_hash = c_item.get("md5", "")
                        c_file = c_item.get("file", "")
                        if c_item.get("script"):
                            if c_hash:
                                script_cache[c_hash] = c_item
                            if c_file:
                                script_cache[c_file] = c_item
            except Exception:
                pass

    if state_mgr.is_step_completed("story_script") and os.path.exists(script_json_path):
        print(f"⏩ [4/6] Step 'story_script' already COMPLETED (cached). Skipping.")
        with open(script_json_path, "r", encoding="utf-8") as f:
            script_items = json.load(f)
    else:
        # Pre-pass: Attach chronological preceding lore to each video scene
        prepared_video_scenes = []
        pending_lore_buffer = []
        scene_counter = 0

        for story_idx, item in enumerate(story_flow_items):
            fname = item["file"]
            img_path = item["image_path"]
            action = item.get("action", "INCLUDE")
            ocr_text = ocr_results.get(fname, {}).get("ocr_text", "").strip()

            if action == "STORY_ONLY":
                if ocr_text:
                    pending_lore_buffer.append(f"[{fname} Lore]: {ocr_text}")
                    print(f"  📖 [Story Flow {story_idx+1}/{total_story_steps}] Reading lore panel {fname}: \"{ocr_text[:60]}\"", flush=True)
                else:
                    print(f"  📖 [Story Flow {story_idx+1}/{total_story_steps}] Lore panel {fname} has no dialogue.", flush=True)
            elif action == "INCLUDE":
                scene_counter += 1
                local_lore = "\n".join(pending_lore_buffer)
                pending_lore_buffer = []  # consume buffer
                prepared_video_scenes.append({
                    "story_step": story_idx + 1,
                    "scene_num": scene_counter,
                    "file": fname,
                    "image_path": img_path,
                    "ocr_text": ocr_text,
                    "preceding_lore": local_lore,
                })

        def process_scene_script(scene_info):
            story_step = scene_info["story_step"]
            scene_num = scene_info["scene_num"]
            fname = scene_info["file"]
            img_path = scene_info["image_path"]
            panel_ocr = scene_info["ocr_text"]
            preceding_lore = scene_info["preceding_lore"]
            img_md5 = get_file_md5(img_path)
            panel_meta = slicer_meta_map.get(fname, {})
            framing_mode = panel_meta.get("framing_mode", "contain")
            val_score = panel_meta.get("validation_score", 1.0)

            # Check cache
            cached = script_cache.get(img_md5) or script_cache.get(fname)
            if cached and cached.get("script"):
                print(f"⏩ [Story Flow {story_step}/{total_story_steps} | Scene {scene_num}/{video_scenes_total}] Reusing cached narration for {fname}.", flush=True)
                return {
                    "panel": scene_num,
                    "file": fname,
                    "image_path": img_path,
                    "framing_mode": framing_mode,
                    "validation_score": val_score,
                    "md5": img_md5,
                    "ocr_text": panel_ocr,
                    "script": cached["script"],
                    "summary": cached.get("summary", f"Scene {scene_num}.")
                }

            print(f"  ⚡ [Story Flow {story_step}/{total_story_steps} | Scene {scene_num}/{video_scenes_total}] Analyzing {fname} (Mode: {framing_mode})...", flush=True)
            script_data = generate_script_for_page(
                image_path=img_path,
                page_num=scene_num,
                total_pages=video_scenes_total,
                ocr_text=panel_ocr,
                custom_prompt=custom_prompt,
                mode=mode,
                chapter_context=preceding_lore
            )

            script_text = script_data.get("narrator_text", "")
            return {
                "panel": scene_num,
                "file": fname,
                "image_path": img_path,
                "framing_mode": framing_mode,
                "validation_score": val_score,
                "md5": img_md5,
                "ocr_text": panel_ocr,
                "script": script_text,
                "summary": script_data.get("page_summary", f"Scene {scene_num}.")
            }

        script_items_map = {}
        with ThreadPoolExecutor(max_workers=min(workers, 8)) as executor:
            futures = [executor.submit(process_scene_script, scene_info) for scene_info in prepared_video_scenes]
            for future in as_completed(futures):
                item = future.result()
                script_items_map[item["panel"]] = item

        script_items = [script_items_map[p_num] for p_num in sorted(script_items_map.keys())]

        # Save to data directory
        with open(script_json_path, "w", encoding="utf-8") as f:
            json.dump(script_items, f, indent=2, ensure_ascii=False)

        with open(cache_json_path, "w", encoding="utf-8") as f:
            json.dump(script_items, f, indent=2, ensure_ascii=False)



        # Consolidate readable master script
        master_paragraphs = [f"# 📜 MANHWA RECAP MASTER SCRIPT: {project_name}\n"]
        for item in script_items:
            master_paragraphs.append(f"--- Scene {item['panel']:03d} ({item['file']}) [Mode: {item.get('framing_mode', 'contain').upper()}] ---")
            if item.get("ocr_text"):
                master_paragraphs.append(f"OCR Dialogue: \"{item['ocr_text']}\"")
            master_paragraphs.append(f"Narrator Script: {item['script']}\n")

        with open(master_script_txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(master_paragraphs))

        state_mgr.mark_step_completed("story_script", result_files=[script_json_path, master_script_txt_path])
        print(f"✅ Master Script generated:\n  📄 {script_json_path}\n  📄 {master_script_txt_path}")

    # -------------------------------------------------------------------------
    # STEP 5 & 6: PARALLEL TTS AUDIO + VIDEO CLIP RENDERING
    # -------------------------------------------------------------------------
    print(f"\n🎙️🎬 [5/6 & 6/6] Steps 'video_render': Multi-Mode Video Clip Rendering ({workers} workers)...")
    if state_mgr.is_step_completed("video_render", [final_video_path, master_audio_path], current_params={"aspect": aspect, "voice": voice}):
        print(f"⏩ [5/6 & 6/6] Steps already COMPLETED (cached). Skipping.")
    else:
        def process_scene_clip(args):
            idx, item = args
            panel_num = item["panel"]
            img_path = item["image_path"]
            narrator_text = item["script"]
            framing_mode = item.get("framing_mode", "contain")
            segment_audio_path = os.path.join(audio_dir, f"audio_{panel_num:03d}.mp3")
            segment_video_path = os.path.join(clips_dir, f"clip_{panel_num:03d}.mp4")
            anim_preset = PRESETS[idx % len(PRESETS)]

            print(f"  ⚡ [Render Scene {panel_num}/{total_panels}] Mode: {framing_mode} | Preset: {anim_preset}...", flush=True)

            # 1. Synthesize TTS
            generate_page_tts(narrator_text, segment_audio_path, voice=voice)

            # 2. Render Video Clip
            build_ken_burns_video_segment(
                image_path=img_path,
                audio_path=segment_audio_path,
                subtitle_text=narrator_text,
                output_video_path=segment_video_path,
                preset=anim_preset,
                framing_mode=framing_mode,
                width=width,
                height=height,
                fps=fps
            )
            return panel_num, segment_audio_path, segment_video_path

        rendered_clips = {}
        audio_clips_map = {}

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(process_scene_clip, (idx, item)) for idx, item in enumerate(script_items)]
            for future in as_completed(futures):
                p_num, a_path, v_path = future.result()
                rendered_clips[p_num] = v_path
                audio_clips_map[p_num] = a_path

        ordered_clips = [rendered_clips[item["panel"]] for item in sorted(script_items, key=lambda x: x["panel"])]

        # Combine Audio
        combined_audio = AudioSegment.empty()
        for item in sorted(script_items, key=lambda x: x["panel"]):
            segment_audio_path = audio_clips_map[item["panel"]]
            if os.path.exists(segment_audio_path) and os.path.getsize(segment_audio_path) > 0:
                clip = AudioSegment.from_file(segment_audio_path)
                combined_audio += clip

        combined_audio.export(master_audio_path, format="mp3", bitrate="192k")

        # Save Scene Map JSON (PDF Blueprint)
        scene_map = []
        for item in sorted(script_items, key=lambda x: x["panel"]):
            scene_map.append({
                "scene_id": f"scene_{item['panel']:03d}",
                "image": item["file"],
                "framing_mode": item.get("framing_mode", "contain"),
                "narration": item["script"],
                "audio_duration_sec": get_audio_duration_sec(audio_clips_map[item["panel"]]),
            })
        with open(scene_map_json_path, "w", encoding="utf-8") as f:
            json.dump(scene_map, f, indent=2, ensure_ascii=False)

        # Concatenate Master Video
        print(f"\n🧩 Stitching {len(ordered_clips)} synchronized scene clips into FINAL MASTER VIDEO...")
        concatenate_video_segments(ordered_clips, final_video_path)

        state_mgr.mark_step_completed("video_render", result_files=[final_video_path, master_audio_path], params={"aspect": aspect, "voice": voice})

    state_mgr.set_project_status("COMPLETED")
    print("\n=========================================================================")
    print("🎉 MANHWA RECAP PROJECT COMPLETED SUCCESSFULLY!")
    print(f"📹 Master Video: {os.path.abspath(final_video_path)}")
    print(f"🎙️ Master Audio: {os.path.abspath(master_audio_path)}")
    print(f"📝 Master Script: {os.path.abspath(master_script_txt_path)}")
    print(f"🗺️ Scene Map:     {os.path.abspath(scene_map_json_path)}")
    print(f"🔤 OCR Results:   {os.path.abspath(ocr_txt_path)}")
    print("=========================================================================\n")
    return final_video_path


def main():
    parser = argparse.ArgumentParser(description="AI Manhwa & Comic Recap Production Engine")
    parser.add_argument("input", nargs="?", help="Manhwa chapter URL or path to local image directory / PDF file", default=None)
    parser.add_argument("--url", "--source", dest="source", help="Manhwa chapter URL or local folder/file path", default=None)
    parser.add_argument("-o", "-name", "--project-name", "--output", dest="project_name", help="Custom project folder name under output/", default=None)
    parser.add_argument("-v", "--voice", help="Edge-TTS Narrator Voice (default: en-US-ChristopherNeural)", default="en-US-ChristopherNeural")
    parser.add_argument("--aspect", choices=["16:9", "9:16"], help="Video aspect ratio (default: 16:9 landscape)", default="16:9")
    parser.add_argument("-w", "--workers", type=int, help="Parallel processing threads (default: 8)", default=8)
    parser.add_argument("--mode", choices=["manhwa", "comic"], help="Recap style mode (default: manhwa)", default="manhwa")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR speech bubble text extraction")
    parser.add_argument("-y", "--yes", "--auto-approve", dest="auto_approve", action="store_true", help="Auto approve panel manifest without interactive prompt")
    parser.add_argument("--review", dest="re_review", action="store_true", help="Force re-opening visual review web UI even if already cached in state")
    parser.add_argument("--force", action="store_true", help="Force re-run all steps bypassing state cache")
    parser.add_argument("--fps", type=int, help="Video FPS (default: 30)", default=30)
    parser.add_argument("--prompt", help="Custom prompt instructions for script writer", default=None)

    args = parser.parse_args()

    source_input = args.input or args.source
    if not source_input:
        parser.error("Please provide a chapter URL or local folder path as positional argument, or via --source / --url flag.")

    try:
        process_manhwa_recap_project(
            source_input=source_input.strip(),
            project_name=args.project_name,
            voice=args.voice,
            aspect=args.aspect,
            workers=args.workers,
            fps=args.fps,
            force=args.force,
            mode=args.mode,
            enable_ocr=not args.no_ocr,
            custom_prompt=args.prompt,
            auto_approve=args.auto_approve,
            re_review=args.re_review,
        )
    except Exception as e:
        print(f"\n❌ Error executing Manhwa Recap engine: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
