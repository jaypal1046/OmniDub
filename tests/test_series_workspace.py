import json
import tempfile
import unittest
from pathlib import Path

from core.series_workspace import prepare_series_workspace


class SeriesWorkspaceTest(unittest.TestCase):
    def test_moves_legacy_chapters_and_rebases_saved_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "sample-ch1"
            (old / "data").mkdir(parents=True)
            (old / "data" / "script.json").write_text(
                json.dumps({"image_path": str(old / "images" / "panel.png")}), encoding="utf-8")
            memory = root / "sample" / "_story" / "data"
            memory.mkdir(parents=True)
            (memory / "story_bible.json").write_text("{}", encoding="utf-8")

            series, chapter = prepare_series_workspace(root, "sample", "sample-ch1")

            self.assertEqual(chapter, series / "chapters" / "sample-ch1")
            self.assertFalse(old.exists())
            self.assertTrue((series / "data" / "story_bible.json").exists())
            saved = json.loads((chapter / "data" / "script.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["image_path"], str(chapter / "images" / "panel.png"))
            self.assertEqual(prepare_series_workspace(root, "sample", "sample-ch1")[1], chapter)
