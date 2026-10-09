import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.series_memory import prior_memory, sync_series_memory


class SeriesMemoryTest(unittest.TestCase):
    def test_backfills_prior_chapter_and_rebuilds_after_source_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number in (1, 2):
                data = root / "chapters" / f"story-ch{number}" / "data"
                data.mkdir(parents=True)
                (data / "script.json").write_text(json.dumps([
                    {"script": f"Renee helps him in chapter {number}.", "summary": "Renee helps him.", "ocr_text": ""}
                ]), encoding="utf-8")
            memory = root / "data"
            memory.mkdir()
            (memory / "story_bible.json").write_text(json.dumps({"rolling_summary": "old memory"}), encoding="utf-8")
            calls = []

            def answer(prompt, images=(), role="story-analysis"):
                calls.append(prompt)
                number = 1 if "Chapter: story-ch1" in prompt else 2
                return {"summary": [f"Chapter {number} event."],
                        "rolling_summary": f"Story through chapter {number}.",
                        "characters": [{"id": "c1", "name": "Renee", "role": "saintess",
                                        "aliases": [], "relationships": {}, "review": False}],
                        "open_threads": ["Will he survive?"],
                        "timeline_events": [f"Chapter {number} event."]}

            with patch("core.series_memory._ask", side_effect=answer):
                first = sync_series_memory(root, stop_before="story-ch2")
                self.assertEqual([x["id"] for x in first["chapters"]], ["story-ch1"])
                self.assertEqual(prior_memory(first, "story-ch2")["rolling_summary"], "Story through chapter 1.")
                second = sync_series_memory(root, through="story-ch2")
                self.assertEqual([x["id"] for x in second["chapters"]], ["story-ch1", "story-ch2"])
                self.assertEqual(prior_memory(second, "story-ch2")["rolling_summary"], "Story through chapter 1.")
                sync_series_memory(root, through="story-ch2")
                self.assertEqual(len(calls), 2)
                script = root / "chapters" / "story-ch1" / "data" / "script.json"
                script.write_text(script.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                sync_series_memory(root, through="story-ch2")
            self.assertEqual(len(calls), 4)
            self.assertTrue((memory / "story_bible.legacy.json").exists())
