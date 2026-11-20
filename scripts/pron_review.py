"""Pronunciation review for lesson jobs: the lines the listen-back check flagged, a clip of each to listen to,
and a reading the reviewer can teach textts (standard library only; ffmpeg for the clips).

Used by lesson_jobs.py (the dashboard and its routes). Nothing here changes a lesson by itself: a taught reading
goes to textts' readings dictionary, and the job is rebuilt from its voice stage when the reviewer asks.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

TEXTTS_URL = os.environ.get("TEXTTS_URL", "http://127.0.0.1:8000").rstrip("/")
KANA = re.compile(r"^[ぁ-ゖァ-ヺーー]+$")  # hiragana, katakana, the long-vowel mark
PAD_MS = 150


class ReviewError(RuntimeError):
    pass


def _ffmpeg() -> str:
    exe = os.environ.get("OPENCUT_FFMPEG") or shutil.which("ffmpeg")
    if not exe:
        raise ReviewError("ffmpeg not found: set OPENCUT_FFMPEG")
    return exe


def flagged(folder: Path, name: str) -> list[dict]:
    """The lines the last voice check flagged, from <name>.qc.json (written by the render stage)."""
    path = folder / f"{name}.qc.json"
    if not path.exists():
        return []
    history = (json.loads(path.read_text(encoding="utf-8")).get("voice") or {}).get("history") or []
    if not history:
        return []
    return [{"id": s.get("id"), "display": s.get("display"), "heard": s.get("heard"), "score": s.get("score")}
            for s in history[-1].get("suspicious", [])]


def clip(folder: Path, name: str, line_id: str) -> bytes:
    """A short MP3 of one line, cut from the voice file textts made (its timeline gives the line's span)."""
    state = folder / f"{name}.tts.json"
    if not state.exists():
        raise ReviewError("no voice yet for this lesson: run the tts stage first")
    info = json.loads(state.read_text(encoding="utf-8"))
    timeline = json.loads(Path(info["timeline"]).read_text(encoding="utf-8"))
    item = next((i for i in timeline.get("items", []) if i.get("id") == line_id), None)
    if item is None:
        raise ReviewError(f"{line_id} is not in the timeline")
    start = max(0.0, item["start_ms"] / 1000 - PAD_MS / 1000)
    length = (item["end_ms"] - item["start_ms"]) / 1000 + 2 * PAD_MS / 1000
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "clip.mp3"
        done = subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
                               "-i", info["audio"], "-c:a", "libmp3lame", "-b:a", "128k", str(out)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        if done.returncode != 0 or not out.exists():
            raise ReviewError(f"cannot cut the clip: {done.stderr.strip()[-300:]}")
        return out.read_bytes()


def teach(word: str, reading: str) -> dict:
    """Adds word=reading to textts' readings dictionary. The reading must be kana; the word non-empty."""
    word = (word or "").strip()
    reading = (reading or "").strip()
    if not word:
        raise ReviewError("word is empty")
    if not KANA.match(reading):
        raise ReviewError("reading must be kana (hiragana or katakana), e.g. にほん")
    body = json.dumps({"word": word, "reading": reading}).encode("utf-8")
    req = urllib.request.Request(f"{TEXTTS_URL}/api/v1/readings", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except OSError as error:
        raise ReviewError(f"cannot reach textts ({TEXTTS_URL}): {error}") from error
