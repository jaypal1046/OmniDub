import os
import json
import hashlib
import base64
import requests
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from .comic_script import (
    encode_image_base64, get_mime_type, clean_json_response,
    get_active_vision_provider, call_gemini_vision
)
from .character_registry import CharacterRegistry, CharacterProfile
from .beat_analyzer import PanelBeat, group_panels_into_scenes, get_scene_context


@dataclass
class PanelScript:
    panel_idx: int
    narrator_text: str
    page_summary: str
    beat_type: str
    emotion: str
    character_focus: Optional[str] = None


@dataclass
class SceneScript:
    scene_idx: int
    panel_indices: List[int]
    panel_scripts: List[PanelScript]
    scene_summary: str
    dominant_beat: str


class NarrativeEngine:
    def __init__(self, project_dir: str, character_registry: CharacterRegistry = None):
        self.project_dir = project_dir
        self.character_registry = character_registry or CharacterRegistry(project_dir)
        self.cache_dir = os.path.join(project_dir, "data", "script_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_key(self, panel_indices: List[int], character_context: str) -> str:
        key_str = f"{panel_indices}:{character_context}"
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    def _load_cached_scene(self, cache_key: str) -> Optional[SceneScript]:
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return SceneScript(
                        scene_idx=data["scene_idx"],
                        panel_indices=data["panel_indices"],
                        panel_scripts=[PanelScript(**ps) for ps in data["panel_scripts"]],
                        scene_summary=data["scene_summary"],
                        dominant_beat=data["dominant_beat"]
                    )
            except Exception:
                pass
        return None

    def _save_cached_scene(self, cache_key: str, scene_script: SceneScript):
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.json")
        data = {
            "scene_idx": scene_script.scene_idx,
            "panel_indices": scene_script.panel_indices,
            "panel_scripts": [asdict(ps) for ps in scene_script.panel_scripts],
            "scene_summary": scene_script.scene_summary,
            "dominant_beat": scene_script.dominant_beat
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _build_scene_prompt(
        self,
        scene_panels: List[Dict],
        prior_scenes_summary: str,
        character_context: str,
        scene_context: Dict
    ) -> str:
        """Build prompt for scene-level script generation."""

        # Panel descriptions for the prompt
        panel_descs = []
        for p in scene_panels:
            ocr = p.get("ocr_text", "")
            beat = p.get("beat_type", "action")
            emotion = p.get("emotion", "intensity")
            panel_descs.append(
                f"Panel {p['panel_idx']} [{beat}/{emotion}]: "
                f"{'OCR: ' + ocr[:100] if ocr else 'Visual only'}"
            )

        panels_text = "\n".join(panel_descs)

        prompt = (
            "You are an elite YouTube Manhwa Recap Storyteller (like Duskpage / Recap King).\n\n"
            "TASK: Write narration for a SCENE (multiple panels) as a continuous story segment.\n"
            "Output per-panel narration that flows naturally across panels.\n\n"
            "STORYTELLING RULES:\n"
            "1. Do NOT translate dialogue word-for-word. Narrate the unfolding scene, actions, reveals, power escalation.\n"
            "2. Fast-paced, engaging conversational English for TTS.\n"
            "3. 1-2 sentences PER PANEL (approx 15-30 words each).\n"
            "4. Maintain character voice consistency. Use character names.\n"
            "5. No stage directions, [sound effects], or markdown.\n"
            "6. Ensure NARRATIVE CONTINUITY across panels in this scene.\n\n"
            f"{character_context}\n\n"
            f"PRIOR SCENES SUMMARY:\n{prior_scenes_summary or '(This is the first scene)'}\n\n"
            f"CURRENT SCENE (dominant beat: {scene_context['dominant_beat']}):\n{panels_text}\n\n"
            "OUTPUT FORMAT - JSON array of panel scripts:\n"
            "[\n"
            "  {\"panel_idx\": 1, \"narrator_text\": \"...\", \"page_summary\": \"...\", \"beat_type\": \"...\", \"emotion\": \"...\", \"character_focus\": \"...\"},\n"
            "  ...\n"
            "]"
        )

        return prompt

    def _call_vision_api(self, prompt: str, image_paths: List[str]) -> Optional[List[PanelScript]]:
        """Call vision API with multiple images (if supported) or first image as representative."""
        provider = get_active_vision_provider()

        # Use first panel as visual reference (APIs typically support single image)
        # For multi-image, we'd need API-specific handling
        primary_image = image_paths[0] if image_paths else None

        if not primary_image or not os.path.exists(primary_image):
            return None

        mime_type = get_mime_type(primary_image)
        base64_data = encode_image_base64(primary_image)

        if provider == "gemini":
            res = call_gemini_vision(prompt, mime_type, base64_data)
        else:
            return None

        if not res:
            return None

        # Parse response - expecting array of panel scripts
        try:
            if isinstance(res, list):
                return [PanelScript(**item) for item in res]
            elif isinstance(res, dict) and "panels" in res:
                return [PanelScript(**item) for item in res["panels"]]
            elif isinstance(res, dict):
                # Single panel response, replicate for all (fallback)
                single = PanelScript(
                    panel_idx=0,
                    narrator_text=res.get("narrator_text", ""),
                    page_summary=res.get("page_summary", ""),
                    beat_type=res.get("beat_type", "action"),
                    emotion=res.get("emotion", "intensity")
                )
                return [single]
        except Exception:
            pass

        return None

    def _heuristic_scene_script(
        self,
        scene_panels: List[Dict],
        character_context: str,
        scene_context: Dict
    ) -> List[PanelScript]:
        """Fallback heuristic when all APIs fail."""
        scripts = []
        dominant_beat = scene_context.get("dominant_beat", "action")

        beat_narratives = {
            "hook": "The story begins with a mystery that demands answers.",
            "exposition": "The world builds around our protagonist as secrets unfold.",
            "action": "Battle erupts as overwhelming power clashes in spectacular fashion.",
            "reveal": "A stunning revelation changes everything we thought we knew.",
            "cliffhanger": "The chapter ends on a precipice, leaving fate hanging in balance.",
            "breather": "A quiet moment lets the weight of recent events settle."
        }

        base_narrative = beat_narratives.get(dominant_beat, "The story continues with intensity.")

        for i, p in enumerate(scene_panels):
            panel_idx = p.get("panel_idx", i)
            ocr = p.get("ocr_text", "")

            if i == 0:
                narrator = base_narrative
            elif ocr:
                narrator = f"The tension escalates as events unfold: {ocr[:50]}..."
            else:
                narrator = f"Each moment builds toward the inevitable confrontation."

            scripts.append(PanelScript(
                panel_idx=panel_idx,
                narrator_text=narrator,
                page_summary=f"Scene panel {panel_idx}",
                beat_type=p.get("beat_type", dominant_beat),
                emotion=p.get("emotion", "intensity"),
                character_focus=p.get("character_focus")
            ))

        return scripts

    def generate_scene_script(
        self,
        scene_panels: List[Dict],
        prior_scenes_summary: str,
        scene_context: Dict
    ) -> SceneScript:
        """Generate script for a single scene (batch of panels)."""

        # Character context
        character_context = self.character_registry.get_context_for_prompt()

        # Cache key
        panel_indices = [p["panel_idx"] for p in scene_panels]
        cache_key = self._get_cache_key(panel_indices, character_context + prior_scenes_summary)

        # Check cache
        cached = self._load_cached_scene(cache_key)
        if cached:
            return cached

        # Build prompt
        prompt = self._build_scene_prompt(scene_panels, prior_scenes_summary, character_context, scene_context)

        # Get image paths
        image_paths = [p.get("image_path", "") for p in scene_panels]

        # Call vision API
        panel_scripts = self._call_vision_api(prompt, image_paths)

        if not panel_scripts:
            # Heuristic fallback
            panel_scripts = self._heuristic_scene_script(scene_panels, character_context, scene_context)

        # Ensure panel_idx alignment
        for i, ps in enumerate(panel_scripts):
            if ps.panel_idx != panel_indices[i]:
                ps.panel_idx = panel_indices[i]

        scene_script = SceneScript(
            scene_idx=scene_context["scene_idx"],
            panel_indices=panel_indices,
            panel_scripts=panel_scripts,
            scene_summary=f"Scene {scene_context['scene_idx']}: {scene_context['dominant_beat']} ({len(panel_indices)} panels)",
            dominant_beat=scene_context["dominant_beat"]
        )

        # Cache
        self._save_cached_scene(cache_key, scene_script)

        return scene_script

    def generate_full_chapter_script(
        self,
        all_panel_data: List[Dict],
        panel_beats: List[PanelBeat]
    ) -> List[SceneScript]:
        """
        Main entry: generate scripts for entire chapter.
        all_panel_data: list of dicts with panel_idx, image_path, ocr_text, beat_type, emotion, classification
        panel_beats: beat analysis for each panel
        """
        # Group into scenes
        scenes = group_panels_into_scenes(panel_beats)
        scene_contexts = get_scene_context(scenes, panel_beats)

        all_scene_scripts = []
        prior_summary = ""

        for scene_ctx in scene_contexts:
            scene_panels = [all_panel_data[idx] for idx in scene_ctx["panel_indices"]]

            scene_script = self.generate_scene_script(scene_panels, prior_summary, scene_ctx)
            all_scene_scripts.append(scene_script)

            # Update prior summary for next scene
            prior_summary = " | ".join([s.scene_summary for s in all_scene_scripts])

        return all_scene_scripts


def analyze_and_script_chapter(
    panel_dir: str,
    panel_metadata: List[dict],
    ocr_texts: Dict[int, str],
    character_registry: CharacterRegistry = None
) -> List[SceneScript]:
    """
    Full pipeline: analyze beats → group scenes → generate scene scripts.
    Returns list of SceneScript objects with per-panel narration.
    """
    # Analyze beats for each panel
    panel_beats = []
    for meta in panel_metadata:
        panel_idx = meta.get("panel_idx", 0)
        image_path = meta.get("image_path", os.path.join(panel_dir, f"panel_{panel_idx:03d}.png"))
        ocr_text = ocr_texts.get(panel_idx, "")
        classification = meta.get("classification", "INCLUDE")

        beat = PanelBeat(
            panel_idx=panel_idx,
            beat_type="action",  # Will be overwritten
            confidence=0.0,
            visual_cues=[],
            pacing_hint="",
            emotion="intensity"
        )
        # Use beat_analyzer
        from .beat_analyzer import analyze_panel_beat
        beat = analyze_panel_beat(image_path, panel_idx, len(panel_metadata), ocr_text, classification)
        panel_beats.append(beat)

    # Prepare panel data for narrative engine
    all_panel_data = []
    for meta in panel_metadata:
        panel_idx = meta.get("panel_idx", 0)
        all_panel_data.append({
            "panel_idx": panel_idx,
            "image_path": meta.get("image_path", os.path.join(panel_dir, f"panel_{panel_idx:03d}.png")),
            "ocr_text": ocr_texts.get(panel_idx, ""),
            "beat_type": next((b.beat_type for b in panel_beats if b.panel_idx == panel_idx), "action"),
            "emotion": next((b.emotion for b in panel_beats if b.panel_idx == panel_idx), "intensity"),
            "classification": meta.get("classification", "INCLUDE")
        })

    # Generate scripts
    engine = NarrativeEngine(os.path.dirname(os.path.dirname(panel_dir)), character_registry)
    scene_scripts = engine.generate_full_chapter_script(all_panel_data, panel_beats)

    return scene_scripts
