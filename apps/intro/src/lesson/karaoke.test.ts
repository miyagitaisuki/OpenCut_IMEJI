import { expect, test } from "bun:test";

import { karaoke, pieces } from "./karaoke";

test("splits into units: ruby words whole, kana one by one, small kana joined", () => {
  expect(pieces("食{た}べました。").map((p) => p.base)).toEqual(["食", "べ", "ま", "し", "た", "。"]);
  expect(pieces("きょうは").map((p) => p.base)).toEqual(["きょ", "う", "は"]);
  expect(pieces("会社{かいしゃ}で")[0]).toMatchObject({ base: "会社", reading: "かいしゃ", weight: 3 });
});

test("units tile the cue in order, from the body start", () => {
  const k = karaoke({ start: 10, end: 14, text: "はい、そうです。" }, 4);
  expect(k.start).toBe(6);
  expect(k.units[0].start).toBeCloseTo(6);
  expect(k.units.at(-1)!.end).toBeCloseTo(10);
  for (let i = 1; i < k.units.length; i++) expect(k.units[i].start).toBeCloseTo(k.units[i - 1].end);
});

test("a long word takes longer than a short one", () => {
  const k = karaoke({ start: 0, end: 10, text: "勉強{べんきょう}は" }, 0);
  const [a, b] = k.units;
  expect(a.end - a.start).toBeGreaterThan(b.end - b.start);
});

import { align } from "./karaoke";

test("with heard tokens, the units follow the real pace", () => {
  const cue = { start: 0, end: 4, text: "あいうえ" };
  // Whisper heard the first half fast and the second half slowly.
  const heard = [
    { text: "あ", start: 0.1, end: 0.3 },
    { text: "い", start: 0.3, end: 0.5 },
    { text: "う", start: 1.5, end: 2.5 },
    { text: "え", start: 2.5, end: 3.9 },
  ];
  const k = align(cue, 0, heard);
  expect(k.units[1].end).toBeLessThan(1); // plain spread would say 2.0
  expect(k.units.at(-1)!.end).toBeGreaterThan(3.5);
  for (let i = 1; i < k.units.length; i++) expect(k.units[i].start).toBeGreaterThanOrEqual(k.units[i - 1].start);
});

test("too few tokens: the plain spread", () => {
  const cue = { start: 0, end: 4, text: "あいうえ" };
  expect(align(cue, 0, [{ text: "あ", start: 0, end: 1 }])).toEqual(karaoke(cue, 0));
});
