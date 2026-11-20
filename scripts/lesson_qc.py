#!/usr/bin/env python3
"""Checks on a lesson before it is published (standard library + Pillow for `layout`).

  python scripts/lesson_qc.py pron   <x.project.json> [--words x.words.json] [--fix]
  python scripts/lesson_qc.py engine <x.project.json> [--voices scripts/lesson_voices.json]
  python scripts/lesson_qc.py layout <folder-of-scene-stills> [--safe L,T,R,B]
  python scripts/lesson_qc.py video  <x.mp4> [--short]

pron    Compares what Whisper heard (`node apps/intro/scripts/lesson.ts words`) with each
        subtitle line. A line that sounds too different is a suspect: the voice may have
        misread a kanji. `--fix` adds the line's furigana words (`漢字{かな}`) to textts'
        reading dictionary (POST /api/v1/readings), so a re-voice reads them as written.
        Whisper (base model) also mishears, so a suspect is a place to listen, not proof.
engine  Asks AivisSpeech how it will read each line (`/audio_query`: the moras it will say) and compares
        that with the furigana. Exact, unlike Whisper: a line is a suspect only if the engine reads it
        differently from what the script says (particles は/へ/を and long vowels are allowed for).
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
PUNCT = re.compile(r"[\s、。，．,.!?！？「」『』（）()・\-ー〜~'\"]+")
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
        # A single kanji with okurigana (行{い}きます) is a stem, not a word: an entry for it would be
        # applied inside other words. Only words of two or more kanji are added.
        done = add_readings([pair for _, _, text, _ in suspects for pair in word_candidates(text)], TEXTTS_URL)
        print(f"added to textts' reading dictionary: {', '.join(done) or 'nothing'}; voice the lesson again to apply them")
    return 1 if suspects else 0


def kana_norm(text: str) -> str:
    """Hiragana -> katakana, minus punctuation, with the spellings that sound alike made equal
    (particle は/へ/を, long vowels)."""
    out = "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in PUNCT.sub("", unicodedata.normalize("NFKC", text)))
    for a, b in (("ヘ", "エ"), ("ハ", "ワ"), ("ヲ", "オ"), ("ー", "")):
        out = out.replace(a, b)
    # long vowels: ...エイ / ...オウ are spoken エー / オー
    return re.sub(r"([エケセテネメレゲゼデベペ])イ", r"\1エ", re.sub(r"([オコソトノモヨロゴゾドボポョ])ウ", r"\1オ", out))


# A word made of kanji (with okurigana between them): 三{みっ}つ目{め} -> 三つ目 / みっつめ.
SEGMENT = re.compile(r"(?:[一-鿿々]+\{[^}]+\}(?:(?![はがをにでとものへや])[ぁ-ん]{1,2}(?=[一-鿿々]+\{))?)+")


def word_candidates(text: str) -> list[tuple[str, str]]:
    """Words of a furigana line to teach textts: two or more kanji, or kanji joined by okurigana."""
    out = []
    for m in SEGMENT.finditer(text):
        seg = m.group(0)
        word, kana = surface(seg), reading(seg)
        if len(re.sub(r"[ぁ-ん]", "", word)) >= 2:
            out.append((word, kana))
    return out


def textts_readings(url: str) -> dict[str, str]:
    try:
        return json.load(urllib.request.urlopen(f"{url}/api/v1/readings", timeout=15)).get("readings", {})
    except Exception:  # noqa: BLE001
        return {}


def add_readings(pairs: list[tuple[str, str]], url: str) -> list[str]:
    done = []
    for word, kana in dict.fromkeys(pairs):
        try:
            req = urllib.request.Request(f"{url}/api/v1/readings", method="POST",
                                         data=json.dumps({"word": word, "reading": kana}).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=20).read()
            done.append(f"{word}={kana}")
        except Exception as error:  # noqa: BLE001
            print(f"  could not add {word}={kana}: {error}", file=sys.stderr)
    return done


def engine(project_path: Path, voices_path: Path, url: str, fix: bool = False) -> int:
    """Per line: the moras AivisSpeech will say vs the furigana of the script (textts' readings applied first)."""
    import urllib.parse  # noqa: PLC0415

    known = textts_readings(TEXTTS_URL)

    project = json.loads(project_path.read_text(encoding="utf-8"))
    voices = json.loads(voices_path.read_text(encoding="utf-8")) if voices_path.exists() else {}
    suspects = []
    cues = project.get("subtitles", [])
    for i, cue in enumerate(cues):
        voice = (voices.get(str(cue.get("role", "1"))) or voices.get("1") or {}).get("voice")
        if not voice:
            continue
        spoken = surface(cue["text"])
        for word in sorted(known, key=len, reverse=True):
            spoken = spoken.replace(word, known[word])
        req = urllib.request.Request(f"{url}/audio_query?" + urllib.parse.urlencode({"text": spoken, "speaker": voice}), method="POST")
        try:
            query = json.load(urllib.request.urlopen(req, timeout=30))
        except Exception as error:  # noqa: BLE001
            print(f"error: AivisSpeech at {url}: {error}", file=sys.stderr)
            return 2
        said = "".join(m["text"] for ap in query["accent_phrases"] for m in ap["moras"])
        want = reading(cue["text"])
        for word in sorted(known, key=len, reverse=True):  # Latin words (QBank) are taught to textts in kana
            want = want.replace(word, known[word])
        score = difflib.SequenceMatcher(None, kana_norm(want), kana_norm(said)).ratio()
        if score < 0.85:
            suspects.append((i, score, want, said))
    print(f"{len(cues) - len(suspects)}/{len(cues)} lines are read by the engine as the furigana says")
    for i, score, want, said in suspects:
        print(f"  line {i}: {score:.2f}  furigana: {want}  |  engine says: {said}")
    if fix and suspects:
        pairs = [pair for i, *_ in suspects for pair in word_candidates(cues[i]["text"])]
        added = add_readings(pairs, TEXTTS_URL)
        print(f"added to textts' reading dictionary: {', '.join(added) or 'nothing'}; run the check again, then voice the lesson again")
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
    e = sub.add_parser("engine")
    e.add_argument("project")
    e.add_argument("--voices", default=str(Path(__file__).resolve().parent / "lesson_voices.json"))
    e.add_argument("--fix", action="store_true", help="teach textts the readings of the suspect lines' words")
    e.add_argument("--url", default=os.environ.get("AIVIS_URL", "http://127.0.0.1:10101"))
    la = sub.add_parser("layout")
    la.add_argument("folder")
    la.add_argument("--safe", default="90,40,1830,540", help="left,top,right,bottom in pixels")
    v = sub.add_parser("video")
    v.add_argument("file")
    v.add_argument("--short", action="store_true", help="a Short: 1080x1920, under 60 s")
    args = parser.parse_args(argv)
    if args.command == "pron":
        return pron(Path(args.project), Path(args.words) if args.words else None, args.fix)
    if args.command == "engine":
        return engine(Path(args.project), Path(args.voices), args.url.rstrip("/"), args.fix)
    if args.command == "layout":
        return layout(Path(args.folder), tuple(int(n) for n in args.safe.split(",")))  # type: ignore[arg-type]
    if args.short:
        return video(Path(args.file), (1080, 1920), 60)
    return video(Path(args.file))


if __name__ == "__main__":
    raise SystemExit(main())
