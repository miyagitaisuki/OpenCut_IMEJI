"""Tests for the SceneSpec check in opencut_scenes.py (stdlib only; no Claude call)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import opencut_scenes  # noqa: E402


class SceneSpec(unittest.TestCase):
    def test_valid_file_has_no_problems(self):
        good = {"scenes": [{"cue": 0, "template": "title", "title": "Hi"},
                           {"cue": 2, "template": "practice", "question": "q", "options": ["a", "b"], "answer": 1}]}
        self.assertEqual(opencut_scenes.validate_spec(good), [])

    def test_missing_field_is_named(self):
        problems = opencut_scenes.validate_spec({"scenes": [{"cue": 0, "template": "title"}]})
        self.assertIn("$.scenes[0]: missing title", problems)

    def test_bad_enum_is_named(self):
        problems = opencut_scenes.validate_spec({"scenes": [{"cue": 1, "template": "chart", "kind": "pie", "items": [{"label": "a", "value": 1}]}]})
        self.assertTrue(any("kind" in p for p in problems))

    def test_unknown_template_fails(self):
        self.assertTrue(opencut_scenes.validate_spec({"scenes": [{"cue": 0, "template": "video"}]}))

    def test_practice_needs_two_to_four_options(self):
        problems = opencut_scenes.validate_spec({"scenes": [{"cue": 0, "template": "practice", "question": "q", "options": ["a"], "answer": 0}]})
        self.assertTrue(any("options" in p for p in problems))

    def test_negative_cue_fails(self):
        self.assertTrue(opencut_scenes.validate_spec({"scenes": [{"cue": -1, "template": "title", "title": "x"}]}))


if __name__ == "__main__":
    unittest.main()
