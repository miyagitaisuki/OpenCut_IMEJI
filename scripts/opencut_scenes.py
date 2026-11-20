#!/usr/bin/env python3
"""Writes a lesson's scenes file (`*.visuals.json`) with Claude (standard library only).

Reads the cues of an OpenCut project (`opencut import-textts` made it), asks the
Claude API for scenes tied to those cues, checks them with `lesson check` and, if
they are not valid, shows the model its errors once. Review and edit the file
before rendering: `bun run lesson preview` shows every scene as a still.

The lesson's text (Japanese and its translation) is sent to the Claude API.

Environment: ANTHROPIC_API_KEY (required unless --prompt-only), ANTHROPIC_MODEL
(default claude-sonnet-5-5).

Examples:
  python scripts/opencut_scenes.py lessons/ch193/ch193.project.json
  python scripts/opencut_scenes.py lessons/ch193/ch193.project.json --prompt-only > prompt.txt
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
INTRO = REPO / "apps" / "intro"
API = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-5-5"


class ScenesError(RuntimeError):
    pass


def _lesson(*words: str, check: bool = True) -> subprocess.CompletedProcess:
    node = os.environ.get("OPENCUT_NODE") or shutil.which("node")
    if not node:
        raise ScenesError("needs Node.js (node 22+ on PATH)")
    done = subprocess.run([node, str(INTRO / "scripts" / "lesson.ts"), *words], cwd=INTRO,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and done.returncode != 0:
        raise ScenesError((done.stdout + done.stderr).strip())
    return done


def build_prompt(project: Path) -> str:
    return _lesson("prompt", str(project.resolve())).stdout


def ask(messages: list[dict], model: str, key: str) -> str:
    body = json.dumps({"model": model, "max_tokens": 8000, "messages": messages}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        raise ScenesError(f"Claude API {error.code}: {error.read().decode('utf-8', 'replace')[:400]}") from error
    except urllib.error.URLError as error:
        raise ScenesError(f"cannot reach the Claude API: {error.reason}") from error
    return "".join(block.get("text", "") for block in data.get("content", []))


def extract_json(text: str) -> dict:
    """The object in the reply, with or without a code fence around it."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = fenced.group(1) if fenced else text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ScenesError(f"the reply is not JSON ({error}):\n{text[:300]}") from error


def generate(project: Path, out: Path, model: str | None = None) -> Path:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ScenesError("set ANTHROPIC_API_KEY, or use --prompt-only and give the prompt to Claude yourself")
    model = model or os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    messages = [{"role": "user", "content": build_prompt(project)}]
    for attempt in (1, 2):
        reply = ask(messages, model, key)
        try:
            scenes = extract_json(reply)
        except ScenesError as error:
            problems = str(error)
        else:
            out.write_text(json.dumps(scenes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            done = _lesson("check", str(out), str(project.resolve()), check=False)
            if done.returncode == 0:
                for line in done.stdout.splitlines():
                    print(line, file=sys.stderr)
                return out
            problems = done.stdout.strip()
        if attempt == 2:
            raise ScenesError(f"the scenes are still not valid after a second try:\n{problems}")
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": f"That file has errors:\n{problems}\n\nReturn the corrected JSON object only."}]
    raise AssertionError("unreachable")


# ---- Shorts ----------------------------------------------------------------

SHORT_MAX_SECONDS = 55.0  # a YouTube Short is under 60 s; the cut-off leaves room for the outro


def _scene_last_cue(scenes: list[dict], index: int, cue_count: int) -> int:
    """The last cue a scene covers: its `until_cue`, else the cue before the next scene."""
    scene = scenes[index]
    if scene.get("until_cue") is not None:
        return min(int(scene["until_cue"]), cue_count - 1)
    nxt = scenes[index + 1]["cue"] if index + 1 < len(scenes) else cue_count
    return min(nxt - 1, cue_count - 1)


def pick_short(visuals_path: Path, project_path: Path, max_seconds: float = SHORT_MAX_SECONDS) -> dict:
    """The grammar point worth a Short: a `grammar` scene, its `examples`, and a `practice` question
    right after them when there is one. The Short is one unbroken stretch of the lesson's voice, so
    a practice scene that is not directly after the examples is not used.

    Score: examples (up to 4), pattern parts, and 4 for a practice question. Returns the chosen
    candidate with its reasons; raises ScenesError when nothing fits under `max_seconds`."""
    visuals = json.loads(visuals_path.read_text(encoding="utf-8"))
    project = json.loads(project_path.read_text(encoding="utf-8"))
    cues = project.get("subtitles", [])
    scenes = sorted(visuals.get("scenes", []), key=lambda sc: sc["cue"])
    candidates: list[dict] = []
    for gi, grammar in enumerate(scenes):
        if grammar.get("template") != "grammar":
            continue
        examples = scenes[gi + 1] if gi + 1 < len(scenes) else None
        if not examples or examples.get("template") != "examples":
            continue
        practice = scenes[gi + 2] if gi + 2 < len(scenes) and scenes[gi + 2].get("template") == "practice" else None

        def span(end_index: int) -> tuple[float, float]:
            last = _scene_last_cue(scenes, end_index, len(cues))
            return cues[grammar["cue"]]["start"], cues[last]["end"] + 0.8

        start, end = span(gi + 2 if practice else gi + 1)
        if practice and end - start >= max_seconds:  # too long with the question: keep the pattern and examples
            practice = None
            start, end = span(gi + 1)
        if end - start >= max_seconds:
            continue
        items = len(examples.get("items", []))
        parts = len(grammar.get("parts", []))
        score = 2 * min(items, 4) + parts + (4 if practice else 0)
        reasons = [f"{items} example(s)", f"{parts} pattern part(s)"]
        if practice:
            reasons.append(f"practice question at cue {practice['cue']}")
        candidates.append({"grammar_cue": grammar["cue"], "practice_cue": practice["cue"] if practice else None,
                           "duration_s": round(end - start, 2), "score": score, "reasons": reasons})
    if not candidates:
        raise ScenesError("no grammar scene followed by examples fits under "
                          f"{max_seconds:.0f} s: write a Short by hand (`lesson.ts short --grammar <cue>`)")
    # Highest score; on a tie, the earlier one in the lesson.
    return max(candidates, key=lambda c: (c["score"], -c["grammar_cue"]))


def make_short(visuals_path: Path, project_path: Path, out: Path | None = None) -> dict:
    """Picks the Short and renders it beside the main video: a vertical 1080x1920 clip, under 60 s,
    with the voice cut from the lesson. Nothing is uploaded."""
    choice = pick_short(visuals_path, project_path)
    target = out or project_path.with_name(
        re.sub(r"\.project\.json$|\.json$", "", project_path.name) + f".short-{choice['grammar_cue']}.mp4")
    _lesson("short", str(visuals_path.resolve()), str(project_path.resolve()),
            "--grammar", str(choice["grammar_cue"]), "-o", str(target.resolve()))
    return {**choice, "path": str(target)}


def short_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="opencut_scenes.py short",
                                     description="Pick a lesson's best grammar point (with its practice question) and render it as a Short.")
    parser.add_argument("visuals", help="x.visuals.json: the lesson's scenes")
    parser.add_argument("project", help="x.project.json: the lesson's cues and voice")
    parser.add_argument("-o", "--out", help="the Short's .mp4 (default: next to the project, x.short-<cue>.mp4)")
    parser.add_argument("--dry-run", action="store_true", help="only print the choice; render nothing")
    args = parser.parse_args(argv)
    try:
        if args.dry_run:
            print(json.dumps(pick_short(Path(args.visuals), Path(args.project)), ensure_ascii=False, indent=2))
            return 0
        result = make_short(Path(args.visuals), Path(args.project), Path(args.out) if args.out else None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ScenesError as error:
        print(f"opencut_scenes: {error}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "short":
        return short_main(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", help="x.project.json from `opencut import-textts`")
    parser.add_argument("-o", "--out", help="scenes file (default: next to the project, x.visuals.json)")
    parser.add_argument("--model", help=f"default {DEFAULT_MODEL} or $ANTHROPIC_MODEL")
    parser.add_argument("--prompt-only", action="store_true", help="print the prompt and stop (no API call)")
    args = parser.parse_args(argv)
    project = Path(args.project)
    try:
        if args.prompt_only:
            sys.stdout.write(build_prompt(project))
            return 0
        out = Path(args.out) if args.out else project.with_name(re.sub(r"\.project\.json$|\.json$", "", project.name) + ".visuals.json")
        print(generate(project, out, args.model))
        return 0
    except ScenesError as error:
        print(f"opencut_scenes: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
