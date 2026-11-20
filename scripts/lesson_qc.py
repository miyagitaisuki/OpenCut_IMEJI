#!/usr/bin/env python3
"""Checks on a lesson before it is published (standard library + Pillow for `layout`).

  python scripts/lesson_qc.py pron   <x.project.json> [--words x.words.json] [--fix]
  python scripts/lesson_qc.py layout <folder-of-scene-stills> [--safe L,T,R,B]
  python scripts/lesson_qc.py video  <x.mp4> [--short]

pron    Compares what Whisper heard (`node apps/intro/scripts/lesson.ts words`) with each
        subtitle line. A line that sounds too different is a suspect: the voice may have
        misread a kanji. `--fix` adds the line's furigana words (`漢字{かな}`) to textts'
        reading dictionary (POST /api/v1/readings), so a re-voice reads them as written.
        Whisper (base model) also mishears, so a suspect is a place to listen, not proof.
layout  Looks at scene stills (`lesson.ts preview`): dark text outside the safe area means
        a scene overflowed (the subtitles and the chibi use the rest of the screen).
video   ffprobe: size, codec, length, loudness (-16 LUFS target).

Exit status 1 when something needs attention.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
from pathlib import Path

TEXTTS_URL = os.environ.get("TEXTTS_URL", "http://127.0.0.1:8000").rstrip("/")
RUBY = re.compile(r"([一-鿿々]+)\{([^}]+)\}")
PUNCT = re.compile(r"[\s、。，．,.!?！？「」『』（）()・\-ー〜~]+")
THRESHOLD = 0.55


def norm(text: str) -> str:
    return PUNCT.sub("", unicodedata.normalize("NFKC", text))


def surface(text: str) -> str:
    return RUBY.sub(lambda m: m.group(1), text)


def reading(text: str) -> str:
    return RUBY.sub(lambda m: m.group(2), text)


def similarity(expected: str, heard: str) -> float:
    """Best of: the sentence as written (kanji) and as read (kana) against what was heard."""
    h = norm(heard)
    if not h:
        return 0.0
    return max(difflib.SequenceMatcher(None, norm(surface(expected)), h).ratio(),
               difflib.SequenceMatcher(None, norm(reading(expected)), h).ratio())


def pron(project_path: Path, words_path: Path | None, fix: bool) -> int:
    project = json.loads(project_path.read_text(encoding="utf-8"))
    words_path = words_path or project_path.with_name(re.sub(r"\.project\.json$|\.json$", "", project_path.name) + ".words.json")
    if not words_path.exists():
        print(f"error: {words_path} not found: run `node apps/intro/scripts/lesson.ts words {project_path}`", file=sys.stderr)
        return 2
    heard = json.loads(words_path.read_text(encoding="utf-8"))
    audio = (project.get("audio") or [{}])[0]
    offset = float(audio.get("start", 0))  # Whisper times count from the body start
    suspects: list[tuple[int, float, str, str]] = []
    for i, cue in enumerate(project.get("subtitles", [])):
        lo, hi = cue["start"] - offset - 0.3, cue["end"] - offset + 0.3
        said = "".join(w["text"] for w in heard if lo <= (w["start"] + w["end"]) / 2 <= hi)
        score = similarity(cue["text"], said)
        if score < THRESHOLD:
            suspects.append((i, score, cue["text"], said))
    total = len(project.get("subtitles", []))
    print(f"{total - len(suspects)}/{total} lines sound as written (threshold {THRESHOLD})")
    for i, score, text, said in suspects:
        print(f"  line {i}: {score:.2f}  written: {surface(text)}  |  heard: {said or '(nothing)'}")
    if fix and suspects:
        added = []
        for _, _, text, _ in suspects:
            for kanji, kana in RUBY.findall(text):
                added.append((kanji, kana))
        done = []
        for kanji, kana in dict.fromkeys(added):
            try:
                req = urllib.request.Request(f"{TEXTTS_URL}/api/v1/readings", method="POST",
                                             data=json.dumps({"word": kanji, "reading": kana}).encode("utf-8"),
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=20).read()
                done.append(f"{kanji}={kana}")
            except Exception as error:  # noqa: BLE001
                print(f"  could not add {kanji}={kana}: {error}", file=sys.stderr)
        print(f"added to textts' reading dictionary: {', '.join(done) or 'nothing'}; voice the lesson again to apply them")
    return 1 if suspects else 0


def layout(folder: Path, safe: tuple[int, int, int, int]) -> int:
    """Dark text pixels outside the safe area (left, top, right, bottom) of 1920x1080 stills."""
    from PIL import Image  # noqa: PLC0415

    bad = 0
    stills = sorted(folder.glob("[0-9][0-9]-*.png"))  # `lesson.ts preview` names them 01-title-cue0.png ...
    if not stills:
        print(f"error: no stills in {folder}", file=sys.stderr)
        return 2
    left, top, right, bottom = safe
    for path in stills:
        im = Image.open(path).convert("RGB")
        w, h = im.size
        px = im.load()
        out = 0
        # Sampling every 2nd pixel is plenty: text strokes are thick.
        for y in range(0, h, 2):
            for x in range(0, w, 2):
                if left <= x <= right and top <= y <= bottom:
                    continue
                r, g, b = px[x, y]
                if r < 90 and g < 100 and b < 150:  # navy / ink text
                    out += 1
        status = "OVERFLOW" if out > 12 else "ok"
        bad += status != "ok"
        print(f"  {path.name}: {status}" + (f" ({out} dark samples outside the safe area)" if out else ""))
    print(f"{len(stills) - bad}/{len(stills)} scenes inside the safe area")
    return 1 if bad else 0


def video(path: Path, size: tuple[int, int] = (1920, 1080), max_seconds: float | None = None) -> int:
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        print("error: ffprobe/ffmpeg not on PATH", file=sys.stderr)
        return 2
    info = json.loads(subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                                     capture_output=True, text=True, check=True).stdout)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    loud = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    lufs = re.findall(r"I:\s+(-?\d+\.\d)\s+LUFS", loud)
    peak = re.findall(r"Peak:\s+(-?\d+\.\d)\s+dBFS", loud)
    got = float(lufs[-1]) if lufs else None
    checks = {
        f"{size[0]}x{size[1]}": (v["width"], v["height"]) == size,
        "H.264": v["codec_name"] == "h264",
        "has audio": a is not None,
        "loudness -16 +/-1.5 LUFS": got is not None and abs(got + 16) <= 1.5,
        "true peak <= -1 dBTP": bool(peak) and float(peak[-1]) <= -0.9,
    }
    if max_seconds is not None:
        checks[f"shorter than {max_seconds:g} s"] = float(info["format"]["duration"]) < max_seconds
    print(f"{path.name}: {v['width']}x{v['height']} {v['codec_name']}, {float(info['format']['duration']):.1f} s, "
          f"{got} LUFS, peak {peak[-1] if peak else '?'} dBFS")
    for name, ok in checks.items():
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    return 0 if all(checks.values()) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pron")
    p.add_argument("project")
    p.add_argument("--words")
    p.add_argument("--fix", action="store_true")
    la = sub.add_parser("layout")
    la.add_argument("folder")
    la.add_argument("--safe", default="90,40,1830,540", help="left,top,right,bottom in pixels")
    v = sub.add_parser("video")
    v.add_argument("file")
    v.add_argument("--short", action="store_true", help="a Short: 1080x1920, under 60 s")
    args = parser.parse_args(argv)
    if args.command == "pron":
        return pron(Path(args.project), Path(args.words) if args.words else None, args.fix)
    if args.command == "layout":
        return layout(Path(args.folder), tuple(int(n) for n in args.safe.split(",")))  # type: ignore[arg-type]
    if args.short:
        return video(Path(args.file), (1080, 1920), 60)
    return video(Path(args.file))


if __name__ == "__main__":
    raise SystemExit(main())
