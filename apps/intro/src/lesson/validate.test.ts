import { expect, test } from "bun:test";

import { buildPrompt } from "./prompt";
import { validate } from "./validate";

const ok = () => true;

test("a good file has no errors", () => {
  const r = validate(
    { scenes: [{ template: "title", cue: 0, title: "T" }, { template: "chart", cue: 1, kind: "bar", items: [{ label: "a", value: 1 }, { label: "b", value: 2 }], highlight: 1, accent: "star" }] },
    3,
    ok,
  );
  expect(r.errors).toEqual([]);
});

test("reports what is wrong, scene by scene", () => {
  const r = validate(
    {
      scenes: [
        { template: "nope", cue: 0 },
        { template: "title", cue: 9, title: "" },
        { template: "chart", cue: 1, kind: "line", items: [{ label: "a", value: "3" }] },
        { template: "grammar", cue: 2, parts: [{ text: "a" }] },
        { template: "image", cue: 2, images: [{ src: "missing.png" }] },
      ],
    },
    3,
    () => false,
  );
  const all = r.errors.join("\n");
  expect(all).toMatch(/scenes\[0\].*template must be/);
  expect(all).toMatch(/scenes\[1\].*cue must be an integer 0\.\.2/);
  expect(all).toMatch(/scenes\[1\].*title is required/);
  expect(all).toMatch(/kind must be/);
  expect(all).toMatch(/items needs at least 2/);
  expect(all).toMatch(/parts needs at least 2/);
  expect(all).toMatch(/picture not found: missing.png/);
});

test("not a scenes file", () => {
  expect(validate([], 3).errors[0]).toMatch(/scenes/);
});

test("the prompt numbers every cue and carries the translation", () => {
  const p = buildPrompt([{ start: 1, end: 2.5, text: "会社{かいしゃ}で", translation: "Ở công ty" }, { start: 3, end: 4, text: "はい" }], "Bài 1");
  expect(p).toContain("0 [1.0-2.5s] 会社{かいしゃ}で  | Ở công ty");
  expect(p).toContain("1 [3.0-4.0s] はい");
  expect(p).toContain("Lesson: Bài 1");
});
