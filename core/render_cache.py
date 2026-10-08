import os
import json
import hashlib
import subprocess
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class RenderCacheEntry:
    cache_key: str
    input_hash: str
    output_path: str
    params: Dict[str, Any]
    duration: float
    created_at: float
    file_size: int


class RenderCache:
    """
    Content-addressable render cache for video segments.
    Keys are hashes of input image + audio + render parameters.
    """

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        self.index_path = os.path.join(cache_dir, "cache_index.json")
        self.entries: Dict[str, RenderCacheEntry] = {}
        os.makedirs(cache_dir, exist_ok=True)
        self._load_index()

    def _load_index(self):
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.entries = {k: RenderCacheEntry(**v) for k, v in data.items()}
            except Exception:
                self.entries = {}

    def _save_index(self):
        data = {k: asdict(v) for k, v in self.entries.items()}
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _compute_input_hash(self, image_path: str, audio_path: str) -> str:
        """Compute hash of input files."""
        hasher = hashlib.sha256()

        # Hash image file
        if os.path.exists(image_path):
            with open(image_path, "rb") as f:
                # Read first 64KB + last 64KB for large files
                size = os.path.getsize(image_path)
                if size <= 131072:
                    hasher.update(f.read())
                else:
                    hasher.update(f.read(65536))
                    f.seek(-65536, 2)
                    hasher.update(f.read(65536))

        # Hash audio file
        if os.path.exists(audio_path):
            with open(audio_path, "rb") as f:
                size = os.path.getsize(audio_path)
                if size <= 131072:
                    hasher.update(f.read())
                else:
                    hasher.update(f.read(65536))
                    f.seek(-65536, 2)
                    hasher.update(f.read(65536))

        return hasher.hexdigest()[:32]

    def _compute_cache_key(
        self,
        image_path: str,
        audio_path: str,
        preset: str,
        framing_mode: str,
        width: int,
        height: int,
        fps: int,
        subtitle_text: str
    ) -> str:
        """Compute full cache key including all render parameters."""
        input_hash = self._compute_input_hash(image_path, audio_path)

        param_str = f"{input_hash}:{preset}:{framing_mode}:{width}:{height}:{fps}:{subtitle_text}"
        return hashlib.sha256(param_str.encode()).hexdigest()[:16]

    def get(
        self,
        image_path: str,
        audio_path: str,
        preset: str,
        framing_mode: str,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        subtitle_text: str = ""
    ) -> Optional[str]:
        """
        Check if rendered segment exists in cache.
        Returns output path if cached and valid, else None.
        """
        cache_key = self._compute_cache_key(
            image_path, audio_path, preset, framing_mode,
            width, height, fps, subtitle_text
        )

        entry = self.entries.get(cache_key)
        if not entry:
            return None

        # Verify output file still exists and is valid
        if not os.path.exists(entry.output_path) or os.path.getsize(entry.output_path) == 0:
            # Cache miss - remove stale entry
            del self.entries[cache_key]
            self._save_index()
            return None

        # Verify input files haven't changed (compare hashes)
        current_input_hash = self._compute_input_hash(image_path, audio_path)
        if current_input_hash != entry.input_hash:
            del self.entries[cache_key]
            self._save_index()
            return None

        return entry.output_path

    def put(
        self,
        image_path: str,
        audio_path: str,
        preset: str,
        framing_mode: str,
        output_path: str,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        subtitle_text: str = "",
        duration: float = 0.0
    ) -> str:
        """Store rendered segment in cache."""
        cache_key = self._compute_cache_key(
            image_path, audio_path, preset, framing_mode,
            width, height, fps, subtitle_text
        )

        # Copy to cache directory with cache_key as filename
        cache_output = os.path.join(self.cache_dir, f"{cache_key}.mp4")

        import shutil
        shutil.copy2(output_path, cache_output)

        entry = RenderCacheEntry(
            cache_key=cache_key,
            input_hash=self._compute_input_hash(image_path, audio_path),
            output_path=cache_output,
            params={
                "preset": preset,
                "framing_mode": framing_mode,
                "width": width,
                "height": height,
                "fps": fps,
                "subtitle_text": subtitle_text
            },
            duration=duration,
            created_at=os.path.getmtime(cache_output),
            file_size=os.path.getsize(cache_output)
        )

        self.entries[cache_key] = entry
        self._save_index()

        return cache_output

    def invalidate(self, pattern: str = None):
        """Invalidate cache entries. If pattern provided, remove matching keys."""
        if pattern:
            to_remove = [k for k in self.entries if pattern in k]
            for k in to_remove:
                entry = self.entries[k]
                if os.path.exists(entry.output_path):
                    try:
                        os.remove(entry.output_path)
                    except Exception:
                        pass
                del self.entries[k]
        else:
            # Clear all
            for entry in self.entries.values():
                if os.path.exists(entry.output_path):
                    try:
                        os.remove(entry.output_path)
                    except Exception:
                        pass
            self.entries = {}
        self._save_index()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_size = sum(e.file_size for e in self.entries.values())
        return {
            "entries": len(self.entries),
            "total_size_mb": total_size / (1024 * 1024),
            "cache_dir": self.cache_dir
        }


def get_render_cache(project_dir: str) -> RenderCache:
    """Factory: get render cache for a project."""
    cache_dir = os.path.join(project_dir, "data", "render_cache")
    return RenderCache(cache_dir)