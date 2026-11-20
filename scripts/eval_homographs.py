#!/usr/bin/env python3
"""Measures how well a morphological tagger (MeCab + UniDic, via fugashi) reads the homographs in
scripts/homograph_eval.json, before any of it is used on lessons. Dev tool: needs `pip install fugashi unidic-lite`
in a Python with a wheel for it (3.10 here; the pipeline itself stays standard library only).

  python scripts/eval_homographs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def to_hira(text: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ン" else c for c in text)


def tagger_reading(tagger, sentence: str, word: str) -> str:
    """Kana of the tokens covering the first occurrence of `word`."""
    start = sentence.index(word)
    end = start + len(word)
    pos = 0
    kana = []
    for token in tagger(sentence):
        s, e = pos, pos + len(token.surface)
        pos = e
        if e > start and s < end:
            kana.append(token.feature.kana or token.surface)
    return to_hira("".join(kana))


def main() -> int:
    try:
        import fugashi
    except ImportError:
        print("fugashi is not installed here: pip install fugashi unidic-lite", file=sys.stderr)
        return 2
    tagger = fugashi.Tagger()
    cases = json.loads((Path(__file__).with_name("homograph_eval.json")).read_text(encoding="utf-8"))
    right = 0
    for case in cases:
        got = tagger_reading(tagger, case["sentence"], case["word"])
        ok = got in case["reading"].split("|")  # alternatives: 明日 あした|あす; 行 いき (the verb stem)|い
        right += ok
        print(f"{'OK  ' if ok else 'MISS'} {case['word']:4} expect {case['reading']:8} got {got:10} {case['sentence']}")
    print(f"{right}/{len(cases)} read as expected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
