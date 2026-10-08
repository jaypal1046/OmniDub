import os
import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from PIL import Image

@dataclass
class CharacterProfile:
    name: str
    face_embedding: Optional[List[float]] = None
    first_panel_idx: int = -1
    last_panel_idx: int = -1
    voice_id: str = "en-US-ChristopherNeural"
    aliases: List[str] = field(default_factory=list)
    description: str = ""
    confidence: float = 0.5

@dataclass
class FaceMatch:
    panel_idx: int
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    embedding: List[float]
    matched_character: Optional[str] = None
    confidence: float = 0.0

class CharacterRegistry:
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.registry_path = os.path.join(project_dir, "data", "character_registry.json")
        self.characters: Dict[str, CharacterProfile] = {}
        self.face_matches: List[FaceMatch] = []
        self._load()

    def _load(self):
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.characters = {k: CharacterProfile(**v) for k, v in data.get("characters", {}).items()}
                    self.face_matches = [FaceMatch(**fm) for fm in data.get("face_matches", [])]
            except Exception:
                pass

    def save(self):
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        data = {
            "characters": {k: asdict(v) for k, v in self.characters.items()},
            "face_matches": [asdict(fm) for fm in self.face_matches]
        }
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def add_face_match(self, panel_idx: int, bbox: Tuple[int, int, int, int], embedding: List[float]):
        self.face_matches.append(FaceMatch(panel_idx=panel_idx, bbox=bbox, embedding=embedding))

    def match_faces_to_characters(self, ocr_texts: Dict[int, str] = None):
        """
        Match face embeddings to characters using:
        1. Embedding similarity (if available)
        2. OCR name proximity (name near face bbox)
        3. Positional consistency (same face position across panels)
        """
        if not self.face_matches:
            return

        ocr_texts = ocr_texts or {}
        for fm in self.face_matches:
            if fm.matched_character:
                continue

            # Try OCR proximity first
            ocr_text = ocr_texts.get(fm.panel_idx, "")
            if ocr_text:
                # Simple heuristic: capitalized words near start of text
                words = ocr_text.split()
                for w in words[:5]:
                    if w[0].isupper() and len(w) > 2 and w not in ["The", "And", "But", "Then", "With", "From"]:
                        fm.matched_character = w
                        fm.confidence = 0.7
                        break

            # Try positional consistency: same bbox region across panels
            if not fm.matched_character:
                for other in self.face_matches:
                    if other.panel_idx == fm.panel_idx or not other.matched_character:
                        continue
                    if self._bbox_overlap_ratio(fm.bbox, other.bbox) > 0.7:
                        fm.matched_character = other.matched_character
                        fm.confidence = 0.6
                        break

    def _bbox_overlap_ratio(self, b1: Tuple, b2: Tuple) -> float:
        x1, y1, w1, h1 = b1
        x2, y2, w2, h2 = b2
        xi1, yi1 = max(x1, x2), max(y1, y2)
        xi2, yi2 = min(x1 + w1, x2 + w2), min(y1 + h1, y2 + h2)
        if xi2 <= xi1 or yi2 <= yi1:
            return 0.0
        inter = (xi2 - xi1) * (yi2 - yi1)
        area1 = w1 * h1
        area2 = w2 * h2
        return inter / min(area1, area2)

    def build_profiles(self):
        """Build CharacterProfile objects from matched faces."""
        char_faces: Dict[str, List[FaceMatch]] = {}
        for fm in self.face_matches:
            if fm.matched_character:
                char_faces.setdefault(fm.matched_character, []).append(fm)

        for name, faces in char_faces.items():
            if name not in self.characters:
                self.characters[name] = CharacterProfile(
                    name=name,
                    first_panel_idx=min(f.panel_idx for f in faces),
                    last_panel_idx=max(f.panel_idx for f in faces),
                    confidence=sum(f.confidence for f in faces) / len(faces)
                )
            else:
                prof = self.characters[name]
                prof.first_panel_idx = min(prof.first_panel_idx, min(f.panel_idx for f in faces))
                prof.last_panel_idx = max(prof.last_panel_idx, max(f.panel_idx for f in faces))
                prof.confidence = max(prof.confidence, sum(f.confidence for f in faces) / len(faces))

    def get_character_at_panel(self, panel_idx: int) -> Optional[CharacterProfile]:
        for c in self.characters.values():
            if c.first_panel_idx <= panel_idx <= c.last_panel_idx:
                return c
        return None

    def get_all_characters(self) -> List[CharacterProfile]:
        return list(self.characters.values())

    def get_context_for_prompt(self) -> str:
        """Generate character roster context for LLM prompt."""
        if not self.characters:
            return ""
        lines = ["CHARACTER ROSTER:"]
        for c in sorted(self.characters.values(), key=lambda x: x.first_panel_idx):
            lines.append(f"- {c.name}: appears panels {c.first_panel_idx}-{c.last_panel_idx}, voice: {c.voice_id}")
        return "\n".join(lines)

    def assign_voices(self, voice_map: Dict[str, str] = None):
        """Assign distinct voices to characters."""
        voices = [
            "en-US-ChristopherNeural", "en-US-AriaNeural", "en-US-GuyNeural",
            "en-US-JennyNeural", "en-US-DavisNeural", "en-US-JaneNeural",
            "en-GB-RyanNeural", "en-GB-SoniaNeural", "en-AU-WilliamNeural",
            "en-AU-NatashaNeural"
        ]
        if voice_map:
            for name, voice in voice_map.items():
                if name in self.characters:
                    self.characters[name].voice_id = voice
        else:
            for i, (name, char) in enumerate(sorted(self.characters.items())):
                char.voice_id = voices[i % len(voices)]


def create_registry_from_panels(panel_dir: str, panel_metadata: List[dict], ocr_texts: Dict[int, str]) -> CharacterRegistry:
    """
    Factory: create registry from sliced panels + metadata + OCR.
    panel_metadata: list of {"panel_idx": int, "faces": [{"bbox": [...], "embedding": [...]}], ...}
    """
    project_dir = os.path.dirname(os.path.dirname(panel_dir))
    registry = CharacterRegistry(project_dir)

    for meta in panel_metadata:
        panel_idx = meta.get("panel_idx", 0)
        for face in meta.get("faces", []):
            bbox = face.get("bbox")
            embedding = face.get("embedding")
            if bbox and embedding:
                registry.add_face_match(panel_idx, tuple(bbox), embedding)

    registry.match_faces_to_characters(ocr_texts)
    registry.build_profiles()
    registry.assign_voices()
    registry.save()
    return registry