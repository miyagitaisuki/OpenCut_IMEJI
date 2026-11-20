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
import homographs
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


def pron_data(project_path: Path, words_path: Path | None, fix: bool) -> dict:
    """Whisper's transcript of each cue against the cue text. Data only; `pron` prints it."""
    project = json.loads(project_path.read_text(encoding="utf-8"))
    words_path = words_path or project_path.with_name(re.sub(r"\.project\.json$|\.json$", "", project_path.name) + ".words.json")
    if not words_path.exists():
        return {"ok": None, "total": 0, "suspects": [], "readings_added": [],
                "error": f"{words_path} not found: run `node apps/intro/scripts/lesson.ts words {project_path}`"}
    heard = json.loads(words_path.read_text(encoding="utf-8"))
    audio = (project.get("audio") or [{}])[0]
    offset = float(audio.get("start", 0))  # Whisper times count from the body start
    suspects: list[dict] = []
    cues = project.get("subtitles", [])
    for i, cue in enumerate(cues):
        lo, hi = cue["start"] - offset - 0.3, cue["end"] - offset + 0.3
        said = "".join(w["text"] for w in heard if lo <= (w["start"] + w["end"]) / 2 <= hi)
        score = similarity(cue["text"], said)
        if score < THRESHOLD:
            suspects.append({"line": i, "score": round(score, 2), "written": surface(cue["text"]),
                             "heard": said or "(nothing)", "display": cue["text"]})
    added: list[str] = []
    if fix and suspects:
        # A single kanji with okurigana (行{い}きます) is a stem, not a word: an entry for it would be
        # applied inside other words. Only words of two or more kanji are added.
        added = add_readings([pair for s_ in suspects for pair in word_candidates(s_["display"])], TEXTTS_URL)
    return {"ok": not suspects, "total": len(cues), "suspects": suspects, "readings_added": added, "error": None}


def pron(project_path: Path, words_path: Path | None, fix: bool) -> int:
    data = pron_data(project_path, words_path, fix)
    if data["error"]:
        print(f"error: {data['error']}", file=sys.stderr)
        return 2
    total = data["total"]
    print(f"{total - len(data['suspects'])}/{total} lines sound as written (threshold {THRESHOLD})")
    for s_ in data["suspects"]:
        print(f"  line {s_['line']}: {s_['score']:.2f}  written: {s_['written']}  |  heard: {s_['heard']}")
    if fix and data["suspects"]:
        print(f"added to textts' reading dictionary: {', '.join(data['readings_added']) or 'nothing'}; voice the lesson again to apply them")
    return 1 if data["suspects"] else 0


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


def engine_data(project_path: Path, voices_path: Path, url: str, fix: bool = False) -> dict:
    """Per line: the moras AivisSpeech will say vs the furigana of the script. Data only; `engine` prints it."""
    import urllib.parse  # noqa: PLC0415

    known = textts_readings(TEXTTS_URL)

    project = json.loads(project_path.read_text(encoding="utf-8"))
    voices = json.loads(voices_path.read_text(encoding="utf-8")) if voices_path.exists() else {}
    suspects: list[dict] = []
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
            return {"ok": None, "total": len(cues), "suspects": [], "readings_added": [],
                    "error": f"AivisSpeech at {url}: {error}"}
        said = "".join(m["text"] for ap in query["accent_phrases"] for m in ap["moras"])
        want = reading(cue["text"])
        for word in sorted(known, key=len, reverse=True):  # Latin words (QBank) are taught to textts in kana
            want = want.replace(word, known[word])
        score = difflib.SequenceMatcher(None, kana_norm(want), kana_norm(said)).ratio()
        if score < 0.85:
            suspects.append({"line": i, "score": round(score, 2), "furigana": want, "engine_says": said,
                             "display": cue["text"]})
    added: list[str] = []
    if fix and suspects:
        pairs = [pair for s_ in suspects for pair in word_candidates(s_["display"])]
        added = add_readings(pairs, TEXTTS_URL)
    return {"ok": not suspects, "total": len(cues), "suspects": suspects, "readings_added": added, "error": None}


def engine(project_path: Path, voices_path: Path, url: str, fix: bool = False) -> int:
    data = engine_data(project_path, voices_path, url, fix)
    if data["error"]:
        print(f"error: {data['error']}", file=sys.stderr)
        return 2
    total = data["total"]
    print(f"{total - len(data['suspects'])}/{total} lines are read by the engine as the furigana says")
    for s_ in data["suspects"]:
        print(f"  line {s_['line']}: {s_['score']:.2f}  furigana: {s_['furigana']}  |  engine says: {s_['engine_says']}")
    if fix and data["suspects"]:
        print(f"added to textts' reading dictionary: {', '.join(data['readings_added']) or 'nothing'}; run the check again, then voice the lesson again")
    return 1 if data["suspects"] else 0


def layout_data(folder: Path, safe: tuple[int, int, int, int]) -> dict:
    """Dark text pixels outside the safe area of each still. Data only; `layout` prints it."""
    from PIL import Image  # noqa: PLC0415

    stills = sorted(folder.glob("[0-9][0-9]-*.png"))  # `lesson.ts preview` names them 01-title-cue0.png ...
    if not stills:
        return {"ok": None, "total": 0, "scenes": [], "error": f"no stills in {folder}"}
    left, top, right, bottom = safe
    scenes: list[dict] = []
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
        scenes.append({"file": path.name, "ok": out <= 12, "dark_outside": out})
    return {"ok": all(sc["ok"] for sc in scenes), "total": len(scenes), "scenes": scenes, "error": None}


def layout(folder: Path, safe: tuple[int, int, int, int]) -> int:
    data = layout_data(folder, safe)
    if data["error"]:
        print(f"error: {data['error']}", file=sys.stderr)
        return 2
    for sc in data["scenes"]:
        status = "ok" if sc["ok"] else "OVERFLOW"
        print(f"  {sc['file']}: {status}" + (f" ({sc['dark_outside']} dark samples outside the safe area)" if sc["dark_outside"] else ""))
    good = sum(sc["ok"] for sc in data["scenes"])
    print(f"{good}/{data['total']} scenes inside the safe area")
    return 0 if data["ok"] else 1


def video(path: Path, size: tuple[int, int] = (1920, 1080), max_seconds: float | None = None) -> int:
    ffprobe = os.environ.get("OPENCUT_FFPROBE") or shutil.which("ffprobe")
    ffmpeg = os.environ.get("OPENCUT_FFMPEG") or shutil.which("ffmpeg")
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


RETRY_BUDGET = 3  # attempts per issue before the loop gives up on it


def state_hash(project_path: Path) -> str:
    """Fingerprint of what the voice and text say: changes when the agent edits a line, not when a check runs."""
    import hashlib  # noqa: PLC0415

    project = json.loads(project_path.read_text(encoding="utf-8"))
    body = [(c.get("text", ""), c.get("role", "")) for c in project.get("subtitles", [])]
    return hashlib.sha256(json.dumps(body, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _issue_key(issue: dict) -> str:
    return f"{issue['type']}|{issue.get('scene_id', '')}|{issue.get('field', '')}"


def _circuit(project_path: Path, issues: list[dict]) -> dict:
    """Circuit breaker over runs. A run is recorded in `<project>.qc-history.json`.
    OPEN when the same state already failed before (the agent is oscillating between two edits),
    or when an issue has used its retry budget. OPEN means: stop, quarantine, and ask a person."""
    history_path = project_path.with_name(re.sub(r"\.project\.json$|\.json$", "", project_path.name) + ".qc-history.json")
    history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else {"runs": []}
    current = state_hash(project_path)
    keys = [_issue_key(i) for i in issues]
    previous = history["runs"][-1]["state"] if history["runs"] else None
    # A -> B -> A: this state failed before and the lesson has changed since. A -> A (no edit) is not a loop.
    repeats = bool(issues) and current != previous and any(
        r["state"] == current and r["status"] == "FAILED" for r in history["runs"])
    spent = [k for k in set(keys) if sum(1 for r in history["runs"] if k in r.get("issue_keys", [])) >= RETRY_BUDGET]
    reason = None
    if repeats:
        reason = "this state of the lesson already failed earlier: the edits are going back and forth"
    elif spent:
        reason = f"retry budget used up for: {', '.join(sorted(spent))}"
    status = "FAILED" if issues else "PASSED"
    # Only a changed lesson is an attempt: checking the same state again is not a new try.
    if current != previous:
        history["runs"].append({"state": current, "status": status, "issue_keys": keys})
        history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"state_hash": current, "circuit": "OPEN" if reason else "CLOSED", "circuit_reason": reason,
            "attempts_recorded": len(history["runs"])}


def report(project_path: Path, words_path: Path | None, stills: Path | None, voices_path: Path,
           url: str, safe: tuple[int, int, int, int], fix: bool = False) -> dict:
    """All checks as one structured result an agent can act on.

    status: PASSED (all checks ran and passed), FAILED (issues to fix), or QUARANTINE (the circuit
    breaker opened: stop editing, a person must look). A check that could not run is listed under
    `unchecked`; it is never counted as a pass."""
    checks: dict[str, dict] = {}
    checks["pron"] = pron_data(project_path, words_path, False)
    checks["engine"] = engine_data(project_path, voices_path, url, fix)
    if stills is not None:
        checks["layout"] = layout_data(stills, safe)
    unchecked = [name for name, c in checks.items() if c.get("error") or c.get("ok") is None]

    issues: list[dict] = []
    n = 0

    def add(issue: dict) -> None:
        nonlocal n
        n += 1
        issues.append({"issue_id": f"err_{n:02d}", **issue})

    for line in checks.get("engine", {}).get("suspects", []):
        token, expected, got = _first_difference(line["furigana"], line["engine_says"])
        annotated, resolved, unresolved = homographs.annotate(line["display"])
        issue = {"scene_id": f"cue_{line['line']:03d}", "type": "PRON_MISMATCH", "field": f"subtitles[{line['line']}].text",
                 "token": token, "expected_reading": expected, "tts_phonemes": got,
                 "metrics": {"similarity": line["score"], "threshold": 0.85},
                 "suggestion": f"write the reading explicitly in the text: {token}{{{expected}}} (the engine reads {got})"
                 if token else "reword or add furigana for the words of this line"}
        if resolved:  # a homograph rule settles the reading: give the exact text to write
            issue["homograph_fix"] = annotated
            issue["suggestion"] = f"write the readings the rules decide: {annotated}"
        if unresolved:  # the sentence decides: an agent (or a person) reads it
            issue["homograph_unresolved"] = [u["word"] for u in unresolved]
        add(issue)
    for line in checks.get("pron", {}).get("suspects", []):
        add({"scene_id": f"cue_{line['line']:03d}", "type": "HEARD_MISMATCH", "field": f"subtitles[{line['line']}].text",
             "heard": line["heard"], "metrics": {"similarity": line["score"], "threshold": 0.55},
             "suggestion": "check the kanji readings of this line; a listening pass with the engine check confirms it"})
    for index, sc in enumerate(checks.get("layout", {}).get("scenes", []), start=1):
        if not sc["ok"]:
            add({"scene_id": f"scene_{index:02d}_{sc['file'].split('-', 1)[-1].rsplit('.', 1)[0]}",
                 "type": "LAYOUT_OVERFLOW", "field": "scene_still",
                 "metrics": {"dark_samples_outside_safe": sc["dark_outside"], "allowed": 12},
                 "suggestion": "shorten the text of this scene or split it (the safe area is SAFE in src/lesson/theme.tsx)"})

    circuit = _circuit(project_path, issues)
    if circuit["circuit"] == "OPEN":
        status = "QUARANTINE"
    elif issues or unchecked:
        status = "FAILED"
    else:
        status = "PASSED"
    return {"status": status, "ok": status == "PASSED", **circuit,
            "checks": {k: {kk: vv for kk, vv in v.items() if kk != "suspects"} for k, v in checks.items()},
            "unchecked": unchecked, "issues": issues}


def _first_difference(expected: str, said: str) -> tuple[str, str, str]:
    """The first word-sized span where the furigana and the engine's reading differ: (token, expected, said)."""
    e, g = kana_norm(expected), kana_norm(said)
    matcher = difflib.SequenceMatcher(None, e, g)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            return _kanji_near(expected, i1), e[i1:i2], g[j1:j2]
    return "", "", ""


def _kanji_near(text: str, kana_index: int) -> str:
    """The kanji run closest to a position in the kana reading (a rough token for the suggestion)."""
    runs = list(re.finditer(r"[一-鿿々]+", surface(text)))
    if not runs:
        return ""
    return max(runs, key=lambda m: -abs(m.start() - kana_index)).group(0)


def report_cli(args) -> int:
    stills = Path(args.stills) if args.stills else None
    data = report(Path(args.project), Path(args.words) if args.words else None, stills,
                  Path(args.voices), args.url.rstrip("/"), tuple(int(n) for n in args.safe.split(",")), args.fix)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0 if data["ok"] else 1


def quarantine(project_path: Path, report_data: dict, stills: Path | None, dest: Path) -> Path:
    """Parks a lesson that is not ready: the project, the failing stills, and a qc_report.md a person can read
    in about 30 seconds. Nothing here is published."""
    import shutil  # noqa: PLC0415

    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(project_path, dest / project_path.name)
    lines = [f"# QC report: {project_path.name}", "", f"Status: **{report_data['status']}**", ""]
    if report_data.get("circuit_reason"):
        lines += [f"Circuit breaker: {report_data['circuit_reason']}", ""]
    if report_data.get("unchecked"):
        lines += [f"Not checked: {', '.join(report_data['unchecked'])}", ""]
    for issue in report_data.get("issues", []):
        lines.append(f"- **{issue['issue_id']}** `{issue['type']}` {issue.get('scene_id', '')} ({issue.get('field', '')})")
        lines.append(f"  - metrics: {json.dumps(issue.get('metrics', {}), ensure_ascii=False)}")
        lines.append(f"  - suggestion: {issue.get('suggestion', '')}")
        if issue["type"] == "LAYOUT_OVERFLOW" and stills is not None:
            still = stills / issue.get("scene_id", "").replace("scene_", "", 1)
            matches = sorted(stills.glob(f"{issue['scene_id'].split('_')[1]}-*.png"))
            if matches:
                shutil.copy2(matches[0], dest / matches[0].name)
                lines.append(f"  - image: {matches[0].name}")
    (dest / "qc_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (dest / "qc_report.json").write_text(json.dumps(report_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def quarantine_cli(args) -> int:
    stills = Path(args.stills) if args.stills else None
    project = Path(args.project)
    data = report(project, Path(args.words) if args.words else None, stills, Path(args.voices),
                  args.url.rstrip("/"), tuple(int(n) for n in args.safe.split(",")), False)
    if data["status"] == "PASSED":
        print("passed: nothing to quarantine")
        return 0
    folder = quarantine(project, data, stills, Path(args.dest) / re.sub(r"\.project\.json$|\.json$", "", project.name))
    print(f"{data['status']}: parked in {folder}")
    return 1


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
    qp = sub.add_parser("quarantine", help="park a lesson that fails QC: qc_report.md, the project, the failing stills")
    qp.add_argument("project")
    qp.add_argument("--words")
    qp.add_argument("--stills")
    qp.add_argument("--voices", default=str(Path(__file__).resolve().parent / "lesson_voices.json"))
    qp.add_argument("--url", default=os.environ.get("AIVIS_URL", "http://127.0.0.1:10101"))
    qp.add_argument("--safe", default="90,40,1830,540")
    qp.add_argument("--dest", default="quarantine")
    rp = sub.add_parser("report", help="every check at once, as JSON: pron, engine, layout (with --stills)")
    rp.add_argument("project")
    rp.add_argument("--words")
    rp.add_argument("--stills", help="folder of scene stills (lesson.ts preview) for the layout check")
    rp.add_argument("--voices", default=str(Path(__file__).resolve().parent / "lesson_voices.json"))
    rp.add_argument("--url", default=os.environ.get("AIVIS_URL", "http://127.0.0.1:10101"))
    rp.add_argument("--safe", default="90,40,1830,540")
    rp.add_argument("--fix", action="store_true", help="teach textts the readings of engine suspects")
    rp.add_argument("--out", help="also write the JSON report to this file (the publish gate reads it)")
    v = sub.add_parser("video")
    v.add_argument("file")
    v.add_argument("--short", action="store_true", help="a Short: 1080x1920, under 60 s")
    args = parser.parse_args(argv)
    if args.command == "pron":
        return pron(Path(args.project), Path(args.words) if args.words else None, args.fix)
    if args.command == "engine":
        return engine(Path(args.project), Path(args.voices), args.url.rstrip("/"), args.fix)
    if args.command == "quarantine":
        return quarantine_cli(args)
    if args.command == "report":
        return report_cli(args)
    if args.command == "layout":
        return layout(Path(args.folder), tuple(int(n) for n in args.safe.split(",")))  # type: ignore[arg-type]
    if args.short:
        return video(Path(args.file), (1080, 1920), 60)
    return video(Path(args.file))


if __name__ == "__main__":
    raise SystemExit(main())
