#!/usr/bin/env python3
"""PTC client: QBank -> textts -> OpenCut (standard library only).

Turns listening questions stored in QBank into a lesson video:

  1. read each question's `transcript` from the QBank REST API;
  2. send the joined script to textts (`POST /api/v1/dialogue`) for MP3 + SRT
     + timeline;
  3. `opencut import-textts` builds the project, then this script adds one
     `question` marker per question (`ref` = `qbank:<id>`);
  4. optionally `opencut render` (with `--render`).

Or, from a lesson script written and approved beforehand (`--script`, see the
`soan-bai-video` skill): `<name>.script.vi.txt` has one `[role] 日本語 // Tiếng Việt`
line per sentence and `## Title` lines for the chapters. `<name>.visuals.json`
next to it (or `--visuals`) gives the scenes; it is checked against the script
before anything is voiced.

Environment: QBANK_URL (default http://127.0.0.1:8765), TEXTTS_URL (default
http://127.0.0.1:8000), OPENCUT_BIN (default `opencut` on PATH, else
target/release|debug/opencut under the repo).

Examples:
  python scripts/opencut_ptc.py check
  python scripts/opencut_ptc.py lesson --question 7323 --question 7514 \
      --out lessons/n2-nghe --render --burn-subtitles
  python scripts/opencut_ptc.py lesson --chapter 193 --limit 5 --out lessons/ch193
  python scripts/opencut_ptc.py lesson --script lessons/minna-05/minna-05.script.vi.txt \
      --out lessons/minna-05 --karaoke --mascot apps/intro/public/avatars/chibi --render
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
QBANK_URL = os.environ.get("QBANK_URL", "http://127.0.0.1:8765").rstrip("/")
TEXTTS_URL = os.environ.get("TEXTTS_URL", "http://127.0.0.1:8000").rstrip("/")
PAUSE_BETWEEN_QUESTIONS_MS = 1500

# Lines that carry speech: "[1] ...", "[0] ..." (narrator) or "1 ...".
_SPEECH = re.compile(r"^\s*\[?\d+\]?[\s　]*\S")
# QBank writes ruby as {漢字|かな}; textts wants 漢字{かな}.
_QBANK_RUBY = re.compile(r"\{([^{}|]+)\|([^{}|]+)\}")


class PtcError(RuntimeError):
    pass


def http_json(method: str, url: str, body: dict | None = None, timeout: int = 600):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:400]
        raise PtcError(f"{method} {url} -> HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, OSError) as error:
        raise PtcError(f"cannot reach {url}: {error}") from error


# ---- QBank ---------------------------------------------------------------


def qbank_question(question_id: int) -> dict:
    return http_json("GET", f"{QBANK_URL}/api/questions/{int(question_id)}")


def qbank_chapter_questions(chapter_id: int, limit: int) -> list[dict]:
    items = http_json("GET", f"{QBANK_URL}/api/questions?limit=5000")
    items = items if isinstance(items, list) else items.get("items", [])
    found = [q for q in items if q.get("chapter_id") == chapter_id and q.get("transcript")]
    return found[:limit] if limit else found


def to_textts_ruby(text: str) -> str:
    return _QBANK_RUBY.sub(lambda m: f"{m.group(1)}{{{m.group(2)}}}", text)


_LEADING_ROLE = re.compile(r"^\s*\[?\d+\]?[\s　:：]*")


# QBank's Vietnamese often labels speakers ("Nam:", "Nữ:"); the subtitle needs only the words.
_SPEAKER_LABEL = re.compile(
    r"^\s*(Nam|Nữ|Người dẫn|Giáo viên|Học sinh|Thầy|Cô|Bố|Mẹ|Con|Anh|Chị)\s*\d*\s*[:：]\s*"
)


def _is_speech(line: str) -> bool:
    return bool(_SPEECH.match(line)) and not line.lstrip().startswith("[pause")


def _translations(question: dict, speech_lines: list[str]) -> list[str] | None:
    """One Vietnamese line per spoken line, or None when QBank's translation does not line up."""
    raw = [
        _SPEAKER_LABEL.sub("", _LEADING_ROLE.sub("", l)).strip()
        for l in (question.get("translation") or "").splitlines()
        if l.strip() and not l.lstrip().startswith("[pause")
    ]
    if not raw:
        return None
    if len(raw) != len(speech_lines):
        print(
            f"warning: question {question['id']}: {len(raw)} translation lines for "
            f"{len(speech_lines)} spoken lines; translation skipped",
            file=sys.stderr,
        )
        return None
    return raw


def build_script(questions: list[dict]) -> tuple[str, str, list[int]]:
    """The textts script, the same script with ` // translation` for OpenCut,
    and the speech-line index where each question starts."""
    plain: list[str] = []
    translated: list[str] = []
    starts: list[int] = []
    speech = 0
    for position, question in enumerate(questions):
        transcript = (question.get("transcript") or "").strip()
        if not transcript:
            raise PtcError(f"question {question['id']} has no transcript (not a listening question?)")
        if position:
            plain.append(f"[pause={PAUSE_BETWEEN_QUESTIONS_MS}]")
            translated.append(f"[pause={PAUSE_BETWEEN_QUESTIONS_MS}]")
        starts.append(speech)
        lines = [l.rstrip() for l in to_textts_ruby(transcript).splitlines() if l.strip()]
        spoken = [l for l in lines if _is_speech(l)]
        tr = _translations(question, spoken)
        index = 0
        for line in lines:
            plain.append(line)
            if _is_speech(line):
                translated.append(f"{line} // {tr[index]}" if tr else line)
                index += 1
                speech += 1
            else:
                translated.append(line)
    return "\n".join(plain) + "\n", "\n".join(translated) + "\n", starts


def parse_lesson_script(path: Path) -> tuple[str, str, list[tuple[str, int]]]:
    """A lesson script -> (script for textts, script with ` // translation` for OpenCut,
    chapters as (title, index of the first spoken line)). `#` lines are comments; `## Title`
    starts a chapter at the next spoken line."""
    plain: list[str] = []
    translated: list[str] = []
    chapters: list[tuple[str, int]] = []
    speech = 0
    pending: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("##"):
            pending = stripped.lstrip("#").strip()
            continue
        if stripped.startswith("#"):
            continue
        if _is_speech(line):
            if pending is not None:
                chapters.append((pending, speech))
                pending = None
            plain.append(line.split(" // ", 1)[0].rstrip())
            translated.append(line)
            speech += 1
        else:  # [pause=...], [sfx=...], [bgm=...]
            plain.append(line)
            translated.append(line)
    if not speech:
        raise PtcError(f"{path}: no spoken lines")
    return "\n".join(plain) + "\n", "\n".join(translated) + "\n", chapters


def add_chapter_markers(project_path: Path, chapters: list[tuple[str, int]]) -> int:
    """One `chapter` marker per chapter, at its first spoken line's cue; the first one at 0:00 (YouTube needs it)."""
    project = json.loads(project_path.read_text(encoding="utf-8"))
    cues = project.get("subtitles", [])
    markers = project.setdefault("markers", [])
    for n, (title, first_line) in enumerate(chapters):
        if first_line >= len(cues):
            raise PtcError(f"chapter {title!r} starts at line {first_line}, but the project has {len(cues)} subtitles")
        markers.append({"time": 0.0 if n == 0 else round(cues[first_line]["start"], 3), "kind": "chapter", "label": title})
    markers.sort(key=lambda m: m["time"])
    project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(chapters)


def lesson_node(*args: str) -> subprocess.CompletedProcess:
    node = shutil.which("node")
    if not node:
        raise PtcError("needs Node.js (node 22+ on PATH)")
    script = REPO / "apps" / "intro" / "scripts" / "lesson.ts"
    env = dict(os.environ)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:  # `lesson words` calls ffmpeg: textts ships one
        for found in Path(os.environ.get("LOCALAPPDATA", "")).glob("Programs/textts-gui/resources/ffmpeg"):
            env["PATH"] = f"{found}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run([node, str(script), *args], cwd=script.parent.parent, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def check_scenes(visuals: str, script: Path) -> list[str]:
    """`lesson check` of the scenes against the (unvoiced) script: returns its warnings; errors raise."""
    done = lesson_node("check", str(Path(visuals).resolve()), str(script.resolve()))
    text = (done.stdout + done.stderr).strip()
    if done.returncode != 0:
        raise PtcError("the scenes do not fit the script:\n" + text)
    return [l for l in text.splitlines() if l.startswith("warning")]


# ---- textts --------------------------------------------------------------


def textts_dialogue(title: str, filename: str, script: str, roles: dict | None = None) -> dict:
    body = {
        "title": title,
        "filename": filename,
        "script": script,
        "options": {"srt": True, "slow": False, "worksheet": False, "format": "mp3"},
    }
    if roles:
        body["roles"] = roles
    result = http_json("POST", f"{TEXTTS_URL}/api/v1/dialogue", body)
    if not result.get("ok"):
        raise PtcError(f"textts refused the script: {result}")
    return result


def textts_outputs(result: dict) -> tuple[Path, Path, Path]:
    folder, base = Path(result["folder"]), result["filename"]
    audio, srt, timeline = (folder / f"{base}{s}" for s in (".mp3", ".srt", ".timeline.json"))
    missing = [str(p) for p in (audio, srt, timeline) if not p.exists()]
    if missing:
        raise PtcError(f"textts did not write {', '.join(missing)}")
    return audio, srt, timeline


# ---- OpenCut -------------------------------------------------------------


def find_opencut() -> str:
    env = os.environ.get("OPENCUT_BIN")
    if env:
        return env
    on_path = shutil.which("opencut")
    if on_path:
        return on_path
    for profile in ("release", "debug"):
        for name in ("opencut.exe", "opencut"):
            candidate = REPO / "target" / profile / name
            if candidate.exists():
                return str(candidate)
    raise PtcError("opencut not found: build it (`cargo build -p opencut-cli`) or set OPENCUT_BIN")


def run(cmd: list[str]) -> None:
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise PtcError(f"{' '.join(cmd[:3])} failed:\n{done.stderr.strip() or done.stdout.strip()}")


def apply_visuals(project: Path, visuals: str, karaoke: bool = False) -> None:
    """Renders the lesson's scenes (apps/intro `lesson build`) and makes them the project's picture."""
    if karaoke:
        # Listen to the voice first, so each word lights up when it is said.
        done = lesson_node("words", str(project.resolve()))
        if done.returncode != 0:
            raise PtcError("lesson words failed (run `node apps/intro/scripts/lesson.ts whisper-setup` once):\n"
                           + (done.stderr.strip() or done.stdout.strip()))
    done = lesson_node("build", str(Path(visuals).resolve()), str(project.resolve()), *(["--captions"] if karaoke else []))
    if done.returncode != 0:
        raise PtcError("lesson visuals failed:\n" + (done.stderr.strip() or done.stdout.strip()))


def add_question_markers(project_path: Path, questions: list[dict], starts: list[int]) -> int:
    """One `question` marker per question, at its first spoken line's cue (intro offset included)."""
    project = json.loads(project_path.read_text(encoding="utf-8"))
    cues = project.get("subtitles", [])
    markers = project.setdefault("markers", [])
    for question, first_line in zip(questions, starts):
        if first_line >= len(cues):
            raise PtcError(
                f"question {question['id']} starts at line {first_line}, but the project has {len(cues)} subtitles"
            )
        markers.append(
            {
                "time": round(cues[first_line]["start"], 3),
                "kind": "question",
                "label": question.get("code") or f"Q{question['id']}",
                "ref": f"qbank:{question['id']}",
            }
        )
    markers.sort(key=lambda m: m["time"])
    project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(questions)


def make_lesson(args: argparse.Namespace) -> dict:
    chapters: list[tuple[str, int]] = []
    from_script = Path(args.script).resolve() if args.script else None
    if from_script:
        if not from_script.exists():
            raise PtcError(f"no such script: {from_script}")
        questions: list[dict] = []
    elif args.question:
        questions = [qbank_question(i) for i in args.question]
    elif args.chapter is not None:
        questions = qbank_chapter_questions(args.chapter, args.limit)
    else:
        raise PtcError("give --question <id> (repeatable) or --chapter <id>")
    if not questions and not from_script:
        raise PtcError("no listening questions found")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = args.name or out.name
    warnings: list[str] = []
    if from_script:
        script, script_tr, chapters = parse_lesson_script(from_script)
        starts: list[int] = []
        base = re.sub(r"\.script(\.vi)?\.txt$|\.txt$", "", from_script.name)
        if not args.visuals:
            sibling = from_script.with_name(f"{base}.visuals.json")
            if sibling.exists():
                args.visuals = str(sibling)
        if args.visuals and args.visuals != "auto":
            # Before any voice is made: scenes that do not fit the script are found here, not after a render.
            warnings = check_scenes(args.visuals, from_script)
    else:
        script, script_tr, starts = build_script(questions)
    (out / f"{name}.script.txt").write_text(script, encoding="utf-8")
    translated_path = out / f"{name}.script.vi.txt"
    translated_path.write_text(script_tr, encoding="utf-8")
    if args.dry_run:
        return {"dry_run": True, "questions": [q["id"] for q in questions], "chapters": [c[0] for c in chapters],
                "warnings": warnings, "script": str(out / f"{name}.script.txt")}

    roles = None
    voices = Path(args.voices) if args.voices else REPO / "scripts" / "lesson_voices.json"
    if from_script and voices.exists():
        roles = json.loads(voices.read_text(encoding="utf-8"))
    result = textts_dialogue(args.title or name, name, script, roles)
    audio, srt, timeline = textts_outputs(result)
    opencut = find_opencut()
    project = out / f"{name}.project.json"
    cmd = [opencut, "import-textts", str(audio), "--srt", str(srt), "--timeline", str(timeline),
           "--script", str(translated_path), "--title", args.title or name, "-o", str(project)]
    for flag, value in (("--intro", args.intro), ("--outro", args.outro)):
        if value:
            cmd += [flag, value]
    for slide in args.slide or []:
        cmd += ["--slide", slide]
    run(cmd)

    if args.visuals:
        # The body picture: Remotion scenes timed by the project's cues. Before the mascot,
        # which is drawn over it.
        visuals = args.visuals
        if visuals == "auto":
            # Claude writes the scenes from the project's cues; look them over (and edit) before the next render.
            import opencut_scenes
            try:
                visuals = str(opencut_scenes.generate(project, out / f"{name}.visuals.json"))
            except opencut_scenes.ScenesError as error:
                raise PtcError(f"auto scenes failed: {error}") from error
        apply_visuals(project, visuals, karaoke=args.karaoke)

    if args.mascot:
        # After intro/outro, so poses sit on the final timeline: one per sentence.
        run([opencut, "mascot", str(project), "--avatar", args.mascot])

    # Cue times already include any intro, so markers follow the project.
    markers = add_question_markers(project, questions, starts) if questions else 0
    if chapters:
        markers += add_chapter_markers(project, chapters)

    video = None
    if args.render:
        video = out / f"{name}.mp4"
        cmd = [opencut, "render", str(project), "-o", str(video)]
        # --karaoke draws the subtitles itself; burning them in again would double them.
        if args.burn_subtitles and not (args.visuals and args.karaoke):
            cmd.append("--burn-subtitles")
        run(cmd)
    return {"project": str(project), "video": str(video) if video else None,
            "questions": [q["id"] for q in questions], "markers": markers,
            "duration_s": result.get("duration_s")}


def check() -> int:
    ok = True
    for label, url in (("QBank", f"{QBANK_URL}/api/questions?limit=1"), ("textts", f"{TEXTTS_URL}/api/v1/health")):
        try:
            http_json("GET", url, timeout=5)
            print(f"{label}: ok ({url.split('/api')[0]})")
        except PtcError as error:
            ok = False
            print(f"{label}: DOWN - {error}")
    try:
        print(f"opencut: {find_opencut()}")
    except PtcError as error:
        ok = False
        print(f"opencut: {error}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Check that QBank, textts and opencut are reachable")
    lesson = sub.add_parser("lesson", help="Listening questions from QBank -> lesson project (and video)")
    lesson.add_argument("--question", type=int, action="append", help="QBank question id; repeat for several")
    lesson.add_argument("--script", metavar="SCRIPT_TXT",
                        help="A lesson script (`[1] 日本語 // Tiếng Việt`, `## Chapter`) instead of QBank questions")
    lesson.add_argument("--voices", metavar="JSON",
                        help="With --script: role -> voice (default scripts/lesson_voices.json: 1 まい, 2 fumifumi, 3 花音)")
    lesson.add_argument("--chapter", type=int, help="QBank chapter id: every listening question in it")
    lesson.add_argument("--limit", type=int, default=0, help="With --chapter: at most this many questions")
    lesson.add_argument("--out", required=True, help="Output folder")
    lesson.add_argument("--name", help="File name (default: the folder name)")
    lesson.add_argument("--title")
    lesson.add_argument("--intro")
    lesson.add_argument("--outro")
    lesson.add_argument("--slide", action="append")
    lesson.add_argument("--mascot", metavar="AVATAR_DIR",
                        help="Chibi in the corner, changing pose per sentence (e.g. apps/intro/public/avatars/chibi)")
    lesson.add_argument("--visuals", metavar="VISUALS_JSON",
                        help="Scenes for the body (charts, diagrams...), timed by cue: apps/intro/scenes/*.visuals.json, "
                             "or `auto` to have Claude write them (needs ANTHROPIC_API_KEY)")
    lesson.add_argument("--karaoke", action="store_true",
                        help="With --visuals: subtitles lit word by word at the voice's pace (needs `bun run lesson whisper-setup` once); "
                             "replaces --burn-subtitles, so intro/outro lines are not burned in")
    lesson.add_argument("--render", action="store_true", help="Also render the video")
    lesson.add_argument("--burn-subtitles", action="store_true")
    lesson.add_argument("--dry-run", action="store_true", help="Only write the textts script")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            return check()
        print(json.dumps(make_lesson(args), ensure_ascii=False, indent=2))
        return 0
    except PtcError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
