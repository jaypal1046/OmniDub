import os
import json
import cv2
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from PIL import Image

@dataclass
class PanelBeat:
    panel_idx: int
    beat_type: str  # hook, exposition, action, reveal, cliffhanger, breather
    confidence: float
    visual_cues: List[str]
    pacing_hint: str
    emotion: str

BEAT_TYPES = [
    "hook",           # Opening, high tension, mystery
    "exposition",     # World building, dialogue, status screens
    "action",         # Combat, movement, impact frames
    "reveal",         # Power up, transformation, identity reveal
    "cliffhanger",    # Chapter end, suspense
    "breather"        # Quiet moment, reaction shot
]

PACING_HINTS = {
    "hook": "OPENING HOOK - Start with maximum suspense and intrigue",
    "exposition": "STORY EXPOSITION - Clear, measured narration with context",
    "action": "HIGH-OCTANE ACTION - Fast, punchy, visceral language",
    "reveal": "DRAMATIC REVEAL - Build tension, emphasize the moment",
    "cliffhanger": "CLIMAX/CLIFFHANGER - Peak tension, end with suspense",
    "breather": "BREATHER MOMENT - Slower, emotional, reflective"
}

EMOTIONS = {
    "hook": "intrigue",
    "exposition": "calm",
    "action": "intensity",
    "reveal": "awe",
    "cliffhanger": "suspense",
    "breather": "emotion"
}


def analyze_panel_beat(
    image_path: str,
    panel_idx: int,
    total_panels: int,
    ocr_text: str = "",
    classification: str = "INCLUDE"
) -> PanelBeat:
    """
    Classify panel beat type using visual analysis + OCR + position.
    """
    visual_cues = []

    # Position-based priors
    position_prior = _position_prior(panel_idx, total_panels)

    # Visual analysis
    visual_score = _analyze_visual_content(image_path, visual_cues)

    # OCR analysis
    ocr_score = _analyze_ocr_content(ocr_text, visual_cues)

    # Classification influence
    class_score = _classification_score(classification)

    # Combine scores
    beat_scores = _combine_scores(position_prior, visual_score, ocr_score, class_score)

    # Select best beat
    best_beat = max(beat_scores.items(), key=lambda x: x[1])
    beat_type, confidence = best_beat

    return PanelBeat(
        panel_idx=panel_idx,
        beat_type=beat_type,
        confidence=confidence,
        visual_cues=visual_cues,
        pacing_hint=PACING_HINTS.get(beat_type, ""),
        emotion=EMOTIONS.get(beat_type, "neutral")
    )


def _position_prior(panel_idx: int, total: int) -> Dict[str, float]:
    """Position-based beat priors."""
    scores = {bt: 0.0 for bt in BEAT_TYPES}
    pct = panel_idx / max(1, total - 1)

    if panel_idx == 0:
        scores["hook"] = 0.6
    elif panel_idx == total - 1:
        scores["cliffhanger"] = 0.7
    elif pct < 0.2:
        scores["hook"] = 0.3
        scores["exposition"] = 0.3
    elif pct > 0.8:
        scores["cliffhanger"] = 0.3
        scores["action"] = 0.2
    else:
        scores["exposition"] = 0.2
        scores["action"] = 0.2
        scores["reveal"] = 0.15

    return scores


def _analyze_visual_content(image_path: str, visual_cues: List[str]) -> Dict[str, float]:
    """Analyze image for visual beat indicators."""
    scores = {bt: 0.0 for bt in BEAT_TYPES}

    try:
        img = cv2.imread(image_path)
        if img is None:
            return scores

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # 1. Motion lines / speed lines detection (high freq horizontal/vertical edges)
        sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        edge_mag = np.sqrt(sobel_x**2 + sobel_y**2)
        high_edge_ratio = float(np.mean(edge_mag > 50))

        if high_edge_ratio > 0.15:
            scores["action"] += 0.3
            visual_cues.append("motion_lines")

        # 2. Impact frames: high contrast, sharp edges, often red/orange flashes
        mean_sat = float(np.mean(hsv[:, :, 1]))
        mean_val = float(np.mean(hsv[:, :, 2]))
        contrast = float(np.std(gray))

        if contrast > 60 and mean_sat > 80:
            scores["action"] += 0.2
            scores["reveal"] += 0.15
            visual_cues.append("high_contrast")

        # 3. Color palette shifts (reveal/power-up often has distinct palette)
        # Check for dominant non-standard colors (purple, gold, bright blue)
        hue = hsv[:, :, 0]
        unique_hues = len(np.unique(hue[hue > 0]))
        if unique_hues > 50:  # Rich color palette
            scores["reveal"] += 0.15
            visual_cues.append("rich_palette")

        # 4. Face close-ups (dialogue/exposition)
        # Large central face region
        center_region = gray[h//4:3*h//4, w//4:3*w//4]
        center_contrast = float(np.std(center_region))
        if center_contrast > 40:
            scores["exposition"] += 0.15
            scores["reveal"] += 0.1
            visual_cues.append("close_up")

        # 5. Panel aspect ratio (vertical = scroll/action, horizontal = establishing)
        aspect = h / max(1, w)
        if aspect > 2.0:
            scores["action"] += 0.15
            visual_cues.append("vertical_strip")
        elif aspect < 0.7:
            scores["exposition"] += 0.1
            visual_cues.append("wide_shot")

        # 6. Brightness (dark = tension/night, bright = day/peaceful)
        if mean_val < 80:
            scores["action"] += 0.1
            scores["cliffhanger"] += 0.1
            visual_cues.append("dark")
        elif mean_val > 180:
            scores["breather"] += 0.15
            visual_cues.append("bright")

    except Exception:
        pass

    return scores


def _analyze_ocr_content(ocr_text: str, visual_cues: List[str]) -> Dict[str, float]:
    """Analyze OCR text for beat indicators."""
    scores = {bt: 0.0 for bt in BEAT_TYPES}

    if not ocr_text:
        return scores

    text = ocr_text.lower()
    word_count = len(text.split())

    # Action keywords
    action_kw = ["attack", "slash", "punch", "kick", "blast", "explosion", "boom", "crash", "smash", "strike", "power", "energy", "ki", "mana", "spell", "technique"]
    if any(kw in text for kw in action_kw):
        scores["action"] += 0.3
        visual_cues.append("action_dialogue")

    # Reveal keywords
    reveal_kw = ["level", "awaken", "evolve", "transform", "power up", "unlock", "true form", "secret", "identity", "reveal", "system", "status", "window", "stat"]
    if any(kw in text for kw in reveal_kw):
        scores["reveal"] += 0.35
        visual_cues.append("reveal_dialogue")

    # Exposition / status window
    if word_count > 30:
        scores["exposition"] += 0.25
        visual_cues.append("text_heavy")

    # Emotional / breather
    emotion_kw = ["...", "sigh", "hah", "wait", "what", "how", "why", "impossible", "unbelievable"]
    if any(kw in text for kw in emotion_kw):
        scores["breather"] += 0.15
        visual_cues.append("emotional_dialogue")

    # Question marks = intrigue/hook
    if "?" in ocr_text:
        scores["hook"] += 0.2
        visual_cues.append("question")

    # Exclamation = action/excitement
    if "!" in ocr_text:
        scores["action"] += 0.15
        visual_cues.append("exclamation")

    return scores


def _classification_score(classification: str) -> Dict[str, float]:
    """Panel classification influences beat."""
    scores = {bt: 0.0 for bt in BEAT_TYPES}

    if classification == "STORY_ONLY":
        scores["exposition"] += 0.5
    elif classification == "INCLUDE":
        scores["action"] += 0.1

    return scores


def _combine_scores(*score_dicts: Dict[str, float]) -> Dict[str, float]:
    """Combine multiple score dictionaries with weights."""
    combined = {bt: 0.0 for bt in BEAT_TYPES}
    weights = [1.0, 1.2, 1.0, 0.8]  # position, visual, ocr, classification

    for i, scores in enumerate(score_dicts):
        for bt, score in scores.items():
            combined[bt] += score * weights[i]

    # Normalize
    total = sum(combined.values())
    if total > 0:
        for bt in combined:
            combined[bt] /= total

    return combined


def group_panels_into_scenes(
    panel_beats: List[PanelBeat],
    max_panels_per_scene: int = 8
) -> List[List[int]]:
    """
    Group consecutive panels into scenes based on beat continuity.
    Scene boundaries: beat type changes significantly, or cliffhanger/hook.
    """
    if not panel_beats:
        return []

    scenes = []
    current_scene = [panel_beats[0].panel_idx]

    for i in range(1, len(panel_beats)):
        prev = panel_beats[i-1]
        curr = panel_beats[i]

        # Scene break conditions
        break_scene = False

        # Explicit scene boundaries
        if prev.beat_type in ("cliffhanger", "hook") and curr.beat_type != prev.beat_type:
            break_scene = True
        elif prev.beat_type == "reveal" and curr.beat_type in ("exposition", "breather"):
            break_scene = True
        elif curr.beat_type == "hook":  # New chapter/arc hook
            break_scene = True

        # Max panels per scene
        if len(current_scene) >= max_panels_per_scene:
            break_scene = True

        if break_scene:
            scenes.append(current_scene)
            current_scene = [curr.panel_idx]
        else:
            current_scene.append(curr.panel_idx)

    if current_scene:
        scenes.append(current_scene)

    return scenes


def get_scene_context(scenes: List[List[int]], all_beats: List[PanelBeat]) -> List[Dict]:
    """Generate context summary for each scene."""
    beat_by_idx = {b.panel_idx: b for b in all_beats}

    scene_contexts = []
    for i, scene in enumerate(scenes):
        beats_in_scene = [beat_by_idx[idx] for idx in scene if idx in beat_by_idx]

        dominant_beat = max(set(b.beat_type for b in beats_in_scene),
                           key=lambda bt: sum(1 for b in beats_in_scene if b.beat_type == bt))

        context = {
            "scene_idx": i,
            "panel_indices": scene,
            "dominant_beat": dominant_beat,
            "beat_sequence": [b.beat_type for b in beats_in_scene],
            "start_panel": scene[0],
            "end_panel": scene[-1]
        }
        scene_contexts.append(context)

    return scene_contexts