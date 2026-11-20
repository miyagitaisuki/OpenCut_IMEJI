"""Tests for the pronunciation review (pron_review.py). The clip test needs ffmpeg and is skipped without it."""
from __future__ import annotations

import json
import math
import shutil
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pron_review  # noqa: E402


def sine_wav(path: Path, seconds: float) -> None:
    rate = 16000
    frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
                      for i in range(int(rate * seconds)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)


class Flagged(unittest.TestCase):
    def test_lists_the_last_attempts_suspicious_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            qc = {"voice": {"history": [
                {"suspicious": [{"id": "L001", "display": "a", "heard": "x", "score": 0.5}]},
                {"suspicious": [{"id": "L002", "display": "b", "heard": "y", "score": 0.7}]}]}}
            (folder / "n.qc.json").write_text(json.dumps(qc, ensure_ascii=False), encoding="utf-8")
            self.assertEqual([l["id"] for l in pron_review.flagged(folder, "n")], ["L002"])

    def test_no_report_no_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(pron_review.flagged(Path(tmp), "n"), [])


class Teach(unittest.TestCase):
    def test_reading_must_be_kana(self):
        with self.assertRaises(pron_review.ReviewError):
            pron_review.teach("日本", "nihon")
        with self.assertRaises(pron_review.ReviewError):
            pron_review.teach("日本", "日本")

    def test_word_must_not_be_empty(self):
        with self.assertRaises(pron_review.ReviewError):
            pron_review.teach("  ", "にほん")


@unittest.skipUnless(shutil.which("ffmpeg") or __import__("os").environ.get("OPENCUT_FFMPEG"), "needs ffmpeg")
class Clip(unittest.TestCase):
    def test_cuts_the_line_span_from_the_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            voice_wav = folder / "voice.wav"
            sine_wav(voice_wav, 4.0)
            timeline = folder / "t.json"
            timeline.write_text(json.dumps({"items": [{"id": "L001", "start_ms": 1000, "end_ms": 2000}]}), encoding="utf-8")
            (folder / "n.tts.json").write_text(json.dumps({"audio": str(voice_wav), "timeline": str(timeline)}), encoding="utf-8")
            data = pron_review.clip(folder, "n", "L001")
            self.assertTrue(len(data) > 1000)
            self.assertTrue(data[:3] in (b"ID3", b"\xff\xfb") or data[:2] == b"\xff\xf3")
            with self.assertRaises(pron_review.ReviewError):
                pron_review.clip(folder, "n", "L999")


if __name__ == "__main__":
    unittest.main()
