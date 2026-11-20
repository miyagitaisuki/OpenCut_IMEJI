#!/usr/bin/env python3
"""Homographs: kanji whose reading depends on the words around them (standard library only).

  python scripts/homographs.py check <project.json>            list what the rules resolve and what they cannot
  python scripts/homographs.py check <project.json> --apply    write the resolved readings into the project's text

A rule decides a reading only when the context settles it. Where it cannot (何で: なにで or なんで),
the word is listed as unresolved; that is the case for an agent (or a person) to read in the sentence.
Resolved readings are written as furigana, `行{い}く`, which textts and the engine both read as written.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 行: the reading of the kanji part depends on the okurigana that follows (行く = いく, 行う = おこなう).
# Compounds where 行 is read ぎょう/こう/ゆく-style do not start with these prefixes, see COMPOUND_PREFIX.
GYO_BY_OKURIGANA = {"う": "おこな", "き": "い", "く": "い", "け": "い", "か": "い", "こ": "い", "っ": "い"}
GYO_COMPOUND_PREFIX = set("旅銀修急飛進")  # 旅行 (りょこう), 銀行 (ぎんこう): not the verb

# 何: なん before counters and で, なに otherwise. 何で is ambiguous (なにで: "by what"; なんで: "why").
NAN_BEFORE = set("年回番時人度号月分階")

HOMOGRAPHS = ("行", "何", "方", "今日", "明日")


def _rule(word: str, index: int, text: str) -> tuple[str | None, str]:
    """(reading of the word's kanji part, or None; the rule's name or the reason it stopped)."""
    nxt = text[index + len(word)] if index + len(word) < len(text) else ""
    prv = text[index - 1] if index > 0 else ""
    if word == "行":
        if prv in GYO_COMPOUND_PREFIX:
            return None, "skip"  # 旅行/銀行: the compound's own reading, nothing to decide here
        if nxt in GYO_BY_OKURIGANA:
            return GYO_BY_OKURIGANA[nxt], "行 + okurigana"
        return None, "行 without okurigana (行き先, 行事 ...): reading needs the word"
    if word == "何":
        if nxt == "で":
            return None, "何で: なにで (by what) or なんで (why) depends on the sentence"
        if nxt in NAN_BEFORE:
            return "なん", "何 + counter"
        return "なに", "何 + other"
    if word == "方":
        if prv in set("どっちどちらこっちそっちあっち両反双") or text[max(0, index - 2):index] in ("どっち", "どちら") \
                or (prv == "の" and text[index + 1:index + 2] == "が"):
            return "ほう", "the side/direction of a comparison (どっちの方, の方が)"
        return "かた", "方 as a person or a way (default)"
    if word == "今日":
        return "きょう", "今日 (default)"
    if word == "明日":
        return "あした", "明日 (default; あす is the formal alternative)"
    return None, "no rule"


def resolve(text: str) -> tuple[list[dict], list[dict]]:
    """(resolved, unresolved) for one line. Words already carrying furigana (`行{い}`) are skipped."""
    resolved: list[dict] = []
    unresolved: list[dict] = []
    for word in HOMOGRAPHS:
        for m in re.finditer(re.escape(word), text):
            index = m.start()
            if index + len(word) < len(text) and text[index + len(word)] == "{":
                continue  # already annotated
            if any(text[index:index + len(word)] == r["word"] and r["index"] == index for r in resolved + unresolved):
                continue
            reading, why = _rule(word, index, text)
            if why == "skip":
                continue
            entry = {"word": word, "index": index, "reading": reading, "why": why}
            (resolved if reading else unresolved).append(entry)
    return resolved, unresolved


def annotate(text: str) -> tuple[str, list[dict], list[dict]]:
    """The line with furigana written for every resolved word, plus what was changed and what was not."""
    resolved, unresolved = resolve(text)
    out = text
    for r in sorted(resolved, key=lambda r: -r["index"]):
        end = r["index"] + len(r["word"])
        # One kanji (行, 何, 方) takes the reading; a compound (今日, 明日) takes it as a whole.
        span = r["word"][:1] if len(r["word"]) == 1 else r["word"]
        out = out[:r["index"]] + f"{span}{{{r['reading']}}}" + out[r["index"] + len(span):]
    return out, resolved, unresolved


def check(project_path: Path, apply: bool) -> dict:
    project = json.loads(project_path.read_text(encoding="utf-8"))
    report: dict = {"changes": [], "unresolved": []}
    for i, cue in enumerate(project.get("subtitles", [])):
        new_text, resolved, unresolved = annotate(cue.get("text", ""))
        for r in resolved:
            report["changes"].append({"line": i, "word": r["word"], "reading": r["reading"], "why": r["why"]})
        for u in unresolved:
            report["unresolved"].append({"line": i, "word": u["word"], "why": u["why"], "text": cue.get("text", "")})
        if apply and resolved:
            cue["text"] = new_text
    if apply and report["changes"]:
        project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check")
    c.add_argument("project")
    c.add_argument("--apply", action="store_true", help="write the resolved readings into the project")
    args = parser.parse_args(argv)
    data = check(Path(args.project), args.apply)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
