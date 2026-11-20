import { expect, test } from "bun:test";

import { parseScript } from "./script";

test("one cue per spoken line, with its translation", () => {
  const r = parseScript("# bài 5\n[1] 駅{えき}へ行{い}きます。 // Tôi đi đến ga.\n[pause=800]\n2 はい。 // Vâng.\n");
  expect(r.errors).toEqual([]);
  expect(r.warnings).toEqual([]);
  expect(r.lines.map((l) => [l.role, l.text, l.translation])).toEqual([
    [1, "駅{えき}へ行{い}きます。", "Tôi đi đến ga."],
    [2, "はい。", "Vâng."],
  ]);
});

test("warns about missing translation and bare kanji", () => {
  const r = parseScript("[1] 駅へ行{い}きます。");
  expect(r.warnings.some((w) => w.includes("translation"))).toBe(true);
  expect(r.warnings.some((w) => w.includes("furigana"))).toBe(true);
});

test("rejects lines without a role and broken furigana", () => {
  const r = parseScript("駅へ\n[1] 駅{えき へ");
  expect(r.errors.length).toBe(2);
});
