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
    node = shutil.which("node")
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


def main(argv: list[str] | None = None) -> int:
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
