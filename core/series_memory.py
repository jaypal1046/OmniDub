"""Build one persistent character and plot map from completed chapters."""

import copy
import hashlib
import json
import re
from pathlib import Path

from .story_pipeline import _ask, _save_json


def _chapter_order(name):
    match = re.search(r"-ch(\d+)$", name)
    return (int(match.group(1)), name) if match else (10**9, name)


def prior_memory(bible, chapter_id):
    chapters = bible.get("chapters", [])
    for index, chapter in enumerate(chapters):
        if chapter.get("id") == chapter_id:
            source = chapter["before"]
            chapters = chapters[:index]
            break
    else:
        source = bible
    return {"characters": copy.deepcopy(source.get("characters", [])),
            "open_threads": copy.deepcopy(source.get("open_threads", [])),
            "timeline": copy.deepcopy(source.get("timeline", [])),
            "rolling_summary": source.get("rolling_summary", ""),
            "chapters": copy.deepcopy(chapters)}


def sync_series_memory(series_dir, stop_before=None, through=None):
    series = Path(series_dir)
    path = series / "data" / "story_bible.json"
    chapters_dir = series / "chapters"
    available = sorted((folder for folder in chapters_dir.iterdir() if folder.is_dir()),
                       key=lambda folder: _chapter_order(folder.name)) if chapters_dir.exists() else []
    if stop_before:
        available = [folder for folder in available if _chapter_order(folder.name) < _chapter_order(stop_before)]
    if through:
        available = [folder for folder in available if _chapter_order(folder.name) <= _chapter_order(through)]
    available = [folder for folder in available if (folder / "data" / "script.json").exists()]

    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if existing.get("memory_version") == 2:
        bible = existing
    else:
        if path.exists():
            backup = path.with_name("story_bible.legacy.json")
            if not backup.exists():
                backup.write_bytes(path.read_bytes())
        bible = {"memory_version": 2, "characters": [], "chapters": [], "open_threads": [],
                 "timeline": [], "rolling_summary": ""}

    sources = []
    for folder in available:
        script_path = folder / "data" / "script.json"
        narrative_path = folder / "data" / "story_narrative.txt"
        script_bytes = script_path.read_bytes()
        narrative_bytes = narrative_path.read_bytes() if narrative_path.exists() else b""
        sources.append((folder, hashlib.sha256(script_bytes + narrative_bytes).hexdigest(),
                        json.loads(script_bytes.decode("utf-8")), narrative_bytes.decode("utf-8")))

    for index, (folder, digest, scenes, narrative) in enumerate(sources):
        saved = bible["chapters"][index] if index < len(bible["chapters"]) else None
        if saved and saved.get("id") == folder.name and saved.get("source_hash") == digest:
            continue
        if saved:
            before = saved.get("before")
            if not isinstance(before, dict) or "characters" not in before:
                raise ValueError(f"Cannot rebuild memory before {folder.name}; missing snapshot")
            bible.update(copy.deepcopy(before))
            bible["chapters"] = bible["chapters"][:index]
        for chapter_folder, chapter_hash, chapter_scenes, chapter_story in sources[index:]:
            before = {key: copy.deepcopy(bible[key]) for key in
                      ("characters", "open_threads", "timeline", "rolling_summary")}
            result = _ask(
                "Update the series story memory from this completed chapter. Track story facts across chapters. "
                "Return JSON object with summary (5-8 short sentences), rolling_summary (story so far, at most "
                "180 words), characters (important recurring people with id, name or null, role, aliases, "
                "relationships keyed by character id, review boolean), open_threads (only unresolved promises, "
                "mysteries, or conflicts), and timeline_events (3-6 major event strings). "
                "Reuse an existing character id when identity is supported. Give a new id cN only for a new "
                "important character. Treat uncertain names and OCR as uncertain; do not invent relationships. "
                "Remove threads that this chapter resolves. Ignore panel art and scanlation credits.\n"
                f"Previous memory: {json.dumps({key: bible[key] for key in ('rolling_summary', 'characters', 'open_threads')}, ensure_ascii=False)}\n"
                f"Chapter: {chapter_folder.name}\n"
                f"Narrative: {chapter_story[:12000]}\n"
                f"Scenes: {json.dumps([{'beat': x.get('summary', ''), 'spoken': x.get('script', ''), 'ocr': x.get('ocr_text', '')} for x in chapter_scenes], ensure_ascii=False)}"
            )
            if isinstance(result.get("summary"), str):
                result["summary"] = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", result["summary"])
                                     if part.strip()][:8]
            if (not isinstance(result.get("summary"), list) or not isinstance(result.get("rolling_summary"), str)
                    or not isinstance(result.get("characters"), list)
                    or not isinstance(result.get("open_threads"), list)
                    or not isinstance(result.get("timeline_events"), list)):
                raise RuntimeError(f"Gemini returned incomplete memory for {chapter_folder.name}: "
                                   f"{[(key, type(value).__name__) for key, value in result.items()]}")
            if not result["open_threads"]:
                followup = _ask(
                    "Find unresolved promises, mysteries, threats, or survival questions at this chapter's end. "
                    "Return JSON object {\"open_threads\":[\"...\"]}; use [] only if every such thread is resolved. "
                    "Use facts only.\n"
                    f"Story so far: {result['rolling_summary']}\n"
                    f"Final scenes: {json.dumps([x.get('script', '') for x in chapter_scenes[-8:]], ensure_ascii=False)}"
                )
                if isinstance(followup.get("open_threads"), list):
                    result["open_threads"] = followup["open_threads"]
            characters = result["characters"]
            ids = [person.get("id") for person in characters if isinstance(person, dict)]
            if len(ids) != len(characters) or len(ids) != len(set(ids)) or any(
                    not isinstance(identity, str) or not re.fullmatch(r"c\d+", identity) for identity in ids):
                raise RuntimeError(f"Gemini returned invalid character IDs for {chapter_folder.name}")
            previous = {person["id"]: person for person in bible["characters"]}
            for person in characters:
                older = previous.get(person["id"], {})
                person["looks"] = older.get("looks", [])
                person["first_seen"] = older.get("first_seen", chapter_folder.name)
                person["relations"] = person.pop("relationships", person.get("relations", {}))
                if not isinstance(person["relations"], dict):
                    person["relations"] = {}
                person["aliases"] = person.get("aliases", []) if isinstance(person.get("aliases"), list) else []
                person["role"] = person.get("role") or "unknown"
                person["review"] = not person.get("name") or bool(person.get("review", False))
            bible["characters"] = characters
            bible["open_threads"] = [thread for thread in result["open_threads"] if isinstance(thread, str)]
            bible["timeline"].extend({"chapter": chapter_folder.name, "event": event}
                                     for event in result["timeline_events"] if isinstance(event, str))
            bible["rolling_summary"] = result["rolling_summary"]
            bible["chapters"].append({"id": chapter_folder.name, "summary": result["summary"],
                                      "source_hash": chapter_hash, "before": before})
            _save_json(str(path), bible)
            print(f"🧠 Series memory updated: {chapter_folder.name}", flush=True)
        break
    return bible
