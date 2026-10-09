import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core.comic_animator import get_audio_duration_sec
from core.comic_script import get_active_vision_provider
from core.story_pipeline import _ask, _image_parts, _reference_path, build_story_script, polish_story_script


class StoryPipelineTest(unittest.TestCase):
    def test_story_edit_uses_story_as_audio_and_skips_filler_panels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            draft = [{"panel": number, "story_panel": number, "script": "A hand is shown.", "ocr_text": "", "target_sec": 4}
                     for number in range(1, 14)]
            notes = [{"panel": number, "beat": "She finds a clue.", "action": "INCLUDE"}
                     for number in range(1, 14)]
            plan = {"panels": [{"max_words": 10} for _ in draft]}
            calls = []

            def answer(prompt, images=(), role="story-analysis"):
                self.assertEqual(role, "story-analysis" if "CAUSAL STORY OUTLINE" in prompt else "narration")
                calls.append(prompt)
                if "CAUSAL STORY OUTLINE" in prompt:
                    return {"events": ["She finds a clue.", "She follows it."]}
                if "Write the complete chapter" in prompt:
                    return {"story": "She finds a clue and follows it to its source."}
                if "Rewrite this draft" in prompt:
                    return {"story": "She follows the clue to its source."}
                if len(calls) == 4:
                    raise RuntimeError("temporary failure")
                return {"scene_ids": [7]}

            progress = str(root / "edit_progress.json")
            with patch("core.story_pipeline._ask", side_effect=answer):
                with self.assertRaisesRegex(RuntimeError, "temporary failure"):
                    polish_story_script(draft, notes, plan, {}, progress)
                edited, story = polish_story_script(draft, notes, plan, {}, progress)
            self.assertEqual(len(calls), 5)
            self.assertEqual(len(edited), 1)
            self.assertEqual(edited[0]["script"], "She follows the clue to its source.")
            self.assertEqual(edited[0]["story_panel"], 7)
            self.assertEqual(edited[0]["panel"], 1)
            self.assertIn("follows the clue to its source", story)
            self.assertEqual(draft[0]["script"], "A hand is shown.")

    def test_story_edit_never_reuses_visual_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            draft = [{"panel": 1, "story_panel": 1, "script": "A glowing hand is shown.",
                      "ocr_text": "", "target_sec": 4}]
            notes = [{"panel": 1, "beat": "She attempts to heal him.", "action": "INCLUDE"}]
            plan = {"panels": [{"max_words": 5}]}

            def answer(prompt, images=(), role="story-analysis"):
                if "CAUSAL STORY OUTLINE" in prompt:
                    return {"events": ["She heals him."]}
                if "Write the complete chapter" in prompt:
                    return {"story": "She attempts to heal him, although he has little hope."}
                if "Rewrite this draft" in prompt:
                    return {"story": "She attempts to heal him despite his doubts."}
                return {"scene_ids": [1]}

            with patch("core.story_pipeline._ask", side_effect=answer):
                edited, _ = polish_story_script(draft, notes, plan, {}, str(Path(directory) / "progress.json"))
            self.assertEqual(edited[0]["script"], "She attempts to heal him despite his doubts.")

    def test_story_edit_aligns_scenes_when_story_panel_numbers_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            draft = [{"panel": 1, "story_panel": 1, "script": "A door opens.", "ocr_text": "", "target_sec": 4},
                     {"panel": 2, "story_panel": 3, "script": "A letter appears.", "ocr_text": "", "target_sec": 4}]
            notes = [{"panel": 1, "beat": "She enters.", "action": "INCLUDE"},
                     {"panel": 2, "beat": "The sender remains unknown.", "action": "STORY_ONLY"},
                     {"panel": 3, "beat": "She finds a letter.", "action": "INCLUDE"}]
            plan = {"panels": [{"max_words": 10} for _ in notes]}
            attempts = []

            def answer(prompt, images=(), role="story-analysis"):
                if "CAUSAL STORY OUTLINE" in prompt:
                    return {"events": ["She finds a letter."]}
                if "Write the complete chapter" in prompt:
                    return {"story": "She enters and finds a mysterious letter."}
                if "Rewrite this draft" in prompt:
                    return {"story": "She finds a mysterious letter after entering."}
                attempts.append(prompt)
                return {"scene_ids": [2]}

            with patch("core.story_pipeline._ask", side_effect=answer):
                edited, _ = polish_story_script(draft, notes, plan, {}, str(Path(directory) / "progress.json"))
            self.assertEqual([x["script"] for x in edited], ["She finds a mysterious letter after entering."])
            self.assertEqual(edited[0]["story_panel"], 3)
            self.assertEqual(len(attempts), 1)

    def test_story_cleanup_resumes_from_saved_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            draft = [{"panel": 1, "story_panel": 1, "script": "A hand is shown.",
                      "ocr_text": "", "target_sec": 4}]
            notes = [{"panel": 1, "beat": "She helps him.", "action": "INCLUDE"}]
            plan = {"panels": [{"max_words": 10}]}
            calls = []

            def answer(prompt, images=(), role="story-analysis"):
                calls.append(prompt)
                if "CAUSAL STORY OUTLINE" in prompt:
                    return {"events": ["She helps him."]}
                if "Write the complete chapter" in prompt:
                    return {"story": "A hand is shown as she helps him."}
                if "Rewrite this draft" in prompt:
                    if len(calls) == 3:
                        raise RuntimeError("temporary failure")
                    return {"story": "She helps him."}
                return {"scene_ids": [1]}

            progress = str(Path(directory) / "progress.json")
            with patch("core.story_pipeline._ask", side_effect=answer):
                with self.assertRaisesRegex(RuntimeError, "temporary failure"):
                    polish_story_script(draft, notes, plan, {}, progress)
                _, story = polish_story_script(draft, notes, plan, {}, progress)
            self.assertEqual(story, "She helps him.")
            self.assertEqual(sum("Write the complete chapter" in call for call in calls), 1)

    def test_missing_audio_cannot_become_three_second_clip(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "missing or empty"):
                get_audio_duration_sec(str(Path(directory) / "missing.mp3"))

    def test_legacy_vision_selects_gemini_without_ox_probe(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test", "ALPHA_OX_API_KEY": "unused"}), patch(
            "core.comic_script._SELECTED_VISION_PROVIDER", None
        ), patch("core.comic_script.requests.post") as post:
            self.assertEqual(get_active_vision_provider(), "gemini")
            post.assert_not_called()

    def test_gemini_key_uses_fast_story_model(self):
        class Response:
            ok = True

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": '{"beat":"ok"}'}]}}]}

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test"}), patch("core.story_pipeline.requests.post", return_value=Response()) as post:
            self.assertEqual(_ask("facts"), {"beat": "ok"})
        self.assertIn("gemini-3.5-flash-lite", post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["headers"], {"x-goog-api-key": "test"})
        self.assertIn("story analyst", post.call_args.kwargs["json"]["system_instruction"]["parts"][0]["text"])

    def test_narrator_uses_its_skill_and_rejects_images(self):
        class Response:
            ok = True

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": '{"lines":[]}'}]}}]}

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test"}), patch(
            "core.story_pipeline.requests.post", return_value=Response()
        ) as post:
            with self.assertRaisesRegex(ValueError, "Narration must use beat notes"):
                _ask("narrate", [("panel", "panel.png")], role="narration")
            post.assert_not_called()
            self.assertEqual(_ask("narrate", role="narration"), {"lines": []})
            self.assertIn("recap storyteller", post.call_args.kwargs["json"]["system_instruction"]["parts"][0]["text"])

    def test_transient_http_error_retries(self):
        class Response:
            def __init__(self, status):
                self.status_code = status
                self.ok = status == 200

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": '{"beat":"ok"}'}]}}]}

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test"}), patch(
            "core.story_pipeline.requests.post", side_effect=[Response(503), Response(200)]
        ) as post, patch("core.story_pipeline.time.sleep"):
            self.assertEqual(_ask("facts"), {"beat": "ok"})
            self.assertEqual(post.call_count, 2)

    def test_rate_limit_waits_for_retry_after(self):
        class Response:
            def __init__(self, status):
                self.status_code = status
                self.ok = status == 200
                self.headers = {"Retry-After": "3"} if status == 429 else {}

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": '{"beat":"ok"}'}]}}]}

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test"}), patch(
            "core.story_pipeline.requests.post", side_effect=[Response(429), Response(200)]
        ) as post, patch("core.story_pipeline.time.sleep") as sleep:
            self.assertEqual(_ask("facts"), {"beat": "ok"})
            self.assertEqual(post.call_count, 2)
            sleep.assert_called_once_with(3.0)

    def test_rate_limit_reads_gemini_retry_delay(self):
        class RateLimited:
            ok = False
            status_code = 429
            headers = {}

            def json(self):
                return {"error": {"details": [{"retryDelay": "12s"}]}}

        class Success:
            ok = True

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": '{"beat":"ok"}'}]}}]}

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test"}), patch(
            "core.story_pipeline.requests.post", side_effect=[RateLimited(), Success()]
        ), patch("core.story_pipeline.time.sleep") as sleep:
            self.assertEqual(_ask("facts"), {"beat": "ok"})
            sleep.assert_called_once_with(12.0)

    def test_request_failure_reports_cause(self):
        import requests

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test"}), patch(
            "core.story_pipeline.requests.post", side_effect=requests.ReadTimeout("private details")
        ), patch("core.story_pipeline.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "after 3 attempts \\(ReadTimeout\\)"):
                _ask("facts")

    def test_resume_reuses_completed_narration_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panels = []
            for number in range(13):
                path = root / f"{number}.png"
                Image.new("RGB", (10, 10), "red").save(path)
                panels.append({"file": path.name, "image_path": str(path), "action": "INCLUDE", "ocr_text": ""})
            narration_calls = []

            def answer(prompt, images=(), role="story-analysis"):
                if "factual manhwa story analyst" in prompt:
                    first = int(Path(images[0][1]).stem) + 1
                    return {"panels": [{"panel": number, "beat": "An event.", "characters": [],
                                        "new_threads": [], "resolved_threads": [], "timeline_event": None}
                                       for number in range(first, min(first + 6, 14))]}
                if "recap storyteller" in prompt:
                    narration_calls.append(prompt)
                    if len(narration_calls) == 2:
                        raise RuntimeError("temporary failure")
                    first = 1 if "panels 1-12" in prompt else 13
                    return {"lines": [{"panel": number, "text": "An event occurred."}
                                      for number in range(first, min(first + 12, 14))]}
                if "Summarize these factual" in prompt:
                    return {"summary": "Events so far."}
                return {"summary": ["Events occurred."], "rolling_summary": "Events occurred.", "relations": []}

            with patch("core.story_pipeline._ask", side_effect=answer):
                with self.assertRaisesRegex(RuntimeError, "temporary failure"):
                    build_story_script(str(root), "chapter", panels)
                notes, lines = build_story_script(str(root), "chapter", panels)
            self.assertEqual(len(notes), 13)
            self.assertEqual(len(lines), 13)
            self.assertEqual(len(narration_calls), 3)
            self.assertFalse((root / "data" / "story_progress.json").exists())

    def test_invalid_model_json_retries(self):
        class Response:
            ok = True

            def __init__(self, text):
                self.text = text

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": self.text}]}}]}

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test"}), patch(
            "core.story_pipeline.requests.post", side_effect=[Response("not json"), Response('{"beat":"ok"}')]
        ) as post, patch("core.story_pipeline.time.sleep"):
            self.assertEqual(_ask("facts"), {"beat": "ok"})
            self.assertEqual(post.call_count, 2)

    def test_tall_panel_sends_overview_then_ordered_detail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tall.png"
            Image.new("RGB", (600, 2500), "blue").save(path)
            parts = _image_parts(str(path), "Current panel")
            self.assertEqual([label for label, _ in parts], [
                "Current panel overview", "Current panel detail 1/3 (top to bottom)",
                "Current panel detail 2/3 (top to bottom)", "Current panel detail 3/3 (top to bottom)",
            ])
            self.assertEqual(len(_image_parts(str(path), "Previous panel context")), 1)

    def test_story_reference_stays_inside_story_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside.png"
            Image.new("RGB", (10, 10), "red").save(outside)
            folder = root / "story"
            folder.mkdir()
            self.assertIsNone(_reference_path(str(folder), {"ref_image": "../outside.png"}))

    def test_request_labels_panel_and_reference_images(self):
        class Response:
            ok = True

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": '{"beat":"ok"}'}]}}]}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "panel.png"
            Image.new("RGB", (600, 2500), "blue").save(path)
            with patch.dict("os.environ", {"GEMINI_API_KEY": "test"}), patch(
                "core.story_pipeline.requests.post", return_value=Response()
            ) as post:
                _ask("facts", [("Current panel", str(path)), ("Known character c1", str(path))])
            parts = post.call_args.kwargs["json"]["contents"][0]["parts"]
            labels = [part["text"] for part in parts if "text" in part]
            self.assertEqual(labels, ["facts", "Current panel overview",
                                      "Current panel detail 1/3 (top to bottom)",
                                      "Current panel detail 2/3 (top to bottom)",
                                      "Current panel detail 3/3 (top to bottom)",
                                      "Known character c1 overview"])

    def test_ox_key_is_not_used(self):
        with patch.dict("os.environ", {"ALPHA_OX_API_KEY": "unused"}, clear=True), patch("core.story_pipeline.requests.post") as post:
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                _ask("facts")
            post.assert_not_called()

    def test_chapters_share_memory_and_narrator_sees_no_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            story = root / "series"
            image = root / "panel.png"
            Image.new("RGB", (100, 100), "red").save(image)
            calls = []

            def answer(prompt, images=(), role="story-analysis"):
                calls.append((prompt, images))
                if "recap storyteller" in prompt:
                    self.assertEqual(role, "narration")
                if "factual manhwa story analyst" in prompt:
                    return {"panels": [{"panel": 1, "beat": "Jin finds a letter.", "characters": [{"id": "c1" if len(calls) > 3 else None,
                            "name": "Jin", "look": "blue coat" if len(calls) > 3 else "black hair, red vest", "role": "lead", "confidence": 0.9,
                            "bounds": [0.1, 0.1, 0.8, 0.8]}], "new_threads": ["Who sent the letter?"],
                            "resolved_threads": [], "timeline_event": "Jin finds the letter"}]}
                if "recap storyteller" in prompt:
                    self.assertEqual(images, ())
                    return {"lines": [{"panel": 1, "text": "Jin found a letter that could change everything."}]}
                return {"summary": ["Jin finds a letter."], "rolling_summary": "Jin found a mysterious letter.", "relations": []}

            panel = {"file": "panel.png", "image_path": str(image), "ocr_text": "Jin!", "action": "INCLUDE"}
            with patch("core.story_pipeline._ask", side_effect=answer):
                build_story_script(str(root / "chapter1"), "chapter1", [panel], story_dir=str(story))
                build_story_script(str(root / "chapter2"), "chapter2", [panel], story_dir=str(story))

            bible = json.loads((story / "data" / "story_bible.json").read_text(encoding="utf-8"))
            self.assertEqual([chapter["id"] for chapter in bible["chapters"]], ["chapter1", "chapter2"])
            self.assertTrue((story / bible["characters"][0]["looks"][0]["ref_image"]).exists())
            self.assertEqual(len({look["ref_image"] for look in bible["characters"][0]["looks"]}), 2)
            self.assertIn("Jin found a mysterious letter", calls[3][0])
            self.assertEqual(len(calls[3][1]), 2)

    def test_series_memory_is_not_overwritten_by_draft_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            story = root / "series"
            data = story / "data"
            data.mkdir(parents=True)
            bible_path = data / "story_bible.json"
            original = {"memory_version": 2, "characters": [], "chapters": [], "open_threads": [],
                        "timeline": [], "rolling_summary": "Earlier chapter happened."}
            bible_path.write_text(json.dumps(original), encoding="utf-8")
            image = root / "panel.png"
            Image.new("RGB", (10, 10), "red").save(image)
            panel = {"file": "panel.png", "image_path": str(image), "ocr_text": "", "action": "INCLUDE"}

            def answer(prompt, images=(), role="story-analysis"):
                if "factual manhwa story analyst" in prompt:
                    return {"panels": [{"panel": 1, "beat": "She returns.", "characters": [],
                                        "new_threads": [], "resolved_threads": [], "timeline_event": None}]}
                if "recap storyteller" in prompt:
                    return {"lines": [{"panel": 1, "text": "She returns."}]}
                raise AssertionError("Legacy memory writer was called")

            with patch("core.story_pipeline._ask", side_effect=answer):
                build_story_script(str(root / "chapter"), "chapter", [panel], story_dir=str(story))
            self.assertEqual(json.loads(bible_path.read_text(encoding="utf-8")), original)

    def test_resume_starts_at_failed_panel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panels = []
            for number in range(1, 8):
                path = root / f"{number}.png"
                Image.new("RGB", (100, 100), "red").save(path)
                panels.append({"file": path.name, "image_path": str(path), "action": "INCLUDE", "ocr_text": str(number)})
            analyzed = []

            def answer(prompt, images=(), role="story-analysis"):
                if "factual manhwa story analyst" in prompt:
                    analyzed.append(images[0][1])
                    if len(analyzed) == 2:
                        raise RuntimeError("temporary failure")
                    start = int(Path(images[0][1]).stem)
                    return {"panels": [{"panel": number, "beat": "A factual event.", "characters": [],
                            "new_threads": [], "resolved_threads": [], "timeline_event": None}
                            for number in range(start, min(start + 6, 8))]}
                if "recap storyteller" in prompt:
                    return {"lines": [{"panel": number, "text": "An event occurred."} for number in range(1, 8)]}
                return {"summary": ["Two events."], "rolling_summary": "Two events occurred.", "relations": []}

            with patch("core.story_pipeline._ask", side_effect=answer):
                with self.assertRaisesRegex(RuntimeError, "temporary failure"):
                    build_story_script(str(root), "chapter", panels)
                self.assertTrue((root / "data" / "story_progress.json").exists())
                notes, _ = build_story_script(str(root), "chapter", panels)
            self.assertEqual(len(notes), 7)
            self.assertEqual(analyzed, [str(root / "1.png"), str(root / "7.png"), str(root / "7.png")])
            self.assertFalse((root / "data" / "story_progress.json").exists())

    def test_story_importance_sets_dynamic_time_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panels = []
            for number, action in ((1, "INCLUDE"), (2, "INCLUDE"), (3, "STORY_ONLY"), (4, "INCLUDE")):
                path = root / f"{number}.png"
                Image.new("RGB", (100, 100), "red").save(path)
                panels.append({"file": path.name, "image_path": str(path), "action": action, "ocr_text": str(number)})
            rewrites = []

            def answer(prompt, images=(), role="story-analysis"):
                if "factual manhwa story analyst" in prompt:
                    return {"panels": [{"panel": number, "beat": f"Event {number}.",
                            "importance": {1: 0, 2: 3, 3: 2, 4: 1}[number], "characters": [],
                            "new_threads": [], "resolved_threads": [], "timeline_event": None}
                            for number in range(1, 5)]}
                if "recap storyteller" in prompt:
                    return {"lines": [{"panel": 1, "text": "This ordinary moment has far too many extra unnecessary words."},
                                      {"panel": 2, "text": "The secret changes their fate."},
                                      {"panel": 4, "text": "They read the clue."}]}
                if "Shorten these spoken" in prompt:
                    rewrites.append(prompt)
                    return {"lines": [{"panel": 1, "text": "They move on without a word."}]}
                return {"summary": ["Events occurred."], "rolling_summary": "The events occurred.", "relations": []}

            with patch("core.story_pipeline._ask", side_effect=answer):
                _, script = build_story_script(str(root), "chapter", panels)
            plan = json.loads((root / "data" / "story_plan.json").read_text(encoding="utf-8"))
            self.assertEqual([panel["target_sec"] for panel in plan["panels"]], [4, 13, 0, 8])
            self.assertEqual(plan["planned_total_sec"], 25)
            self.assertEqual(set(script), {1, 2, 4})
            self.assertEqual(len(rewrites), 1)

    def test_narration_that_resists_shortening_gets_bounded_extra_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "panel.png"
            Image.new("RGB", (10, 10), "red").save(image)
            panel = {"file": image.name, "image_path": str(image), "action": "INCLUDE", "ocr_text": ""}
            line = "She takes the letter and finally learns who sent it."

            def answer(prompt, images=(), role="story-analysis"):
                if "factual manhwa story analyst" in prompt:
                    return {"panels": [{"panel": 1, "beat": "She learns who sent the letter.",
                                        "importance": 0, "characters": [], "new_threads": [],
                                        "resolved_threads": [], "timeline_event": None}]}
                if role == "narration":
                    return {"lines": [{"panel": 1, "text": line}]}
                return {"summary": ["She learns the sender."], "rolling_summary": "She knows the sender.", "relations": []}

            with patch("core.story_pipeline._ask", side_effect=answer):
                _, script = build_story_script(str(root), "chapter", [panel])
            plan = json.loads((root / "data" / "story_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(script[1], line)
            self.assertEqual(plan["panels"][0]["target_sec"], 6)
            self.assertEqual(plan["planned_total_sec"], 6)

    def test_batch_sees_image_only_panel_and_rechecks_flagged_ocr(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panels = []
            for number, ocr in ((1, "Hello"), (2, "A reply"), (3, "")):
                path = root / f"{number}.png"
                Image.new("RGB", (100, 100), "red").save(path)
                panels.append({"file": path.name, "image_path": str(path), "action": "INCLUDE",
                               "ocr_text": ocr, "ocr_ignore": number == 3, "ocr_flagged": number == 2})
            analysis_images = []
            narrator_prompt = []

            def answer(prompt, images=(), role="story-analysis"):
                if "factual manhwa story analyst" in prompt:
                    analysis_images.append([Path(path).name for _, path in images])
                    return {"panels": [{"panel": number, "beat": f"Event {number}.", "characters": [],
                            "new_threads": [], "resolved_threads": [], "timeline_event": None,
                            "needs_image": False} for number in range(1, 4)]}
                if "Check this panel image" in prompt:
                    analysis_images.append([Path(path).name for _, path in images])
                    return {"beat": "A crash ends the conversation.", "characters": []}
                if "recap storyteller" in prompt:
                    narrator_prompt.append(prompt)
                    return {"lines": [{"panel": number, "text": f"Event {number} happened."}
                                      for number in range(1, 4)]}
                return {"summary": ["Events occurred."], "rolling_summary": "Events occurred.", "relations": []}

            with patch("core.story_pipeline._ask", side_effect=answer):
                notes, _ = build_story_script(str(root), "chapter", panels)
            self.assertEqual(analysis_images, [["1.png", "2.png", "3.png"], ["2.png"]])
            self.assertEqual(notes[1]["beat"], "A crash ends the conversation.")
            self.assertEqual(notes[2]["beat"], "Event 3.")
            self.assertIn('"panel": 1, "text": "Hello"', narrator_prompt[0])
            self.assertIn('"panel": 3, "text": ""', narrator_prompt[0])


if __name__ == "__main__":
    unittest.main()
