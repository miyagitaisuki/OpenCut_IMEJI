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
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lesson_qc  # noqa: E402  same folder: reading dictionary, word candidates, engine check

REPO = Path(__file__).resolve().parent.parent
QBANK_URL = os.environ.get("QBANK_URL", "http://127.0.0.1:8765").rstrip("/")
TEXTTS_URL = os.environ.get("TEXTTS_URL", "http://127.0.0.1:8000").rstrip("/")
AIVIS_URL = os.environ.get("AIVIS_URL", "http://127.0.0.1:10101").rstrip("/")
# A kanji run that is not followed by furigana: textts has to guess its reading.
_KANJI_NO_RUBY = re.compile(r"(?<![一-鿿々])[一-鿿々]+(?![一-鿿々{])")
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


def apply_chapters(script: Path, project_path: Path) -> int:
    """Puts the script's `##` chapters in a project that is already voiced (no new voice or render), and
    rewrites `<name>.markers.json` beside it, as `opencut render` does."""
    _, _, chapters = parse_lesson_script(script)
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["markers"] = [m for m in project.get("markers", []) if m.get("kind") != "chapter"]
    project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    add_chapter_markers(project_path, chapters)
    project = json.loads(project_path.read_text(encoding="utf-8"))
    clips = [a for a in project.get("audio", []) if a.get("duration")]
    duration = max((a.get("start", 0) + a["duration"] for a in clips), default=0)
    out = project_path.with_name(re.sub(r"\.project\.json$|\.json$", "", project_path.name) + ".markers.json")
    out.write_text(json.dumps({"title": project.get("title", ""), "duration_seconds": duration, "markers": project["markers"]},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(chapters)


def lesson_node(*args: str) -> subprocess.CompletedProcess:
    env = tool_env()
    node = env.get("OPENCUT_NODE") or shutil.which("node")
    if not node:
        raise PtcError("needs Node.js (node 22+ on PATH, or OPENCUT_NODE)")
    script = REPO / "apps" / "intro" / "scripts" / "lesson.ts"
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


def textts_dialogue(title: str, filename: str, script: str, roles: dict | None = None, level: str | None = None) -> dict:
    body = {
        "title": title,
        "filename": filename,
        "script": script,
        "options": {"srt": True, "slow": False, "worksheet": False, "format": "mp3"},
    }
    if roles:
        body["roles"] = roles
    if level:  # N5 reads about 0.85x with longer pauses; N1 is almost natural speed
        body["options"]["level"] = level
    try:
        result = http_json("POST", f"{TEXTTS_URL}/api/v1/dialogue", body)
    except PtcError as error:
        if "HTTP 500" in str(error):
            ffmpeg_dir = tool_env().get("OPENCUT_FFMPEG_DIR")
            hint = (f"; restart textts with {ffmpeg_dir} on PATH" if ffmpeg_dir
                    else "; restart textts with an ffmpeg binary on PATH (see `opencut env`)")
            raise PtcError(f"textts failed to build audio (HTTP 500): it most likely cannot find ffmpeg{hint}") from error
        raise
    if not result.get("ok"):
        raise PtcError(f"textts refused the script: {result}")
    return result


def textts_outputs(result: dict, dest: Path) -> tuple[Path, Path, Path]:
    """The audio, subtitles and timeline textts made. Uses the file when this machine has it (textts on
    the host); otherwise downloads it from textts' /files/ URL into `dest`, so the pipeline also runs in a
    container, where textts' folder path does not exist."""
    files = result.get("files", {})
    dest.mkdir(parents=True, exist_ok=True)
    found: list[Path] = []
    for key, ext in (("audio", ".mp3"), ("srt", ".srt"), ("timeline_json", ".timeline.json")):
        local = Path(files[key]) if files.get(key) else Path(result["folder"]) / f"{result['filename']}{ext}"
        if local.exists():
            found.append(local)
            continue
        url = files.get(f"{key}_url")
        if not url:
            raise PtcError(f"textts did not write {local}, and gave no download URL for it")
        # textts reports http://127.0.0.1:8000/files/...; fetch it from the TEXTTS_URL this run uses instead.
        target = dest / local.name
        request_url = TEXTTS_URL + urllib.parse.urlparse(url).path
        try:
            with urllib.request.urlopen(request_url, timeout=120) as response:
                target.write_bytes(response.read())
        except (urllib.error.URLError, OSError) as error:
            raise PtcError(f"cannot download {request_url}: {error}") from error
        found.append(target)
    return found[0], found[1], found[2]


def textts_check_audio(script: str, roles: dict | None, threshold: float) -> dict:
    """textts listens back to every line and scores it against the script (`results[]` with ok/score/heard)."""
    body: dict = {"script": script, "engine": "aivis", "threshold": threshold}
    if roles:
        body["roles"] = roles
    return http_json("POST", f"{TEXTTS_URL}/api/v1/check-audio", body, timeout=900)


def textts_preview(script: str) -> list[dict]:
    """textts' own furigana suggestions per line (`items[]` with `display`, `annotated`, `reading`)."""
    return http_json("POST", f"{TEXTTS_URL}/api/v1/preview-script", {"script": script}, timeout=120).get("items", [])


def unannotated_lines(script: str) -> list[str]:
    """Spoken lines with kanji but no furigana: the voice guesses those readings."""
    return [l.strip() for l in script.splitlines() if _is_speech(l) and _KANJI_NO_RUBY.search(l)]


def voice_with_qc(script: str, roles: dict | None, args: argparse.Namespace, title: str, name: str) -> tuple[dict, dict]:
    """Voices the script, has textts listen back to each line, and where a line is read wrong teaches
    textts the kanji words of that line (from the script's furigana) and voices the script again."""
    if args.no_qc:
        return textts_dialogue(title, name, script, roles, args.level), {"skipped": True}
    attempts = max(1, args.max_attempts)
    history: list[dict] = []
    taught: set[tuple[str, str]] = set()
    result: dict = {}
    for attempt in range(1, attempts + 1):
        result = textts_dialogue(title, name, script, roles, args.level)
        qc = textts_check_audio(script, roles, args.qc_threshold)
        suspects = [r for r in qc.get("results", []) if not r.get("ok")]
        entry = {"attempt": attempt, "checked": qc.get("checked"),
                 "suspicious": [{"id": r.get("id"), "display": r.get("display"), "heard": r.get("heard"),
                                 "score": r.get("score")} for r in suspects]}
        history.append(entry)
        if not suspects:
            return result, {"ok": True, "attempts": attempt, "history": history}
        pairs = [p for r in suspects for p in lesson_qc.word_candidates(r.get("display") or "")]
        new_pairs = [p for p in dict.fromkeys(pairs) if p not in taught]
        if not new_pairs:  # every word was already taught: voicing again would change nothing
            break
        taught.update(new_pairs)
        entry["readings_added"] = lesson_qc.add_readings(new_pairs, TEXTTS_URL)
        if not entry["readings_added"]:
            break
    return result, {"ok": False, "attempts": len(history), "history": history}


def run_engine_qc(project: Path, voices: Path) -> dict:
    """AivisSpeech's own reading of every line vs the furigana (lesson_qc engine). Teaches the readings
    it finds; `retry` is True only when the reading dictionary actually changed (a voice again can help)."""
    before = lesson_qc.textts_readings(TEXTTS_URL)
    code = lesson_qc.engine(project, voices, AIVIS_URL, fix=True)
    if code == 2:
        return {"ok": None, "note": "AivisSpeech did not answer; engine check skipped", "retry": False}
    after = lesson_qc.textts_readings(TEXTTS_URL)
    return {"ok": code == 0, "retry": after != before, "readings_added": sorted(set(after) - set(before))}


# ---- OpenCut -------------------------------------------------------------


_ENV_CACHE: dict | None = None


def opencut_env() -> dict:
    """`opencut env --json`: the FFmpeg binaries, Node and what is missing. Printed even when it exits 1."""
    cmd = [find_opencut(), "env"]
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError as error:
        raise PtcError(f"`opencut env` printed no report: {done.stderr.strip() or error}") from error


def tool_env() -> dict:
    """The process environment with the resolved ffmpeg/ffprobe/node folders first on PATH, so every
    child (lesson.ts, `lesson words`, opencut) uses the same binaries the report names. Cached."""
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE
    env = dict(os.environ)
    try:
        report = opencut_env()
    except PtcError:
        _ENV_CACHE = env  # no opencut yet: fall back to the plain environment (check() reports it)
        return env
    folders: list[str] = []
    for key in ("ffmpeg", "ffprobe", "node"):
        tool = report.get(key)
        if tool and tool.get("path"):
            folders.append(str(Path(tool["path"]).parent))
            env[f"OPENCUT_{key.upper()}"] = tool["path"]  # what the Python and TS helpers read
            if key == "ffmpeg":
                env["OPENCUT_FFMPEG_DIR"] = str(Path(tool["path"]).parent)
    env["PATH"] = os.pathsep.join(dict.fromkeys(folders + [env.get("PATH", "")]))
    _ENV_CACHE = env
    return env


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
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=tool_env())
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
    """Builds the lesson; when the engine check finds a line it can fix (a reading now taught), builds it
    again, up to --max-attempts times, so the teacher only sees what the pipeline could not repair."""
    attempts = max(1, args.max_attempts)
    for n in range(1, attempts + 1):
        out = _build_once(args, last=(n == attempts))
        if not out.pop("_retry", False):
            out["qc"]["build_attempts"] = n
            return out
        print(f"attempt {n}: the engine check taught textts new readings; building the lesson again", file=sys.stderr)
    raise AssertionError("unreachable")


def _resolve_scenes_arg(args: argparse.Namespace) -> None:
    """With --script and no --visuals: use the scenes file next to the script when there is one."""
    if args.script and not args.visuals:
        from_script = Path(args.script).resolve()
        base = re.sub(r"\.script(\.vi)?\.txt$|\.txt$", "", from_script.name)
        sibling = from_script.with_name(f"{base}.visuals.json")
        if sibling.exists():
            args.visuals = str(sibling)


def stage_tts(args: argparse.Namespace, out: Path, name: str) -> dict:
    """Stage `tts`: the script (QBank questions, or a lesson file) voiced by textts, with the listen-back QC.
    Returns what the later stages need; the caller keeps it in <name>.tts.json."""
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

    warnings: list[str] = []
    starts: list[int] = []
    if from_script:
        script, script_tr, chapters = parse_lesson_script(from_script)
        if args.visuals and args.visuals != "auto":
            # Before any voice is made: scenes that do not fit the script are found here, not after a render.
            warnings = check_scenes(args.visuals, from_script)
    else:
        script, script_tr, starts = build_script(questions)
    (out / f"{name}.script.txt").write_text(script, encoding="utf-8")
    # With --script the input is never overwritten (it may live in this folder and holds the `##` chapter
    # lines); what OpenCut imports is a cleaned copy beside it.
    translated_path = out / (f"{name}.import.txt" if from_script else f"{name}.script.vi.txt")
    translated_path.write_text(script_tr, encoding="utf-8")
    if args.dry_run:
        return {"dry_run": True, "questions": [q["id"] for q in questions], "chapters": [c[0] for c in chapters],
                "warnings": warnings, "script": str(out / f"{name}.script.txt"),
                "unannotated_lines": unannotated_lines(script)[:20], "qc": {}}

    roles = None
    voices = Path(args.voices) if args.voices else REPO / "scripts" / "lesson_voices.json"
    if from_script and voices.exists():
        roles = json.loads(voices.read_text(encoding="utf-8"))
    qc: dict = {"unannotated_lines": unannotated_lines(script)[:20]}
    result, voice_qc = voice_with_qc(script, roles, args, args.title or name, name)
    qc["voice"] = voice_qc
    audio, srt, timeline = textts_outputs(result, out / "textts")
    return {"dry_run": False, "name": name, "title": args.title or name, "questions": questions,
            "starts": starts, "chapters": [list(c) for c in chapters], "translated": str(translated_path),
            "audio": str(audio), "srt": str(srt), "timeline": str(timeline),
            "duration_s": result.get("duration_s"), "warnings": warnings, "qc": qc}


def stage_scenes(args: argparse.Namespace, out: Path, name: str, state: dict) -> dict:
    """Stage `scenes`: import the voice into a project, draw the scenes, the mascot and the markers, then the
    engine check. With --visuals auto the scenes Claude wrote are kept when the cue count has not changed,
    so editing a line does not call Claude again. Sets state: project, markers, retry (engine taught readings)."""
    opencut = find_opencut()
    project = out / f"{name}.project.json"
    cmd = [opencut, "import-textts", state["audio"], "--srt", state["srt"], "--timeline", state["timeline"],
           "--script", state["translated"], "--title", state["title"], "-o", str(project)]
    for flag, value in (("--intro", args.intro), ("--outro", args.outro)):
        if value:
            cmd += [flag, value]
    for slide in args.slide or []:
        cmd += ["--slide", slide]
    run(cmd)

    qc = state["qc"]
    if args.visuals:
        # The body picture: Remotion scenes timed by the project's cues. Before the mascot,
        # which is drawn over it.
        visuals = args.visuals
        if visuals == "auto":
            sibling = out / f"{name}.visuals.json"
            cues_now = len(json.loads(project.read_text(encoding="utf-8")).get("subtitles", []))
            if sibling.exists() and state.get("visuals_cues") == cues_now:
                visuals = str(sibling)  # same cue layout: the scenes already written are kept
            else:
                import opencut_scenes
                try:
                    visuals = str(opencut_scenes.generate(project, sibling))
                except opencut_scenes.ScenesError as error:
                    raise PtcError(f"auto scenes failed: {error}") from error
                state["visuals_cues"] = cues_now
            args.visuals = visuals  # a later pass of this lesson reuses these scenes, not new ones
        apply_visuals(project, visuals, karaoke=args.karaoke)

    if args.mascot:
        # After intro/outro, so poses sit on the final timeline: one per sentence.
        run([opencut, "mascot", str(project), "--avatar", args.mascot])

    # Cue times already include any intro, so markers follow the project.
    markers = add_question_markers(project, state["questions"], state["starts"]) if state["questions"] else 0
    if state["chapters"]:
        markers += add_chapter_markers(project, [tuple(c) for c in state["chapters"]])

    # Engine check: AivisSpeech's own reading of each line against the furigana. Done before rendering,
    # so a line it can fix is fixed by a new voice pass instead of being rendered wrong.
    engine_retry = False
    if not args.no_qc:
        voices_file = Path(args.voices) if args.voices else REPO / "scripts" / "lesson_voices.json"
        qc["engine"] = run_engine_qc(project, voices_file)
        engine_retry = bool(qc["engine"].get("retry"))
    state.update(project=str(project), markers=markers, retry=engine_retry)
    return state


def stage_render(args: argparse.Namespace, out: Path, name: str, state: dict, stage: str) -> dict:
    """Stage `render`: the video (always in this stage; with `all` only when --render), the Short, and the
    QBank manifest. Writes <name>.qc.json."""
    opencut = find_opencut()
    project = Path(state["project"])
    qc = state["qc"]
    video = None
    if args.render or stage == "render":
        video = out / f"{name}.mp4"
        cmd = [opencut, "render", str(project), "-o", str(video)]
        # --karaoke draws the subtitles itself; burning them in again would double them.
        if args.burn_subtitles and not (args.visuals and args.karaoke):
            cmd.append("--burn-subtitles")
        run(cmd)

    if args.short:
        # The Short beside the main video: a grammar point with its practice question, vertical, under 60 s.
        visuals = Path(args.visuals) if args.visuals and args.visuals != "auto" else out / f"{name}.visuals.json"
        if visuals.exists():
            import opencut_scenes
            try:
                qc["short"] = opencut_scenes.make_short(visuals, project)
            except opencut_scenes.ScenesError as error:
                qc["short"] = {"error": str(error)}
        else:
            qc["short"] = {"error": "needs --visuals (scenes) to pick a grammar point"}

    questions = state["questions"]
    qbank = write_qbank_manifest(out, name, questions, Path(state["audio"]), qc) if questions else None
    report = {"project": str(project), "video": str(video) if video else None,
              "questions": [q["id"] for q in questions], "markers": state.get("markers", 0),
              "duration_s": state.get("duration_s"), "qc": qc, "qbank": str(qbank) if qbank else None}
    (out / f"{name}.qc.json").write_text(json.dumps(qc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _build_once(args: argparse.Namespace, last: bool = True) -> dict:
    """One pass over the stages. `--stage tts|scenes|render` runs one stage; its outputs are kept in
    <name>.tts.json and the project, so a later stage (or a rerun of one stage) does not redo the others.
    `all` (default) runs them in order, and voices again when the engine taught readings (not on `last`)."""
    stage = getattr(args, "stage", None) or "all"
    _resolve_scenes_arg(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = args.name or out.name
    state_path = out / f"{name}.tts.json"

    if stage in ("all", "tts"):
        previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        state = stage_tts(args, out, name)
        if state.get("dry_run"):
            return state
        state["visuals_cues"] = previous.get("visuals_cues")  # kept: the scenes stage compares cue counts
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if stage == "tts":
            return {"stage": "tts", "state": str(state_path), "qc": state["qc"]}
    else:
        if not state_path.exists():
            raise PtcError(f"{state_path.name} is missing: run the tts stage first")
        state = json.loads(state_path.read_text(encoding="utf-8"))

    if stage in ("all", "scenes"):
        state = stage_scenes(args, out, name, state)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if stage == "scenes":
            return {"stage": "scenes", "project": state["project"], "qc": state["qc"], "retry": state["retry"]}
        if state["retry"] and not last:
            return {"_retry": True, "qc": state["qc"]}

    report = stage_render(args, out, name, state, stage)
    report["_retry"] = False
    return report


def write_qbank_manifest(out: Path, name: str, questions: list[dict], audio: Path, qc: dict) -> Path:
    """What to write back to QBank, for the QBank MCP tools (attach_audio, set_status): the audio of a
    single-question lesson, and the QC verdict. Status is never set here: the teacher approves in QBank."""
    voice_ok = bool(qc.get("voice", {}).get("ok", qc.get("voice", {}).get("skipped")))
    engine_ok = qc.get("engine", {}).get("ok") is not False
    path = out / f"{name}.qbank.json"
    manifest = {
        "lesson": name,
        "qc_passed": voice_ok and engine_ok,
        "questions": [{"id": q["id"], "code": q.get("code"), "status": q.get("status"),
                       "chapter_id": q.get("chapter_id")} for q in questions],
        "audio": str(audio),
        "actions": [],
    }
    if len(questions) == 1 and manifest["qc_passed"]:
        manifest["actions"].append({"tool": "attach_audio", "question_id": questions[0]["id"], "file_path": str(audio)})
    elif len(questions) == 1:
        manifest["actions"].append({"tool": "none", "reason": "QC did not pass; review qc.json before attaching"})
    else:
        manifest["actions"].append({"tool": "none", "reason": "several questions share one lesson audio; attach it to a passage or the chapter by hand"})
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


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
        report = opencut_env()
        print(f"opencut: {report['opencut']['path']}")
        for key in ("ffmpeg", "ffprobe", "node"):
            tool = report.get(key)
            print(f"  {key}: {tool['path'] + ' (' + (tool.get('version') or '?') + ')' if tool else 'MISSING'}")
        for item in report.get("issues", []):
            ok = False
            print(f"  ISSUE: {item}")
        for item in report.get("warnings", []):
            print(f"  warning: {item}")
    except PtcError as error:
        ok = False
        print(f"opencut: {error}")
    return 0 if ok else 1


def qc_script(script_path: Path, args: argparse.Namespace) -> dict:
    """Script QC without building anything: textts' furigana suggestions, lines missing furigana, and
    the listen-back check (voices the script once, scores each line)."""
    script, _, _ = parse_lesson_script(script_path)
    roles = None
    voices = Path(args.voices) if args.voices else REPO / "scripts" / "lesson_voices.json"
    if voices.exists():
        roles = json.loads(voices.read_text(encoding="utf-8"))
    qc = textts_check_audio(script, roles, args.qc_threshold)
    suspicious = [r for r in qc.get("results", []) if not r.get("ok")]
    return {"script": str(script_path), "unannotated_lines": unannotated_lines(script)[:20],
            "suspicious": suspicious, "checked": qc.get("checked"), "ok": not suspicious}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Check that QBank, textts and opencut are reachable")
    qc_cmd = sub.add_parser("qc", help="QC a lesson script with textts (listen-back check) without building the lesson")
    qc_cmd.add_argument("--script", required=True)
    qc_cmd.add_argument("--voices", metavar="JSON")
    qc_cmd.add_argument("--qc-threshold", type=float, default=0.9)
    chap = sub.add_parser("chapters", help="Put a script's ## chapters into an already voiced project")
    chap.add_argument("--script", required=True)
    chap.add_argument("--project", required=True)
    lesson = sub.add_parser("lesson", help="Listening questions from QBank -> lesson project (and video)")
    lesson.add_argument("--question", type=int, action="append", help="QBank question id; repeat for several")
    lesson.add_argument("--script", metavar="SCRIPT_TXT",
                        help="A lesson script (`[1] 日本語 // Tiếng Việt`, `## Chapter`) instead of QBank questions")
    lesson.add_argument("--level", choices=["N5", "N4", "N3", "N2", "N1"],
                        help="textts reading speed and pauses for this learner level (N5 slowest)")
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
    lesson.add_argument("--short", action="store_true",
                        help="Also render a Short (vertical, under 60 s) beside the video: a grammar point and its practice question (needs --visuals)")
    lesson.add_argument("--burn-subtitles", action="store_true")
    lesson.add_argument("--dry-run", action="store_true", help="Only write the textts script")
    lesson.add_argument("--stage", choices=["all", "tts", "scenes", "render"], default="all",
                        help="Run one stage: tts (voice, QC), scenes (project, scenes, mascot, engine QC), render "
                             "(video, Short). Each keeps its output in <name>.tts.json or the project, so the "
                             "next stage runs later without the earlier ones (default all)")
    lesson.add_argument("--no-qc", action="store_true", help="Skip the listen-back check and the engine check")
    lesson.add_argument("--qc-threshold", type=float, default=0.9, help="Listen-back score below which a line is wrong (0.5-1)")
    lesson.add_argument("--max-attempts", type=int, default=2,
                        help="Voice and build again when QC taught textts new readings (default 2)")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            return check()
        if args.command == "qc":
            report = qc_script(Path(args.script), args)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ok"] else 1
        if args.command == "chapters":
            print(f"{apply_chapters(Path(args.script), Path(args.project))} chapters")
            return 0
        print(json.dumps(make_lesson(args), ensure_ascii=False, indent=2))
        return 0
    except PtcError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
