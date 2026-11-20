import { expect, test } from "bun:test";

import { keywordOf, planScenes, stripRuby } from "./plan";
import type { AuthoredScene, Cue } from "./types";

const cues: Cue[] = [
  { start: 5, end: 8, text: "会社{かいしゃ}で話{はな}しています。", translation: "Ở công ty" },
  { start: 9, end: 12, text: "アンケートを見てください。" },
  { start: 13, end: 15, text: "はい。" },
  { start: 16, end: 20, text: "ありがとうございます。" },
];

const title = (cue: number, until_cue?: number): AuthoredScene => ({ template: "title", title: "T", cue, until_cue });

test("strips furigana and picks a key word", () => {
  expect(stripRuby("会社{かいしゃ}で")).toBe("会社で");
  expect(keywordOf("会社{かいしゃ}で話{はな}しています。")).toBe("会社");
  expect(keywordOf("アンケートを見てください。")).toBe("アンケート");
  expect(keywordOf("はい。")).toBe("はい");
  expect(keywordOf("わかりました。ではまた。")).toBe("わかりました");
  // A sentence with no long kanji word is kept whole, not cut at 12 characters.
  expect(keywordOf("女{おんな}の人{ひと}はこれからまずなにをしますか。")).toBe("女の人はこれからまずなにをしますか");
  expect(keywordOf("そうですね、それではまたあしたおあいしましょうね、さようなら。")).toBe("そうですね");
});

test("a scene lasts until the next scene's cue; segments tile the body", () => {
  const seg = planScenes(cues, [title(0), title(2)], 3, 20);
  expect(seg.map((s) => s.cues)).toEqual([[0, 1], [2, 3]]);
  expect(seg[0].start).toBe(0);
  expect(seg[0].end).toBe(10); // cue 2 starts at 13, minus the body start 3
  expect(seg[1].start).toBe(10);
  expect(seg[1].end).toBe(20);
});

test("scenes start at their cue, within 0.3 s", () => {
  const seg = planScenes(cues, [title(0), title(1), title(3)], 3, 20);
  expect(Math.abs(seg[1].start - (cues[1].start - 3))).toBeLessThan(0.3);
  expect(Math.abs(seg[2].start - (cues[3].start - 3))).toBeLessThan(0.3);
});

test("cues no scene covers get a keyword scene", () => {
  const seg = planScenes(cues, [title(1, 1)], 3, 20);
  expect(seg.map((s) => s.scene.template)).toEqual(["keyword", "title", "keyword", "keyword"]);
  const first = seg[0].scene;
  expect(first.template === "keyword" && first.keyword).toBe("会社");
  expect(first.template === "keyword" && first.caption).toBe("Ở công ty");
});

test("a cue out of range is an error", () => {
  expect(() => planScenes(cues, [title(9)], 3, 20)).toThrow(/cue 9/);
});
