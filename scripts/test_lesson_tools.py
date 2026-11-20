"""Tests for lesson_qc.py, lesson_audio.py and the lesson-script parser in opencut_ptc.py.

  python -m unittest scripts/test_lesson_tools.py
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lesson_qc  # noqa: E402
import opencut_ptc  # noqa: E402


class Pronunciation(unittest.TestCase):
    def test_same_sentence_is_close_and_other_one_is_not(self):
        text = "図書館{としょかん}へ行{い}きます。"
        self.assertGreater(lesson_qc.similarity(text, "図書館へ行きます"), 0.9)
        self.assertGreater(lesson_qc.similarity(text, "としょかんへいきます"), 0.9)
        self.assertLess(lesson_qc.similarity(text, "多少かへ行"), lesson_qc.THRESHOLD)
        self.assertEqual(lesson_qc.similarity(text, ""), 0.0)


class Layout(unittest.TestCase):
    def test_dark_text_outside_the_safe_area_is_reported(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            good = Image.new("RGB", (1920, 1080), (255, 240, 240))
            ImageDraw.Draw(good).rectangle((200, 100, 900, 300), fill=(43, 58, 103))
            good.save(Path(tmp) / "01-title-cue0.png")
            self.assertEqual(lesson_qc.layout(Path(tmp), (90, 40, 1830, 540)), 0)
            bad = Image.new("RGB", (1920, 1080), (255, 240, 240))
            ImageDraw.Draw(bad).rectangle((200, 700, 900, 800), fill=(43, 58, 103))
            bad.save(Path(tmp) / "02-grammar-cue1.png")
            self.assertEqual(lesson_qc.layout(Path(tmp), (90, 40, 1830, 540)), 1)


class LessonScript(unittest.TestCase):
    def test_chapters_translation_and_plain_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.script.vi.txt"
            path.write_text(
                "# comment\n## Mở bài\n[1] こんにちは。 // Xin chào.\n[pause=500]\n## Hội thoại\n[2] はい。 // Vâng.\n[3] いいえ。 // Không.\n",
                encoding="utf-8",
            )
            plain, translated, chapters = opencut_ptc.parse_lesson_script(path)
            self.assertEqual(plain, "[1] こんにちは。\n[pause=500]\n[2] はい。\n[3] いいえ。\n")
            self.assertIn("// Vâng.", translated)
            self.assertNotIn("##", translated)
            self.assertEqual(chapters, [("Mở bài", 0), ("Hội thoại", 1)])


if __name__ == "__main__":
    unittest.main()
