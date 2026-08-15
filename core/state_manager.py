import os
import json
import re
import hashlib
from datetime import datetime
from urllib.parse import urlparse

STATE_FILE_NAME = "state.json"

def extract_video_id(source):
    """
    Universal multi-platform video ID resolver.
    Supports YouTube, Bilibili, TikTok, Douyin, Twitter/X, Vimeo, Dailymotion,
    Twitch, Instagram, generic Web URLs, and local files.
    """
    if source.startswith("http://") or source.startswith("https://"):
        parsed = urlparse(source)
        domain = parsed.netloc.lower()

        # 1. YouTube
        if "youtube.com" in domain or "youtu.be" in domain:
            yt_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:[&?]|$)", source)
            if yt_match:
                return f"yt_{yt_match.group(1)}"

        # 2. Bilibili (BV / av IDs)
        if "bilibili.com" in domain:
            bili_match = re.search(r"(BV[0-9A-Za-z]{10}|av\d+)", source, re.IGNORECASE)
            if bili_match:
                return f"bilibili_{bili_match.group(1)}"

        # 3. TikTok / Douyin
        if "tiktok.com" in domain or "douyin.com" in domain:
            tt_match = re.search(r"video\/(\d+)", source)
            if tt_match:
                return f"tiktok_{tt_match.group(1)}"

        # 4. Twitter / X
        if "twitter.com" in domain or "x.com" in domain:
            tw_match = re.search(r"status\/(\d+)", source)
            if tw_match:
                return f"twitter_{tw_match.group(1)}"

        # 5. Vimeo
        if "vimeo.com" in domain:
            vim_match = re.search(r"vimeo\.com\/(\d+)", source)
            if vim_match:
                return f"vimeo_{vim_match.group(1)}"

        # 6. Dailymotion
        if "dailymotion.com" in domain or "dai.ly" in domain:
            dm_match = re.search(r"(?:video\/|dai\.ly\/)([0-9A-Za-z]+)", source)
            if dm_match:
                return f"dailymotion_{dm_match.group(1)}"

        # Generic Web Fallback (Domain + MD5 Hash of URL)
        clean_domain = re.sub(r"[^\w]", "_", domain)
        url_hash = hashlib.md5(source.encode("utf-8")).hexdigest()[:8]
        return f"{clean_domain}_{url_hash}"

    # Local file path
    base = os.path.basename(source)
    clean_name = re.sub(r"[^\w\-_]", "_", os.path.splitext(base)[0])
    return clean_name if clean_name else "recap_project"

class StateManager:
    def __init__(self, project_dir, source, force=False):
        self.project_dir = project_dir
        self.state_file = os.path.join(project_dir, STATE_FILE_NAME)
        self.source = source
        self.force = force
        self.state = self._load_or_init_state()

    def _load_or_init_state(self):
        if not self.force and os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    print(f"📋 Loaded existing project state from: {self.state_file}")
                    return state
            except Exception as e:
                print(f"Warning: Failed to load state file ({e}). Re-initializing state.")

        # Fresh state
        now = datetime.now().isoformat()
        state = {
            "source": self.source,
            "created_at": now,
            "updated_at": now,
            "status": "INITIALIZED",
            "steps": {}
        }
        self.save_state(state)
        return state

    def save_state(self, state=None):
        if state:
            self.state = state
        self.state["updated_at"] = datetime.now().isoformat()
        os.makedirs(self.project_dir, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def is_step_completed(self, step_name, required_files=None):
        """
        Checks if a step is marked COMPLETED and all its required output files exist.
        """
        if self.force:
            return False

        step_info = self.state.get("steps", {}).get(step_name, {})
        if step_info.get("status") != "COMPLETED":
            return False

        if required_files:
            for fpath in required_files:
                if not fpath or not os.path.exists(fpath) or os.path.getsize(fpath) == 0:
                    return False

        return True

    def mark_step_completed(self, step_name, result_files=None):
        """
        Marks a pipeline step as COMPLETED and records its result file paths.
        """
        if "steps" not in self.state:
            self.state["steps"] = {}

        self.state["steps"][step_name] = {
            "status": "COMPLETED",
            "completed_at": datetime.now().isoformat(),
            "result_files": result_files or []
        }
        self.save_state()
        print(f"✅ Step [{step_name}] marked COMPLETED.")

    def set_project_status(self, status):
        self.state["status"] = status
        self.save_state()
