"""Keep chapter artifacts and shared story memory inside one series workspace."""

import json
import re
import shutil
from pathlib import Path


def prepare_series_workspace(output_root, series_name, current_chapter):
    root = Path(output_root).resolve()
    series = (root / series_name).resolve()
    chapters = series / "chapters"
    chapters.mkdir(parents=True, exist_ok=True)

    old_memory = series / "_story" / "data"
    new_memory = series / "data"
    if old_memory.exists() and not new_memory.exists():
        shutil.move(str(old_memory), str(new_memory))
        if not any(old_memory.parent.iterdir()):
            old_memory.parent.rmdir()

    for source in root.iterdir():
        if (not source.is_dir() or not (source.name == current_chapter or
                re.fullmatch(re.escape(series_name) + r"-ch\d+", source.name))):
            continue
        if source.resolve().parent != root or source.resolve() == series:
            raise ValueError(f"Chapter path escapes output folder: {source}")
        destination = chapters / source.name
        if destination.exists():
            raise FileExistsError(f"Both legacy and series chapter folders exist: {source} and {destination}")
        if destination.resolve().parent != chapters.resolve():
            raise ValueError(f"Chapter destination escapes series folder: {destination}")
        old_path = str(source.resolve())
        shutil.move(str(source), str(destination))
        print(f"📚 Moved {source.name} into series workspace", flush=True)
        new_path = str(destination.resolve())
        for path in destination.rglob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))

            def rebase(value):
                if isinstance(value, str):
                    return new_path + value[len(old_path):] if value.startswith(old_path) else value
                if isinstance(value, list):
                    return [rebase(item) for item in value]
                if isinstance(value, dict):
                    return {key: rebase(item) for key, item in value.items()}
                return value

            updated = rebase(data)
            if updated != data:
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_text(json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8")
                temporary.replace(path)
    return series, chapters / current_chapter
