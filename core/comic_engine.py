import os
import json
import tempfile
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

from core.manhwa_downloader import download_webtoon_url
from core.comic_pdf import load_comic_images
from core.manhwa_slicer import slice_strip
from core.comic_ocr import extract_ocr_text_from_panel
from core.comic_script import generate_script_for_page
from core.comic_animator import (
    generate_page_tts,
    build_ken_burns_video_segment,
    concatenate_video_segments,
    build_transitions_from_beats,
    select_preset_for_beat
)
from core.panel_classifier import classify_panel_content
from core.character_registry import CharacterRegistry, create_registry_from_panels
from core.beat_analyzer import analyze_panel_beat, group_panels_into_scenes, get_scene_context
from core.narrative_engine import NarrativeEngine, analyze_and_script_chapter
from core.render_cache import get_render_cache


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
    max_workers: int = 8,
    use_narrative_engine: bool = True,
    use_cache: bool = True
):
    """
    Master AI Manhwa Recap Engine - Narrative-First Architecture:
    1. Ingestion: Download URL or load local files/PDF.
    2. Object-Aware Slicing: Detect panel gutters + protect faces and OCR text boxes.
    3. Parallel OCR + Classification + Beat Analysis.
    4. Character Registry: Track recurring faces across panels.
    5. Scene Grouping: Group panels into narrative scenes.
    6. Narrative Script Generation: Batched LLM calls per scene with continuity.
    7. Parallel TTS + Cached Rendering.
    8. Smart Transitions: Crossfade within scenes, hard cuts at boundaries.
    """
    project_dir = os.path.dirname(os.path.abspath(output_mp3_or_mp4))
    os.makedirs(project_dir, exist_ok=True)
    data_dir = os.path.join(project_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    temp_dir_obj = tempfile.TemporaryDirectory()
    temp_dir = temp_dir_obj.name

    print(f"\n=========================================================================", flush=True)
    print(f"🚀 Starting {mode.upper()} Recap Pipeline (Narrative-First Engine)...", flush=True)
    print(f"Input: {input_path_or_url}", flush=True)
    print(f"Output: {output_mp3_or_mp4}", flush=True)
    print(f"Resolution: {width}x{height} | Voice: {voice} | Workers: {max_workers}", flush=True)
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

        # Ensure panel_idx is set in metadata
        for i, meta in enumerate(all_metadata):
            meta["panel_idx"] = i
            meta["image_path"] = all_panel_paths[i]

        print(f"\n📊 Sliced into {total_panels} panels", flush=True)

        # STEP 3: PARALLEL OCR + CLASSIFICATION + BEAT ANALYSIS
        print(f"\n🔍 Parallel OCR + Classification + Beat Analysis ({max_workers} workers)...", flush=True)

        ocr_texts = {}
        panel_beats = []
        classifications = {}

        def process_panel_analysis(idx: int, img_path: str, meta: dict):
            # OCR
            ocr_text = ""
            if enable_ocr:
                ocr_text = extract_ocr_text_from_panel(img_path)

            # Classification
            classification = classify_panel_content(img_path, ocr_text)

            # Beat analysis
            beat = analyze_panel_beat(
                img_path, idx, total_panels, ocr_text, classification.action
            )

            return idx, ocr_text, classification, beat

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(process_panel_analysis, i, path, meta): i
                for i, (path, meta) in enumerate(zip(all_panel_paths, all_metadata))
            }

            for future in as_completed(futures):
                idx, ocr_text, classification, beat = future.result()
                ocr_texts[idx] = ocr_text
                classifications[idx] = classification
                panel_beats.append(beat)
                all_metadata[idx]["classification"] = classification.action
                all_metadata[idx]["ocr_text"] = ocr_text
                all_metadata[idx]["beat_type"] = beat.beat_type
                all_metadata[idx]["emotion"] = beat.emotion

        # Sort beats by panel_idx
        panel_beats.sort(key=lambda b: b.panel_idx)

        # Save OCR results
        ocr_results = {str(k): v for k, v in ocr_texts.items()}
        with open(os.path.join(data_dir, "ocr_results.json"), "w", encoding="utf-8") as f:
            json.dump(ocr_results, f, indent=2, ensure_ascii=False)

        # Save panel beats
        beats_data = []
        for b in panel_beats:
            beats_data.append({
                "panel_idx": b.panel_idx,
                "beat_type": b.beat_type,
                "confidence": b.confidence,
                "visual_cues": b.visual_cues,
                "pacing_hint": b.pacing_hint,
                "emotion": b.emotion
            })
        with open(os.path.join(data_dir, "panel_beats.json"), "w", encoding="utf-8") as f:
            json.dump(beats_data, f, indent=2, ensure_ascii=False)

        # STEP 4: CHARACTER REGISTRY
        print(f"\n👥 Building Character Registry...", flush=True)
        character_registry = create_registry_from_panels(
            sliced_dir, all_metadata, ocr_texts
        )
        print(f"   Found {len(character_registry.characters)} recurring characters", flush=True)
        for name, char in character_registry.characters.items():
            print(f"   - {name}: panels {char.first_panel_idx}-{char.last_panel_idx} (voice: {char.voice_id})", flush=True)

        # STEP 5: SCENE GROUPING
        print(f"\n🎬 Grouping Panels into Scenes...", flush=True)
        scenes = group_panels_into_scenes(panel_beats)
        scene_contexts = get_scene_context(scenes, panel_beats)
        print(f"   Created {len(scenes)} scenes", flush=True)
        for ctx in scene_contexts:
            print(f"   Scene {ctx['scene_idx']}: panels {ctx['panel_indices']} ({ctx['dominant_beat']})", flush=True)

        # STEP 6: NARRATIVE SCRIPT GENERATION (Batched per scene)
        print(f"\n✍️ Generating Narrative Scripts (Scene-Batched)...", flush=True)

        if use_narrative_engine:
            engine = NarrativeEngine(project_dir, character_registry)
            scene_scripts = engine.generate_full_chapter_script(
                all_metadata, panel_beats
            )
        else:
            # Fallback: legacy per-panel script generation
            scene_scripts = []
            for ctx in scene_contexts:
                from core.narrative_engine import SceneScript, PanelScript
                panel_scripts = []
                for panel_idx in ctx["panel_indices"]:
                    meta = all_metadata[panel_idx]
                    script_data = generate_script_for_page(
                        image_path=meta["image_path"],
                        page_num=panel_idx + 1,
                        total_pages=total_panels,
                        ocr_text=meta.get("ocr_text", ""),
                        api_key=api_key,
                        custom_prompt=custom_prompt,
                        mode=mode
                    )
                    panel_scripts.append(PanelScript(
                        panel_idx=panel_idx,
                        narrator_text=script_data.get("narrator_text", ""),
                        page_summary=script_data.get("page_summary", ""),
                        beat_type=meta.get("beat_type", "action"),
                        emotion=meta.get("emotion", "intensity")
                    ))
                scene_scripts.append(SceneScript(
                    scene_idx=ctx["scene_idx"],
                    panel_indices=ctx["panel_indices"],
                    panel_scripts=panel_scripts,
                    scene_summary=f"Scene {ctx['scene_idx']}",
                    dominant_beat=ctx["dominant_beat"]
                ))

        # Flatten panel scripts for downstream processing
        panel_scripts_by_idx = {}
        script_log = []
        for scene in scene_scripts:
            for ps in scene.panel_scripts:
                panel_scripts_by_idx[ps.panel_idx] = ps
                script_log.append({
                    "panel": ps.panel_idx + 1,
                    "scene": scene.scene_idx,
                    "image": os.path.basename(all_metadata[ps.panel_idx]["image_path"]),
                    "framing_mode": all_metadata[ps.panel_idx].get("framing_mode", "contain"),
                    "validation_score": all_metadata[ps.panel_idx].get("validation_score", 1.0),
                    "ocr_text": all_metadata[ps.panel_idx].get("ocr_text", ""),
                    "beat_type": ps.beat_type,
                    "emotion": ps.emotion,
                    "character_focus": ps.character_focus,
                    "script": ps.narrator_text,
                    "summary": ps.page_summary
                })

        # Save script JSON artifact
        script_file_path = os.path.join(project_dir, "recap_script.json")
        with open(script_file_path, "w", encoding="utf-8") as f:
            json.dump(script_log, f, indent=2, ensure_ascii=False)
        print(f"\n📝 Recap script saved to: {script_file_path}", flush=True)

        # STEP 7: PARALLEL TTS + CACHED RENDERING
        print(f"\n🎙️ Parallel TTS + Cached Rendering ({max_workers} workers)...", flush=True)

        segment_video_paths = [None] * total_panels
        audio_segment_paths = [None] * total_panels

        def process_panel_render(idx: int):
            meta = all_metadata[idx]
            ps = panel_scripts_by_idx.get(idx)
            if not ps:
                return idx, None, None

            framing_mode = meta.get("framing_mode", "contain")
            validation_score = meta.get("validation_score", 1.0)

            # Select preset based on beat type
            preset = select_preset_for_beat(ps.beat_type, framing_mode)

            # TTS
            audio_segment_path = os.path.join(temp_dir, f"audio_{idx:03d}.mp3")
            # Use character-specific voice if available
            char_voice = voice
            if ps.character_focus and ps.character_focus in character_registry.characters:
                char_voice = character_registry.characters[ps.character_focus].voice_id
            generate_page_tts(ps.narrator_text, audio_segment_path, voice=char_voice)

            # Render with cache
            video_segment_path = os.path.join(temp_dir, f"segment_{idx:03d}.mp4")
            build_ken_burns_video_segment(
                image_path=meta["image_path"],
                audio_path=audio_segment_path,
                subtitle_text=ps.narrator_text,
                output_video_path=video_segment_path,
                preset=preset,
                framing_mode=framing_mode,
                width=width,
                height=height,
                fps=fps,
                project_dir=project_dir,
                beat_type=ps.beat_type,
                use_cache=use_cache
            )

            return idx, video_segment_path, audio_segment_path

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(process_panel_render, i): i
                for i in range(total_panels)
            }

            for future in as_completed(futures):
                idx, video_path, audio_path = future.result()
                segment_video_paths[idx] = video_path
                audio_segment_paths[idx] = audio_path
                if video_path:
                    ps = panel_scripts_by_idx.get(idx)
                    print(f"   ✅ Panel [{idx+1}/{total_panels}]: {ps.beat_type if ps else '?'} / {os.path.basename(video_path)}", flush=True)

        # Filter out any failed segments
        segment_video_paths = [p for p in segment_video_paths if p]

        # STEP 8: SMART TRANSITIONS + CONCATENATION
        print(f"\n🧩 Stitching with Smart Transitions...", flush=True)

        # Build transitions from beats
        transitions = build_transitions_from_beats(panel_beats)
        crossfade_count = sum(1 for t in transitions if t.get("type") == "crossfade")
        hardcut_count = sum(1 for t in transitions if t.get("type") == "hard_cut")
        print(f"   Transitions: {crossfade_count} crossfades, {hardcut_count} hard cuts", flush=True)

        concatenate_video_segments(
            segment_video_paths,
            output_mp3_or_mp4,
            transitions=transitions
        )

        # Also combine audio for master audio track
        master_audio_path = os.path.join(project_dir, "master_audio.mp3")
        if audio_segment_paths:
            # Filter valid audio paths
            valid_audio = [p for p in audio_segment_paths if p and os.path.exists(p)]
            if valid_audio:
                # Concatenate audio
                with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
                    list_file = f.name
                    for p in valid_audio:
                        safe_p = p.replace("\\", "/")
                        f.write(f"file '{safe_p}'\n")
                try:
                    cmd = [
                        "ffmpeg", "-y",
                        "-f", "concat", "-safe", "0",
                        "-i", list_file,
                        "-c", "copy",
                        master_audio_path
                    ]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                finally:
                    if os.path.exists(list_file):
                        os.remove(list_file)
                print(f"   🎵 Master audio saved: {master_audio_path}", flush=True)

        print(f"\n🎉 {mode.upper()} RECAP VIDEO GENERATED SUCCESSFULLY!", flush=True)
        print(f"Output File: {output_mp3_or_mp4}", flush=True)

        # Cache stats
        if use_cache:
            cache = get_render_cache(project_dir)
            stats = cache.get_stats()
            print(f"📦 Render Cache: {stats['entries']} entries, {stats['total_size_mb']:.1f} MB", flush=True)

        return output_mp3_or_mp4

    finally:
        try:
            temp_dir_obj.cleanup()
        except Exception:
            pass


# Legacy simple engine (for backwards compatibility)
def generate_comic_recap_simple(
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
    """Legacy 5-step engine (original behavior)."""
    return generate_comic_recap(
        input_path_or_url, output_mp3_or_mp4,
        api_key=api_key, voice=voice, width=width, height=height,
        fps=fps, custom_prompt=custom_prompt, mode=mode,
        enable_ocr=enable_ocr, max_workers=4,
        use_narrative_engine=False, use_cache=False
    )