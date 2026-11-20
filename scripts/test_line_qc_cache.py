"""Tests for the per-line listen-back cache (opencut_ptc.textts_check_cached). No textts needed."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import opencut_ptc  # noqa: E402


class LineCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "x.qc-lines.json"
        self.sent: list[str] = []
        self.readings: dict[str, str] = {}
        self._orig_check = opencut_ptc.textts_check_audio
        self._orig_readings = opencut_ptc.lesson_qc.textts_readings
        opencut_ptc.textts_check_audio = self.fake_check
        opencut_ptc.lesson_qc.textts_readings = lambda url: dict(self.readings)

    def tearDown(self):
        opencut_ptc.textts_check_audio = self._orig_check
        opencut_ptc.lesson_qc.textts_readings = self._orig_readings
        self.tmp.cleanup()

    def fake_check(self, script, roles, threshold):
        lines = [l for l in script.splitlines() if l.strip()]
        self.sent.append(script)
        return {"results": [{"id": f"L{i + 1:03d}", "display": l, "heard": l, "score": 1.0, "ok": True}
                            for i, l in enumerate(lines)]}

    def check(self, script):
        return opencut_ptc.textts_check_cached(script, None, "N4", 0.9, self.cache)

    def test_first_run_checks_all_lines(self):
        result = self.check("[1] 一つ目。\n[2] 二つ目。\n[1] 三つ目。\n")
        self.assertEqual(result["checked"], 3)
        self.assertEqual(result["sent"], 3)
        self.assertEqual(len(self.sent), 1)

    def test_edited_line_is_the_only_one_sent(self):
        self.check("[1] 一つ目。\n[2] 二つ目。\n[1] 三つ目。\n")
        self.sent.clear()
        result = self.check("[1] 一つ目。\n[2] 二つ目を変えた。\n[1] 三つ目。\n")
        self.assertEqual(self.sent, ["[2] 二つ目を変えた。\n"])
        self.assertEqual(result["cached"], 2)
        self.assertEqual(result["results"][1]["display"], "[2] 二つ目を変えた。")

    def test_unchanged_script_sends_nothing(self):
        script = "[1] 一つ目。\n[2] 二つ目。\n"
        self.check(script)
        self.sent.clear()
        self.assertEqual(self.check(script)["sent"], 0)
        self.assertEqual(self.sent, [])

    def test_taught_reading_rechecks_only_lines_with_that_word(self):
        script = "[1] 日本へ行きます。\n[2] 図書館へ行きます。\n"
        self.check(script)
        self.readings = {"日本": "にほん"}
        self.sent.clear()
        self.check(script)
        self.assertEqual(self.sent, ["[1] 日本へ行きます。\n"])

    def test_pause_lines_are_not_sent(self):
        self.check("[1] 一つ目。\n[pause=500]\n[2] 二つ目。\n")
        self.assertEqual(self.sent, ["[1] 一つ目。\n[2] 二つ目。\n"])


if __name__ == "__main__":
    unittest.main()
