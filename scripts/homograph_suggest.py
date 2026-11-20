#!/usr/bin/env python3
"""Suggested readings for homographs, written for a reviewer to accept or reject (standard library, plus
fugashi when it is installed). Nothing is changed in the project until a reviewer accepts a suggestion.

  python scripts/homograph_suggest.py suggest <project.json> [-o review.json]
      one entry per homograph occurrence that has no furigana yet: the rule's reading, the tagger's reading
      (when fugashi is installed) and whether they agree. Entries start with "accepted": null.

  (edit the review file: set "accepted" to true or false on each entry; for a case the rules could not decide,
   the reviewer writes the reading in "reading" before accepting)

  python scripts/homograph_suggest.py apply <review.json> <project.json>
      writes the accepted readings into the project's text, the same way homographs.py --apply does.
      Only entries with "accepted": true are written.

fugashi (MeCab + UniDic) is the second reader: `pip install fugashi unidic-lite` in a Python that has wheels for
it (3.10 here), and set OPENCUT_TAGGER_PYTHON to that interpreter if this one lacks it. Without fugashi, only
the rules are used; the review still lists every case the rules could not decide.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import homographs  # noqa: E402


def _ensure_tagger_interpreter() -> None:
    """fugashi (MeCab + UniDic) has wheels for some Python versions only. When this interpreter lacks it and
    OPENCUT_TAGGER_PYTHON names one that has it, run there instead (same arguments)."""
    import importlib.util
    import os
    import subprocess
    if importlib.util.find_spec("fugashi") is not None:
        return
    other = os.environ.get("OPENCUT_TAGGER_PYTHON")
    if other and Path(other).resolve() != Path(sys.executable).resolve():
        raise SystemExit(subprocess.call([other, __file__, *sys.argv[1:]]))


def tagger_for():
    try:
        import fugashi
    except ImportError:
        return None
    return fugashi.Tagger()


def tagger_reading(tagger, sentence: str, word: str) -> str | None:
    if tagger is None:
        return None
    import eval_homographs
    return eval_homographs.tagger_reading(tagger, sentence, word)


_KANJI = re.compile(r"[一-鿿]")


def tagger_words(tagger, text: str) -> list[tuple[str, int, str]]:
    """(surface, index, kana) for each token with kanji that has no furigana already."""
    out: list[tuple[str, int, str]] = []
    pos = 0
    for token in tagger(text):
        start = text.find(token.surface, pos)
        if start < 0:
            continue
        pos = start + len(token.surface)
        after = text[pos:pos + 1]
        if _KANJI.search(token.surface) and after != "{":
            kana = token.feature.kana or token.surface
            out.append((token.surface, start, homographs_hira(kana)))
    return out


def homographs_hira(text: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def suggest(project_path: Path) -> dict:
    project = json.loads(project_path.read_text(encoding="utf-8"))
    tagger = tagger_for()
    entries: list[dict] = []
    for i, cue in enumerate(project.get("subtitles", [])):
        text = cue.get("text", "")
        resolved, unresolved = homographs.resolve(text)
        items = [(r, True) for r in resolved] + [(u, False) for u in unresolved]
        if tagger is not None:
            # Every kanji word the tagger reads, not only the five with rules: 市場, 辛い, ...
            seen = {it["index"] for it, _ in items}  # a word already covered by a rule keeps its entry
            for word, index, reading in tagger_words(tagger, text):
                if index not in seen:
                    items.append(({"word": word, "index": index, "reading": None, "why": "tagger only"}, False))
        for item, decided in items:
            word = item["word"]
            if item["why"] == "tagger only":
                hira = next((k for _, i, k in tagger_words(tagger, text) if i == item["index"]), None)
            else:
                hira = tagger_reading(tagger, text, word) if tagger else None
            rule = item["reading"]  # None for tagger-only words
            agree = None
            if hira is not None and rule is not None:
                agree = hira.startswith(rule)
            entries.append({
                "line": i,
                "word": word,
                "index": item["index"],
                "context": text,
                "rule": rule,
                "rule_why": item["why"],
                "tagger": hira,
                "agree": agree,
                "decided_by_rule": decided,
                "accepted": None,
            })
    return {"project": str(project_path), "tagger": "fugashi" if tagger else "rules only",
            "entries": entries}


def apply(review_path: Path, project_path: Path) -> dict:
    review = json.loads(review_path.read_text(encoding="utf-8"))
    project = json.loads(project_path.read_text(encoding="utf-8"))
    subtitles = project.get("subtitles", [])
    by_line: dict[int, list[dict]] = {}
    for entry in review["entries"]:
        if entry.get("accepted") is True:
            by_line.setdefault(entry["line"], []).append(entry)
    changed = 0
    for line, items in by_line.items():
        cue = subtitles[line]
        text = cue.get("text", "")
        # the word's own index in the current text; annotate from the end so earlier indexes stay valid
        for entry in sorted(items, key=lambda e: -e["index"]):
            reading = entry.get("reading") or entry.get("rule")
            word = entry["word"]
            idx = entry["index"]
            if text[idx:idx + len(word)] != word or not reading:
                continue  # the text changed since the suggestion: skip, do not guess
            span = word[:1] if len(word) == 1 else word
            text = text[:idx] + f"{span}{{{reading}}}" + text[idx + len(span):]
            changed += 1
        cue["text"] = text
    if changed:
        project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"written": changed, "lines": len(by_line)}


def main(argv: list[str] | None = None) -> int:
    _ensure_tagger_interpreter()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("suggest")
    s.add_argument("project")
    s.add_argument("-o", "--out")
    a = sub.add_parser("apply")
    a.add_argument("review")
    a.add_argument("project")
    args = parser.parse_args(argv)
    if args.command == "suggest":
        report = suggest(Path(args.project))
        out = Path(args.out) if args.out else Path(args.project).with_suffix("").with_suffix(".homograph-review.json")
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{len(report['entries'])} suggestions ({report['tagger']}) -> {out}")
    else:
        print(json.dumps(apply(Path(args.review), Path(args.project)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
