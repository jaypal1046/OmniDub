"""Two-pass manhwa understanding and narration with project story memory."""

import base64
import hashlib
import io
import json
import math
import os
import re
import tempfile
import time
from pathlib import Path

import requests
from PIL import Image

from .comic_script import clean_json_response


STORY_MODEL = "gemini-3.1-flash-lite"
STORY_MODELS = [STORY_MODEL, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite-preview", "gemini-3.6-flash"]
SPEAKING_WPM = 145
PANEL_SECONDS = (4, 6, 9, 13)
ANALYSIS_BATCH_SIZE = 6
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def get_gemini_api_keys():
    """Retrieve all available Gemini API keys in priority order for automatic failover."""
    keys = []
    primary = os.environ.get("GEMINI_API_KEY")
    if primary and primary.strip():
        keys.append(primary.strip())
    secondary = os.environ.get("GEMINI_API_KEY2")
    if secondary and secondary.strip() and secondary.strip() not in keys:
        keys.append(secondary.strip())
    for k, v in os.environ.items():
        if k.startswith("GEMINI_API_KEY") and v.strip() and v.strip() not in keys:
            keys.append(v.strip())
    return keys


def _skill_text(role):
    path = SKILLS_DIR / f"manhwa-{role}" / "SKILL.md"
    return path.read_text(encoding="utf-8").split("---", 2)[-1].strip()


def skill_fingerprint():
    return hashlib.sha256((_skill_text("story-analysis") + _skill_text("narration")).encode("utf-8")).hexdigest()


def _jpeg_data(image):
    data = io.BytesIO()
    image.save(data, format="JPEG", quality=80)
    return base64.b64encode(data.getvalue()).decode("ascii")


def _image_parts(path, label):
    with Image.open(path) as source:
        image = source.convert("RGB")
        overview = image.copy()
        overview.thumbnail((1024, 1024))
        parts = [(f"{label} overview", _jpeg_data(overview))]
        if label != "Current panel" or image.height <= 1400:
            return parts
        if image.width > 1024:
            image = image.resize((1024, round(image.height * 1024 / image.width)))
        tiles = []
        for top in range(0, image.height, 900):
            tiles.append(image.crop((0, top, image.width, min(top + 1024, image.height))))
            if top + 1024 >= image.height:
                break
        if len(tiles) > 16:
            raise ValueError(f"Panel is too tall for one request ({len(tiles)} detail tiles): {path}")
        parts.extend((f"{label} detail {number}/{len(tiles)} (top to bottom)", _jpeg_data(tile))
                     for number, tile in enumerate(tiles, 1))
        return parts


def _ask(prompt, images=(), role="story-analysis"):
    if role == "narration" and images:
        raise ValueError("Narration must use beat notes, not panel images")
    keys = get_gemini_api_keys()
    if not keys:
        raise RuntimeError("Story analysis needs GEMINI_API_KEY")
    parts = [{"text": prompt}]
    for label, path in images:
        for part_label, data in _image_parts(path, label):
            parts.extend(({"text": part_label}, {"inline_data": {"mime_type": "image/jpeg", "data": data}}))
    if sum(len(part.get("inline_data", {}).get("data", "")) for part in parts) > 18_000_000:
        raise ValueError("Panel images exceed Gemini's inline request limit; split the panel first")

    max_attempts = 10
    key_idx = 0
    for attempt in range(max_attempts):
        key = keys[key_idx % len(keys)]
        model = STORY_MODELS[attempt % len(STORY_MODELS)]
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": key},
                json={"system_instruction": {"parts": [{"text": _skill_text(role)}]},
                      "contents": [{"parts": parts}], "generationConfig": {"response_mime_type": "application/json"}},
                timeout=(15, 240),
            )
        except requests.RequestException as exc:
            delay = min(45, max(3, 2 ** (attempt + 1)))
            next_model = STORY_MODELS[(attempt + 1) % len(STORY_MODELS)]
            if len(keys) > 1 and (attempt + 1) % 2 == 0:
                key_idx = (key_idx + 1) % len(keys)
            key_info = f" (key #{key_idx + 1})" if len(keys) > 1 else ""
            print(f"⏳ Gemini connection/timeout ({type(exc).__name__}) on {model}; retrying in {delay:.0f}s (switching to {next_model}{key_info})...", flush=True)
            if attempt == max_attempts - 1:
                raise RuntimeError(f"Gemini request failed after {max_attempts} attempts ({type(exc).__name__})") from exc
            time.sleep(delay)
            continue
        else:
            if response.ok:
                try:
                    result = clean_json_response(response.json()["candidates"][0]["content"]["parts"][0]["text"])
                    if isinstance(result, dict):
                        return result
                except (KeyError, IndexError, ValueError):
                    pass
                if attempt == max_attempts - 1:
                    raise RuntimeError("Gemini returned invalid story JSON")
                time.sleep(2 ** attempt)
                continue
            if response.status_code == 429:
                retry = getattr(response, "headers", {}).get("Retry-After", "")
                if not retry:
                    try:
                        details = response.json().get("error", {}).get("details", [])
                        retry = next((item.get("retryDelay", "") for item in details
                                      if isinstance(item, dict) and item.get("retryDelay")), "")
                    except (ValueError, AttributeError, TypeError):
                        pass
                delay = float(str(retry).rstrip("s")) if re.fullmatch(r"\d+(?:\.\d+)?s?", str(retry)) else 30 * 2 ** attempt
                resp_text = getattr(response, "text", "") or ""
                # If daily quota exhausted or long wait:
                if delay > 120 or "quota" in resp_text.lower():
                    # 1. First try failing over to secondary API key if available
                    if len(keys) > 1 and attempt < max_attempts - 1:
                        key_idx = (key_idx + 1) % len(keys)
                        print(f"⏳ Gemini key quota exhausted on {model}; failing over to GEMINI_API_KEY{key_idx + 1}...", flush=True)
                        time.sleep(2)
                        continue
                    # 2. Try rotating to the next available model
                    if attempt < max_attempts - 1:
                        next_model = STORY_MODELS[(attempt + 1) % len(STORY_MODELS)]
                        print(f"⏳ Quota exhausted on {model} (wait {delay:.0f}s); switching model to {next_model}...", flush=True)
                        time.sleep(2)
                        continue
                    raise RuntimeError(f"Gemini HTTP 429: rate limit or quota exhausted across all available keys and models. "
                                       f"Saved chapter progress; retry later (suggested wait {delay:.0f}s).")
                if attempt == max_attempts - 1:
                    raise RuntimeError(f"Gemini HTTP 429: rate limit or quota exhausted. "
                                       f"Saved chapter progress; retry later (suggested wait {delay:.0f}s).")
                print(f"⏳ Gemini rate limit; retrying in {delay:.0f}s...", flush=True)
                time.sleep(max(1, delay))
                continue
            if response.status_code in (408, 500, 502, 503, 504):
                if attempt == max_attempts - 1:
                    raise RuntimeError(f"Gemini HTTP {response.status_code}")
                delay = min(45, max(3, 2 ** (attempt + 1)))
                next_model = STORY_MODELS[(attempt + 1) % len(STORY_MODELS)]
                if len(keys) > 1 and (attempt + 1) % 3 == 0:
                    key_idx = (key_idx + 1) % len(keys)
                model_info = f" (switching to {next_model})" if next_model != model else ""
                print(f"⏳ Gemini server busy/overloaded (HTTP {response.status_code}); retrying in {delay:.0f}s{model_info}...", flush=True)
                time.sleep(delay)
                continue
            raise RuntimeError(f"Gemini HTTP {response.status_code}")
        time.sleep(2 ** attempt)


def _save_json(path, value):
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=dir_name, delete=False) as out:
        json.dump(value, out, indent=2, ensure_ascii=False)
        temporary = out.name
    try:
        # On Windows, os.replace can fail with [WinError 5] Access is denied
        # if the destination file is momentarily locked by Windows Defender,
        # indexing services, or IDE file watchers.
        for attempt in range(10):
            try:
                os.replace(temporary, path)
                return
            except (PermissionError, OSError):
                time.sleep(0.05 * (attempt + 1))
        # Fallback to direct write if rename remained locked
        with open(path, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False)
    finally:
        if os.path.exists(temporary):
            try:
                os.remove(temporary)
            except Exception:
                pass


def _reference_path(story_dir, look):
    relative = look.get("ref_image")
    if not isinstance(relative, str):
        return None
    path = os.path.realpath(os.path.join(story_dir, relative))
    try:
        if os.path.commonpath((story_dir, path)) != story_dir:
            return None
    except ValueError:
        return None
    return path if os.path.isfile(path) else None


def build_story_script(project_dir, chapter_id, panels, custom_prompt=None, story_dir=None):
    """Analyze panels in order, narrate from notes only, then save chapter memory."""
    if not panels or not any(panel.get("action", "INCLUDE") == "INCLUDE" for panel in panels):
        raise ValueError("Chapter needs at least one included panel")
    data_dir = os.path.join(project_dir, "data")
    story_dir = os.path.realpath(story_dir or project_dir)
    bible_path = os.path.join(story_dir, "data", "story_bible.json")
    bible = {"characters": [], "chapters": [], "open_threads": [], "timeline": [], "rolling_summary": ""}
    if os.path.exists(bible_path):
        with open(bible_path, encoding="utf-8") as source:
            bible.update(json.load(source))
    if any(chapter.get("id") == chapter_id for chapter in bible["chapters"]):
        if bible["chapters"][-1].get("id") != chapter_id:
            raise ValueError(f"Cannot rewrite chapter {chapter_id} after later chapters without rebuilding story memory")
        previous = bible["chapters"][-1]
        if "before" not in previous:
            raise ValueError(f"Chapter {chapter_id} has no previous story snapshot; review story_bible.json before rerunning")
        bible["chapters"].pop()
        bible["rolling_summary"] = previous["before"]["rolling_summary"]
        bible["open_threads"] = previous["before"]["open_threads"]
        bible["timeline"] = [event for event in bible["timeline"] if event.get("chapter") != chapter_id]
        bible["characters"] = [character for character in bible["characters"] if character.get("first_seen") != chapter_id]
    before = {"rolling_summary": bible["rolling_summary"], "open_threads": list(bible["open_threads"])}
    chapter_tag = hashlib.sha256(chapter_id.encode("utf-8")).hexdigest()[:8]

    source_state = []
    for panel in panels:
        image_stat = os.stat(panel["image_path"])
        source_state.append((panel["image_path"], image_stat.st_size, image_stat.st_mtime_ns,
                             panel.get("action"), panel.get("ocr_text"), panel.get("ocr_flagged", False),
                             panel.get("ocr_ignore", False)))
    bible_state = os.stat(bible_path) if os.path.exists(bible_path) else None
    signature = hashlib.sha256(json.dumps([7, STORY_MODEL, skill_fingerprint(), chapter_id, source_state,
                                           (bible_state.st_size, bible_state.st_mtime_ns) if bible_state else None],
                                          ensure_ascii=False).encode("utf-8")).hexdigest()
    progress_path = os.path.join(data_dir, "story_progress.json")
    notes = []
    chapter_so_far = ""
    summary_through = 0
    narration_batches = []
    if os.path.exists(progress_path):
        with open(progress_path, encoding="utf-8") as source:
            progress = json.load(source)
        saved_notes = progress.get("notes", [])
        if (progress.get("signature") == signature and isinstance(saved_notes, list)
                and len(saved_notes) <= len(panels)
                and all(note.get("file") == panel.get("file") for note, panel in zip(saved_notes, panels))):
            notes = saved_notes
            bible = progress["bible"]
            chapter_so_far = progress.get("chapter_so_far", "")
            summary_through = progress.get("summary_through", 0)
            narration_batches = progress.get("narration_batches", [])
    crops_dir = os.path.join(story_dir, "data", "character_crops")
    os.makedirs(crops_dir, exist_ok=True)
    batch_facts = {}
    for position, panel in enumerate(panels[len(notes):], len(notes) + 1):
        if len(notes) >= 24 and len(notes) % 24 == 0 and summary_through < len(notes):
            summary = _ask(
                "Summarize these factual chapter beats into one short paragraph for following-panel analysis. "
                "Preserve named characters, causality, unresolved threads, and uncertainty. Add no new facts. "
                "Return JSON object {\"summary\":\"...\"}.\n"
                f"Earlier chapter summary: {chapter_so_far}\n"
                f"New beats: {json.dumps([note['beat'] for note in notes[summary_through:]], ensure_ascii=False)}"
            )
            if not isinstance(summary.get("summary"), str) or not summary["summary"].strip():
                raise RuntimeError("Gemini omitted chapter continuity summary")
            chapter_so_far = summary["summary"]
            summary_through = len(notes)
            _save_json(progress_path, {"signature": signature, "notes": notes, "bible": bible,
                                       "chapter_so_far": chapter_so_far, "summary_through": summary_through})
        recent_ids = [sighting.get("id") for note in reversed(notes[-12:])
                      for sighting in note.get("characters", []) if isinstance(sighting, dict)]
        reference_ids = list(dict.fromkeys(recent_ids + [c["id"] for c in reversed(bible["characters"])]))
        references = []
        for character_id in reference_ids:
            character = next((c for c in bible["characters"] if c["id"] == character_id), None)
            if not character:
                continue
            look = next((look for look in reversed(character.get("looks", []))
                         if _reference_path(story_dir, look)), None)
            if look:
                references.append((character, look))
            if len(references) == 6:
                break
        if position not in batch_facts:
            batch = panels[position - 1:position - 1 + ANALYSIS_BATCH_SIZE]
            selected = list(range(position, position + len(batch)))
            images = [(f"Panel {number}", panels[number - 1]["image_path"]) for number in selected]
            images.extend((f"Known character {character['id']}", _reference_path(story_dir, look))
                          for character, look in references[:2])
            batch_input = [{"panel": position + offset, "file": item.get("file"),
                            "ocr": item.get("ocr_text", ""), "ocr_flagged": item.get("ocr_flagged", False),
                            "image_only": item.get("ocr_ignore", False),
                            "image_attached": position + offset in selected}
                           for offset, item in enumerate(batch)]
            roster = [{"id": character["id"], "name": character.get("name"), "role": character.get("role"),
                       "looks": [look.get("description") for look in character.get("looks", [])[-3:]]}
                      for character in bible["characters"]]
            result = _ask(
                "You are a factual manhwa story analyst. Read these panels in numbered story order. "
                "OCR may contain errors, watermarks or missing words. Every panel image is attached and labeled. "
                "For image_only panels, ignore OCR entirely and infer only what the image supports. "
                "Use each image to verify actions, speakers and visual story changes; mark uncertainty. "
                "Do not invent actions, identities or motives. "
                "CANONICAL NAME DISCIPLINE: Normalize all character names against Known characters. "
                "Never adopt mangled OCR names or homophone corruptions ('fief' not 'thief', 'Saintess' not 'saintest'). "
                "Attribute dialogue to specific known characters whenever visible; never label known characters as 'unidentified voice'. "
                "FLASHBACK CROPS VS LIVE EVENTS: When a panel re-displays an earlier action (e.g. face touch, oath, falling), "
                "explicitly label the beat as '[Flashback reflection]' rather than a new live physical action. "
                "Return JSON object {\"panels\": [one object per input "
                "panel with keys panel, beat, characters, new_threads, resolved_threads, timeline_event, "
                "importance, needs_image]}. needs_image is true when a panel needs a closer visual check. "
                "Bounds are fractional coordinates of that panel image; use null if unsure. "
                f"Story so far: {bible['rolling_summary']}\nKnown characters: {json.dumps(roster, ensure_ascii=False)}\n"
                f"Current chapter: {chapter_so_far}\nRecent beats: {json.dumps([note['beat'] for note in notes[-12:]], ensure_ascii=False)}\n"
                f"Open threads: {json.dumps(bible['open_threads'], ensure_ascii=False)}\n"
                f"Panels: {json.dumps(batch_input, ensure_ascii=False)}", images)
            facts = result.get("panels")
            expected = set(range(position, position + len(batch)))
            if not isinstance(facts, list) or {item.get("panel") for item in facts if isinstance(item, dict)} != expected or len(facts) != len(batch):
                raise RuntimeError(f"Gemini omitted or duplicated panels in analysis batch starting at {position}")
            batch_facts = {item["panel"]: item for item in facts}
        fact = batch_facts.pop(position)
        if panel.get("ocr_flagged") or fact.get("needs_image"):
            checked = _ask(
                "Check this panel image against the existing factual beat. Correct visual actions and speaker "
                "identity only when supported. Return one JSON object with keys beat, characters, new_threads, "
                "resolved_threads, timeline_event, importance. Character bounds are fractions of this image. "
                f"Panel OCR: {panel.get('ocr_text', '')}\nDraft: {json.dumps(fact, ensure_ascii=False)}",
                [("Current panel", panel["image_path"])])
            fact.update(checked)
        if not isinstance(fact.get("beat"), str) or not fact["beat"].strip():
            raise RuntimeError(f"No factual beat for panel {position}")
        sightings = fact.get("characters") or []
        if not isinstance(sightings, list):
            raise RuntimeError(f"Invalid character list for panel {position}")
        for sighting in sightings:
            if not isinstance(sighting, dict):
                continue
            confidence = sighting.get("confidence", 0)
            if sighting.get("id") and (not isinstance(confidence, (int, float)) or confidence < 0.8):
                sighting["id"] = None
                sighting["review"] = True
                continue
            existing = next((c for c in bible["characters"] if c["id"] == sighting.get("id")), None)
            if existing is None:
                new_id = f"c{max((int(c['id'][1:]) for c in bible['characters'] if c.get('id', '').startswith('c') and c['id'][1:].isdigit()), default=0) + 1}"
                existing = {"id": new_id, "name": None, "role": sighting.get("role", "unknown"),
                            "first_seen": chapter_id, "relations": {}, "looks": [], "review": True}
                bible["characters"].append(existing)
            if sighting.get("name") and isinstance(confidence, (int, float)) and confidence >= 0.85:
                existing["name"] = sighting["name"]
            elif sighting.get("name"):
                existing["review"] = True
            look = sighting.get("look")
            bounds = sighting.get("bounds")
            if (isinstance(look, str) and look and not any(saved.get("description", "").casefold() == look.casefold()
                                 for saved in existing["looks"])
                    and isinstance(bounds, list) and len(bounds) == 4
                    and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in bounds)):
                with Image.open(panel["image_path"]) as image:
                    width, height = image.size
                    box = tuple(round(v * size) for v, size in zip(bounds, (width, height, width, height)))
                    if box[2] > box[0] and box[3] > box[1]:
                        relative = os.path.join("data", "character_crops", f"{existing['id']}_{chapter_tag}_{position}.jpg")
                        image.crop(box).convert("RGB").save(os.path.join(story_dir, relative), quality=85)
                        existing["looks"].append({"description": look, "ref_image": relative})
                        existing["looks"] = existing["looks"][-3:]
            sighting["id"] = existing["id"]
        importance = fact.get("importance", 2)
        if type(importance) is not int or importance not in range(4):
            importance = 2
        note = {"panel": position, "file": panel.get("file"), "action": panel.get("action", "INCLUDE"),
                "beat": fact["beat"], "characters": sightings, "importance": importance}
        notes.append(note)
        for thread in fact.get("new_threads", []):
            if isinstance(thread, str) and thread not in bible["open_threads"]:
                bible["open_threads"].append(thread)
        for thread in fact.get("resolved_threads", []):
            if thread in bible["open_threads"]:
                bible["open_threads"].remove(thread)
        if fact.get("timeline_event"):
            bible["timeline"].append({"chapter": chapter_id, "panel": position, "event": fact["timeline_event"]})
        _save_json(progress_path, {"signature": signature, "notes": notes, "bible": bible,
                                   "chapter_so_far": chapter_so_far, "summary_through": summary_through})
        if position % ANALYSIS_BATCH_SIZE == 0 or position == len(panels):
            print(f"📖 Story analysis: {position}/{len(panels)} panels", flush=True)
    _save_json(os.path.join(data_dir, "story_beats.json"), notes)

    plan = []
    pending_lore = 0
    for note in notes:
        if note["action"] == "STORY_ONLY":
            pending_lore += 1
            seconds = 0
        else:
            seconds = min(18, PANEL_SECONDS[note["importance"]] + min(5, pending_lore * 2))
            pending_lore = 0
        max_words = max(1, (seconds - 1) * SPEAKING_WPM // 60) if seconds else 0
        plan.append({"panel": note["panel"], "file": note["file"], "action": note["action"],
                     "importance": note["importance"], "beat": note["beat"],
                     "target_sec": seconds, "max_words": max_words, "max_chars": max_words * 12})
    plan_path = os.path.join(data_dir, "story_plan.json")
    plan_file = {"speaking_wpm": SPEAKING_WPM, "planned_total_sec": sum(item["target_sec"] for item in plan),
                 "panels": plan}
    _save_json(plan_path, plan_file)

    narrator_bible = {
        "rolling_summary": bible["rolling_summary"],
        "characters": [{"id": c["id"], "name": c.get("name"), "role": c.get("role"),
                        "relations": c.get("relations", {}), "review": c.get("review", False)}
                       for c in bible["characters"]],
        "open_threads": bible["open_threads"],
        "timeline": bible["timeline"][-30:],
    }
    by_panel = {}
    for start in range(0, len(notes), 12):
        if start // 12 < len(narration_batches):
            by_panel.update({line["panel"]: line["text"] for line in narration_batches[start // 12]})
            continue
        batch = notes[start:start + 12]
        batch_plan = plan[start:start + 12]
        narration = _ask(
            "You are an elite YouTube manhwa recap storyteller (in the viral style of top recap channels like AniStop and PlotArmor). "
            "Write punchy voiceover from FACTS ONLY. You have no images. "
            "Tell what happened, who is clashing, and why it matters in a sharp, conversational voice. "
            "CRITICAL CHARACTER ROLES & NATURAL NAMING: Introduce the protagonist by canonical Story Bible name ONCE. "
            "Afterward, PRIORITIZE natural pronouns (he/him/his) and short contextual descriptors. STRICTLY BAN repeating the clumsy full name across adjacent lines. "
            "NO PING-PONG NAME DRUMMING: Do NOT alternate character names back-to-back ('Vera does X. Renee does Y. Vera says Z.'). Weave interactions using pronouns (he/she/they). "
            "Cap monikers ('our boy', 'our guy', 'our protagonist') to at most once per batch for punchlines; NEVER spam them on consecutive lines. "
            "NEVER call mentors, dying masters, enemies, or prologue figures 'our MC'—treat them as the veteran master or by canonical name. "
            "Do NOT use meta announcements like 'Enter our actual MC'—weave character arrivals seamlessly into the narrative flow. "
            "HOOK & PREMISE (0-15s): The opening lines MUST hook viewers with the CORE PREMISE + HIGH STAKES + ABSURD TWIST of the series. "
            "BANNED: Do NOT copy prompt examples verbatim. Do NOT insert fake mid-scene rhetorical questions ('What is even happening?', 'A spar?'). "
            "BANNED CRUTCHES: 'sweating bullets', 'cold sweat', 'before he can catch his breath', 'deadpan expression', 'internally screaming', 'every Tuesday', 'social suicide'. "
            "NO BLUSH FATIGUE: Do NOT repeat 'blushes deeply/heavily' or 'cheeks flushing' repeatedly. Express romance through banter and subtle actions. "
            "FLASHBACKS VS LIVE EVENTS: Never narrate a recurring memory crop as if the physical action is happening again right now. Frame it as reflection or omit. "
            "NO SCREENPLAY DESCRIPTIVISM: Never describe camera frames, flowers entering frames, teacups clicking, doors closing, or decorative props. "
            "NO META CAPTIONS: Never say 'A caption reminds us...' or 'An observer notes...'. State lore directly. "
            "HOMOPHONE & GENRE LOCK: Use exact terms: 'fief' (NEVER 'thief'), 'Saintess' (NEVER 'saintest', 'saintis', 'saints'), 'Sir Knight' (NEVER 'Sir Night'), 'White Night' (NEVER 'white knight'), 'petals' (NEVER 'pedals'), 'deference' (NEVER 'difference'), 'courtier' (NEVER 'cordier'), 'concedes' (NEVER 'conceds'). "
            "Genre accuracy: Use Murim terms (sect, inner qi, swordsman, vagrant); NEVER use 'Ronin' or modern corporate jargon. Zero name hallucinations. "
            "Vary pace. Inject natural, scene-specific witty banter and kinetic action tension. "
            "Return JSON object: {\"lines\":[{\"panel\":1,\"text\":\"...\"},...]}. "
            "Provide exactly one short spoken line for each INCLUDE panel, and none for STORY_ONLY panels. "
            "Each line MUST fit its max_words and max_chars. Weave relevant STORY_ONLY facts into the next INCLUDE line. "
            "Give major events more space and make filler brief. Use reviewed OCR to preserve exact dialogue meaning, "
            "but treat analyst beats as the story facts; ignore watermarks and do not recite every bubble. "
            f"Additional style instruction: {custom_prompt or 'witty, punchy, dramatic YouTube recap voice'}\n"
            f"Chapter position: panels {start + 1}-{start + len(batch)} of {len(notes)}. "
            f"Previous narrated lines: {json.dumps(list(by_panel.items())[-4:], ensure_ascii=False)}\n"
            f"Earlier beat notes: {json.dumps([note['beat'] for note in notes[max(0, start - 12):start]], ensure_ascii=False)}\n"
            f"Story bible: {json.dumps(narrator_bible, ensure_ascii=False)}\nBeat notes: {json.dumps(batch, ensure_ascii=False)}\n"
            f"Reviewed OCR: {json.dumps([{'panel': start + offset + 1, 'text': '' if panel.get('ocr_ignore') else panel.get('ocr_text', '')} for offset, panel in enumerate(panels[start:start + 12])], ensure_ascii=False)}\n"
            f"Time plan: {json.dumps(batch_plan, ensure_ascii=False)}",
            role="narration",
        )
        lines = narration.get("lines")
        if not isinstance(lines, list):
            raise RuntimeError("Narrator returned no lines")
        batch_lines = {line.get("panel"): line.get("text", "") for line in lines if isinstance(line, dict)}
        for _ in range(3):
            overlong = [item for item in batch_plan if item["target_sec"] and
                        (len(str(batch_lines.get(item["panel"], "")).split()) > item["max_words"] or
                         len(str(batch_lines.get(item["panel"], ""))) > item["max_chars"])]
            if not overlong:
                break
            rewrite = _ask(
                "Shorten these spoken lines. Rewrite each as one complete sentence. Keep the key event and add no facts. "
                "Use at most max_words words and max_chars characters; count every word before returning. "
                "Return JSON object {\"lines\":[{\"panel\":1,\"text\":\"...\"}]}.\n"
                f"Lines and limits: {json.dumps([{'panel': item['panel'], 'beat': item['beat'], 'text': batch_lines.get(item['panel'], ''), 'max_words': max(1, item['max_words'] * 3 // 4), 'max_chars': item['max_chars'] * 3 // 4} for item in overlong], ensure_ascii=False)}",
                role="narration",
            )
            if not isinstance(rewrite.get("lines"), list):
                raise RuntimeError("Narrator could not shorten overlong lines")
            batch_lines.update({line.get("panel"): line.get("text", "") for line in rewrite["lines"] if isinstance(line, dict)})
        for item in batch_plan:
            if not item["target_sec"]:
                continue
            text = batch_lines.get(item["panel"])
            if not isinstance(text, str) or not text.strip():
                raise RuntimeError(f"Narrator omitted panel {item['panel']}")
            by_panel[item["panel"]] = text
        narration_batches.append([{"panel": item["panel"], "text": by_panel[item["panel"]]}
                                  for item in batch_plan if item["target_sec"]])
        _save_json(progress_path, {"signature": signature, "notes": notes, "bible": bible,
                                   "chapter_so_far": chapter_so_far, "summary_through": summary_through,
                                   "narration_batches": narration_batches})
        print(f"🎙️ Narration: {min(start + 12, len(notes))}/{len(notes)} story panels", flush=True)
    for note in notes:
        if note["action"] == "INCLUDE" and not str(by_panel.get(note["panel"], "")).strip():
            raise RuntimeError(f"Narrator omitted panel {note['panel']}")

    for item in plan:
        text = by_panel.get(item["panel"], "")
        item["words"] = len(text.split())
        if item["target_sec"] and (item["words"] > item["max_words"] or len(text) > item["max_chars"]):
            needed_sec = math.ceil(item["words"] * 60 / SPEAKING_WPM) + 1
            if needed_sec > min(20, item["target_sec"] + 5):
                raise RuntimeError(f"Panel {item['panel']} narration is {item['words']} words; "
                                   f"maximum is {item['max_words']} words")
            item["target_sec"] = max(item["target_sec"], needed_sec)
            item["max_words"] = max(item["max_words"], item["words"])
            item["max_chars"] = max(item["max_chars"], len(text))
            print(f"⏱️ Panel {item['panel']} needs {item['target_sec']}s for narration", flush=True)
        item["estimated_sec"] = round(item["words"] * 60 / SPEAKING_WPM + (1 if item["words"] else 0), 1)
    plan_file["planned_total_sec"] = sum(item["target_sec"] for item in plan)
    plan_file["estimated_total_sec"] = round(sum(item["estimated_sec"] for item in plan), 1)
    _save_json(plan_path, plan_file)

    if bible.get("memory_version") == 2:
        if os.path.exists(progress_path):
            os.remove(progress_path)
        return notes, by_panel

    update = _ask(
        "Summarize factual chapter events from these notes. Return JSON object with summary (5-8 short lines as a list), "
        "rolling_summary (one short story-so-far paragraph), and relations (list of {from_id,to_id,relationship}). "
        "Do not invent or promote uncertain identity matches.\n"
        f"Previous rolling summary: {bible['rolling_summary']}\nBeats: {json.dumps(notes, ensure_ascii=False)}"
    )
    if not isinstance(update.get("summary"), list) or not isinstance(update.get("rolling_summary"), str):
        raise RuntimeError("Story memory update was incomplete")
    bible["chapters"].append({"id": chapter_id, "summary": update["summary"], "before": before})
    bible["rolling_summary"] = update["rolling_summary"]
    for relation in update.get("relations", []):
        if not isinstance(relation, dict):
            continue
        character = next((c for c in bible["characters"] if c["id"] == relation.get("from_id")), None)
        if character and any(c["id"] == relation.get("to_id") for c in bible["characters"]):
            character["relations"][relation["to_id"]] = relation.get("relationship", "unknown")
    _save_json(bible_path, bible)
    if os.path.exists(progress_path):
        os.remove(progress_path)
    return notes, by_panel


def polish_story_script(draft, notes, plan, bible, progress_path):
    """Rewrite the complete draft into connected voiceover before TTS."""
    signature = hashlib.sha256(json.dumps([7, draft, notes, plan, bible, STORY_MODEL, skill_fingerprint()],
                                          sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    progress = {}
    if os.path.exists(progress_path):
        with open(progress_path, encoding="utf-8") as source:
            progress = json.load(source)
        if progress.get("signature") != signature:
            progress = {}
    progress.setdefault("signature", signature)
    progress.setdefault("outline_batches", [])
    for start in range(len(progress["outline_batches"]) * 22, len(notes), 22):
        end = min(len(notes), start + 22)
        outline = _ask(
            "Turn this section into a chronological CAUSAL STORY OUTLINE. Preserve each distinct argument, "
            "reply, confession, choice, revelation, and consequence. Combine decorative or repeated panels. "
            "CANONICAL CHARACTER NAMES: Use exact names from the Story Bible (never mangled OCR names or homophones). "
            "Attribute dialogue to the actual speaker. Fix OCR homophones ('fief' not 'thief', 'Saintess' not 'saintest'). "
            "FLASHBACK / REPEATED PANELS: Combine decorative or cropped flashback panels into a single causal beat; "
            "never outline a cropped memory panel as a new live physical event. "
            "State speakers only when clear. Omit physical appearance, poses, expressions, scenery, colors, "
            "sound effects, and credits. Do not invent motives or events. Return JSON "
            "{\"events\":[\"event 1\",\"event 2\"]}.\n"
            f"Earlier story: {bible.get('rolling_summary', '')}\n"
            f"Previous events: {json.dumps([event for batch in progress['outline_batches'][-1:] for event in batch], ensure_ascii=False)}\n"
            f"Beats: {json.dumps([{'panel': n['panel'], 'beat': n['beat']} for n in notes[start:end]], ensure_ascii=False)}\n"
            f"Reviewed dialogue: {json.dumps([{'panel': x['story_panel'], 'ocr': x['ocr_text']} for x in draft if start < x['story_panel'] <= end and x.get('ocr_text')], ensure_ascii=False)}",
            role="story-analysis",
        )
        events = outline.get("events")
        if not isinstance(events, list) or not events or any(not isinstance(event, str) for event in events):
            raise RuntimeError(f"Story outline returned no events for panels {start + 1}-{end}")
        progress["outline_batches"].append(events)
        _save_json(progress_path, progress)
    progress["outline"] = [event for batch in progress["outline_batches"] for event in batch]
    _save_json(progress_path, progress)
    if not progress.get("story") and not progress.get("story_draft"):
        word_budget = max(120, int(sum(x["max_words"] for x in plan["panels"]) * 0.6))
        response = _ask(
            "Write the complete chapter as one connected, spoken manhwa recap story in the viral, entertaining style of top YouTube channels (AniStop, Manhwa Recap, PlotArmor). "
            "CORE PREMISE HOOK (0-15s): The very first 1-2 sentences MUST hook the viewer with the CORE PREMISE + HIGH STAKES + ABSURD TWIST of the series. "
            "NEVER open with dry clichés like 'It all begins when...' or 'Our story begins...'. Do NOT copy prompt examples verbatim. "
            "CRITICAL MC IDENTIFICATION & NATURAL NAMING: Introduce the true Protagonist by canonical name ONCE. Afterward, PRIORITIZE natural pronouns (he/him/his) "
            "and short situational descriptors. STRICTLY BAN repeating the clumsy full name in every sentence. "
            "NO PING-PONG NAME DRUMMING: In dialogue or 1-on-1 scenes, NEVER alternate character names back-to-back ('Vera said... Renee replied... Vera wondered... Renee moved...'). Establish who is interacting once, then let natural pronouns (he/she) carry the rhythm. Only reintroduce names upon topic shifts, entrances, or location cuts. "
            "Cap monikers ('our boy', 'our guy', 'our protagonist') to at most 1-2 times in the entire chapter, strictly for comedic punchlines. "
            "NEVER call mentors, dying masters, enemies, or flashback figures 'our MC'—treat them as the legendary master or by canonical name. "
            "Do NOT use meta announcements like 'Enter our actual MC'—weave arrivals seamlessly into the narrative flow. "
            "HOMOPHONE & FANTASY DICTIONARY LOCK: Always use proper spelling: 'fief' (NEVER 'thief' for land/holdings), 'Saintess' (NEVER 'saintest', 'saintis', 'saints', 'Santa'), 'Sir Knight' (NEVER 'Sir Night'), 'White Night' (NEVER 'white knight' if referring to holy order/title), 'petals' (NEVER 'pedals'), 'deference' (NEVER 'difference'), 'courtier' (NEVER 'cordier'), 'adjutant' (NEVER 'agitant'), 'stirrup' (NEVER 'steerup'). "
            "FLASHBACK CROPS VS LIVE EVENTS: Webtoon artists repeat cropped panels for emotional reflection. NEVER re-narrate a recurring flashback as if the physical action is happening again in live continuity! Frame it strictly as internal memory or omit. "
            "NO META-NARRATIVE ARTIFACTS: NEVER write 'A caption reminds us...', 'An observer notes...', or 'The panel shows...'. Deliver world lore and actions with direct narrator authority. "
            "NO BLUSH FATIGUE: Do NOT repeat 'blushing bright red', 'cheeks burning', or embarrassment clichés across multiple sentences. Convey connection through sharp dialogue and demeanor. "
            "CLEAN PARALLEL TRANSITIONS: When cutting between parallel events or locations, use clean grounding markers ('Meanwhile, outside the hall...', 'Back at the estate...'). "
            "BANNED CRUTCHES: 'sweating bullets', 'cold sweat', 'before he can catch his breath', 'deadpan expression', 'internally screaming', 'every Tuesday', 'social suicide'. "
            "Deliver energetic fight commentary, dramatic stakes, and organic situational wit. "
            "End with the chapter's real consequence, cliffhanger, or hype teaser. Use natural spoken transitions and varying pace. "
            "Use confirmed names from Story Bible, relevant earlier story memory, and important dialogue meaning. "
            "Skip decorative or repeated beats. Never describe panels, images, poses, outfits, camera views, or OCR. "
            "Do not invent events, fake motives, or certainty. Write natural, flowing spoken paragraphs, not panel notes or a list. "
            f"Cover every causal event in approximately {min(word_budget, len(progress['outline']) * 25)} to {word_budget} spoken words, without padding. "
            "Return JSON object {\"story\": \"...\"} with story as the complete prose narration.\n"
            f"Series memory: {json.dumps({'story_so_far': bible.get('rolling_summary', ''), 'earlier_chapters': [{'id': c['id'], 'summary': c.get('summary', [])} for c in bible.get('chapters', [])[-3:]], 'characters': [{'id': c['id'], 'name': c.get('name'), 'aliases': c.get('aliases', []), 'role': c.get('role'), 'relations': c.get('relations', {}), 'review': c.get('review', False)} for c in bible.get('characters', [])], 'open_threads': bible.get('open_threads', []), 'timeline': bible.get('timeline', [])[-12:]}, ensure_ascii=False)}\n"
            f"Causal events: {json.dumps(progress['outline'], ensure_ascii=False)}",
            role="narration",
        )
        story_val = response.get("story")
        if not story_val:
            for k in ("prose", "narration", "chapter_story", "recap", "text", "story_draft", "story_narration"):
                if isinstance(response.get(k), str) and response[k].strip():
                    story_val = response[k]
                    break
            if not story_val and isinstance(response, dict):
                vals = [v for v in response.values() if isinstance(v, str) and len(v.strip()) > 30]
                if vals:
                    story_val = "\n\n".join(vals)
        if not isinstance(story_val, str) or not story_val.strip():
            raise RuntimeError("Story writer returned no chapter story")
        progress["story_draft"] = story_val
        _save_json(progress_path, progress)
    if not progress.get("story_cleaned"):
        cleaned = _ask(
            "Rewrite this draft as a person telling a friend the chapter's story with sharp YouTube recap flair. Keep the events, "
            "causes, stakes, dialogue meaning, humor, and uncertainty. Ensure the protagonist is referred to with natural pronouns (he/him/his) "
            "rather than repetitive full-name calling. Cap 'our boy' / 'our MC' to rare comedic moments. "
            "PRUNE PING-PONG NAME DRUMMING: Smooth out back-and-forth name ping-pong ('Vera... Renee... Vera... Renee...') into natural pronoun flow (he/she). Names should only appear when necessary to resolve ambiguity. "
            "FIX HOMOPHONES & OCR SLIPS: Replace 'thief' -> 'fief' when referring to territory/holdings; 'saintest/saintis/saints' -> 'Saintess'; 'white knight' -> 'White Night' (holy order/title); 'pedals' -> 'petals'; 'difference' -> 'deference'; 'agitant' -> 'adjutant'. "
            "PRUNE REPEATED MEMORY LOOPS: If an action or beat (e.g., touching a face, falling, an oath) is narrated multiple times because of panel flashback crops, consolidate it into a single clean reference or frame it as a passing reflection. "
            "BANISH META-CAPTIONS & OBSERVER TROPES: Remove 'A caption notes...', 'An observer reckons...', 'The narrator sees...'. State lore directly. "
            "PRUNE BLUSH FATIGUE: Remove repeated blushing or flushing descriptions. "
            "Preserve witty, self-aware narrator banter and kinetic action momentum without canned repetitive clichés ('sweating bullets', 'before he can catch his breath', 'deadpan'). "
            "Delete visual staging: what is shown, poses, clothing, facial expressions, camera views, lighting, sound effects, and decorative actions. "
            "If a detail changes no event or relationship, omit it. Do not add facts. "
            "For example, 'A bloody hand appears against a dark backdrop' becomes 'His condition is worsening'; "
            "'A spoon dips into porridge' is omitted unless the meal changes the interaction. "
            "When a previous chapter exists, make the first sentence explicitly connect its ending to this "
            "chapter's first event. Do not begin with only a time skip. "
            "SENTENCE INTEGRITY & TTS CADENCE: Eliminate spliced or broken clauses. Keep spoken sentences under 40 words. Write connected spoken paragraphs with natural transitions and rhythm for TTS voiceover. "
            "Return JSON object {\"story\":\"...\"}.\n"
            f"Previous story: {bible.get('rolling_summary', '')}\n"
            f"Previous chapter: {json.dumps(bible.get('chapters', [])[-1:], ensure_ascii=False)}\n"
            f"Draft story: {progress.get('story_draft') or progress['story']}",
            role="narration",
        )
        clean_val = cleaned.get("story")
        if not clean_val:
            for k in ("prose", "narration", "cleaned_story", "recap", "text"):
                if isinstance(cleaned.get(k), str) and cleaned[k].strip():
                    clean_val = cleaned[k]
                    break
        if not isinstance(clean_val, str) or not clean_val.strip():
            raise RuntimeError("Story cleanup returned no narration")
        progress["story"] = clean_val
        progress["story_cleaned"] = True
        progress["batches"] = []
        _save_json(progress_path, progress)
    if not draft:
        raise RuntimeError("No video panels available for the story")
    passages = []
    for sentence in re.split(r"(?<=[.!?])\s+", progress["story"].strip()):
        words = sentence.split()
        while words:
            limit = min(40, len(words))
            boundary = next((i for i in range(limit - 1, 23, -1) if words[i].endswith((",", ";", ":"))), None)
            count = boundary + 1 if boundary is not None and len(words) > 40 else limit
            passages.append(" ".join(words[:count]))
            words = words[count:]
    if len(passages) > len(draft):
        raise RuntimeError(f"Story needs {len(passages)} scenes but only {len(draft)} video panels were approved")
    if progress.get("passage_version") != 2:
        progress["passage_version"] = 2
        progress.pop("scene_ids", None)
        _save_json(progress_path, progress)
    scene_ids = progress.get("scene_ids", [])
    for start in range(len(scene_ids), len(passages), 8):
        batch = passages[start:start + 8]
        response = _ask(
            f"Match these {len(batch)} numbered spoken passages to exactly {len(batch)} approved video scenes. "
            "The passages are final audio; do not rewrite them. Return one scene ID per passage, strictly "
            "increasing, greater than the previous scene. Use verified beats and dialogue to match events. "
            "Skip panels that add no story. Return JSON {\"scene_ids\":[1,3,5]}.\n"
            f"Previous scene: {scene_ids[-1] if scene_ids else 0}\n"
            f"Passages: {json.dumps([{'number': start + i + 1, 'text': text} for i, text in enumerate(batch)], ensure_ascii=False)}\n"
            f"Approved scenes: {json.dumps([{'scene': i + 1, 'beat': notes[x['story_panel'] - 1]['beat'], 'ocr': x.get('ocr_text', '')} for i, x in enumerate(draft) if i + 1 > (scene_ids[-1] if scene_ids else 0)], ensure_ascii=False)}",
            role="narration",
        )
        matches = response.get("scene_ids")
        if not isinstance(matches, list) or len(matches) != len(batch):
            raise RuntimeError(f"Scene matcher returned {len(matches) if isinstance(matches, list) else 0} "
                               f"matches for passages {start + 1}-{start + len(batch)}")
        try:
            matches = [int(value) for value in matches]
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Scene matcher returned a nonnumeric scene") from exc
        if any(not 1 <= value <= len(draft) for value in matches):
            raise RuntimeError("Scene matcher returned an unknown scene")
        for offset, requested in enumerate(matches):
            latest = len(draft) - (len(passages) - start - offset - 1)
            scene_ids.append(min(latest, max((scene_ids[-1] + 1) if scene_ids else 1, requested)))
        progress["scene_ids"] = scene_ids
        _save_json(progress_path, progress)
    polished = []
    for text, scene_id in zip(passages, scene_ids):
        original = draft[scene_id - 1]
        needed_sec = math.ceil(len(text.split()) * 60 / SPEAKING_WPM) + 1
        polished.append({**original, "panel": len(polished) + 1, "script": text,
                         "target_sec": max(original["target_sec"], needed_sec)})
    return polished, progress["story"]
