"""Two-pass manhwa understanding and narration with project story memory."""

import base64
import hashlib
import io
import json
import os
import tempfile
import time
from pathlib import Path

import requests
from PIL import Image

from .comic_script import clean_json_response


STORY_MODEL = "gemini-3.5-flash-lite"
SPEAKING_WPM = 145
PANEL_SECONDS = (4, 6, 9, 13)
ANALYSIS_BATCH_SIZE = 6
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


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
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Story analysis needs GEMINI_API_KEY")
    parts = [{"text": prompt}]
    for label, path in images:
        for part_label, data in _image_parts(path, label):
            parts.extend(({"text": part_label}, {"inline_data": {"mime_type": "image/jpeg", "data": data}}))
    if sum(len(part.get("inline_data", {}).get("data", "")) for part in parts) > 18_000_000:
        raise ValueError("Panel images exceed Gemini's inline request limit; split the panel first")
    for attempt in range(3):
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{STORY_MODEL}:generateContent",
                headers={"x-goog-api-key": key},
                json={"system_instruction": {"parts": [{"text": _skill_text(role)}]},
                      "contents": [{"parts": parts}], "generationConfig": {"response_mime_type": "application/json"}},
                timeout=(10, 120),
            )
        except requests.RequestException:
            if attempt == 2:
                raise RuntimeError("Gemini request failed after 3 attempts") from None
        else:
            if response.ok:
                try:
                    result = clean_json_response(response.json()["candidates"][0]["content"]["parts"][0]["text"])
                    if isinstance(result, dict):
                        return result
                except (KeyError, IndexError, ValueError):
                    pass
                if attempt == 2:
                    raise RuntimeError("Gemini returned invalid story JSON")
                time.sleep(2 ** attempt)
                continue
            if response.status_code not in (408, 429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError(f"Gemini HTTP {response.status_code}")
        time.sleep(2 ** attempt)


def _save_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=os.path.dirname(path), delete=False) as out:
        json.dump(value, out, indent=2, ensure_ascii=False)
        temporary = out.name
    os.replace(temporary, path)


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
    crops_dir = os.path.join(story_dir, "data", "character_crops")
    os.makedirs(crops_dir, exist_ok=True)
    batch_facts = {}
    for position, panel in enumerate(panels[len(notes):], len(notes) + 1):
        if len(notes) >= 12 and len(notes) % 12 == 0 and summary_through < len(notes):
            summary = _ask(
                "Summarize these factual chapter beats into one short paragraph for following-panel analysis. "
                "Preserve named characters, causality, unresolved threads, and uncertainty. Add no new facts. "
                "Return JSON object {\"summary\":\"...\"}.\n"
                f"Earlier chapter summary: {chapter_so_far}\n"
                f"New beats: {json.dumps([note['beat'] for note in notes[-12:]], ensure_ascii=False)}"
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
                "Do not invent actions, identities or motives. Return JSON object {\"panels\": [one object per input "
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
        if panel.get("ocr_ignore") or panel.get("ocr_flagged") or fact.get("needs_image"):
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
        batch = notes[start:start + 12]
        batch_plan = plan[start:start + 12]
        narration = _ask(
            "You are a YouTube manhwa recap storyteller. Write voiceover from FACTS ONLY. You have no images. "
            "Tell what happened and why it matters; never describe the picture or clothing. Use names only when confirmed. "
            "Connect relevant earlier events. Keep one consistent dramatic conversational voice. Open with a hook only at chapter start, "
            "end with a supported consequence or cliffhanger only at chapter end. Vary pace. Never invent events or motives. "
            "Return JSON object: {\"lines\":[{\"panel\":1,\"text\":\"...\"},...]}. "
            "Provide exactly one short spoken line for each INCLUDE panel, and none for STORY_ONLY panels. "
            "Each line MUST fit its max_words and max_chars. Weave relevant STORY_ONLY facts into the next INCLUDE line. "
            "Give major events more space and make filler brief. Use reviewed OCR to preserve exact dialogue meaning, "
            "but treat analyst beats as the story facts; ignore watermarks and do not recite every bubble. "
            f"Additional style instruction: {custom_prompt or 'dramatic, clear, fast'}\n"
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
                "Shorten these spoken manhwa recap lines to strictly less than their max_words and max_chars "
                "without adding facts or losing the key event. "
                "Return JSON object {\"lines\":[{\"panel\":1,\"text\":\"...\"}]}.\n"
                f"Lines and limits: {json.dumps([{**item, 'text': batch_lines.get(item['panel'], '')} for item in overlong], ensure_ascii=False)}",
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
            if len(text.split()) > item["max_words"] or len(text) > item["max_chars"]:
                raise RuntimeError(f"Panel {item['panel']} exceeds its narration time budget")
            by_panel[item["panel"]] = text
    for note in notes:
        if note["action"] == "INCLUDE" and not str(by_panel.get(note["panel"], "")).strip():
            raise RuntimeError(f"Narrator omitted panel {note['panel']}")

    for item in plan:
        item["words"] = len(by_panel.get(item["panel"], "").split())
        item["estimated_sec"] = round(item["words"] * 60 / SPEAKING_WPM + (1 if item["words"] else 0), 1)
    plan_file["estimated_total_sec"] = round(sum(item["estimated_sec"] for item in plan), 1)
    _save_json(plan_path, plan_file)

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
