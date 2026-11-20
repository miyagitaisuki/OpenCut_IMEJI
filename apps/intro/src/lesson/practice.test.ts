import { expect, test } from "bun:test";

import { practiceTiming } from "./practice";

test("counts down for `think` seconds after the choices are up", () => {
  const t = practiceTiming(20, 5, 3);
  expect(t.countFrom).toBeCloseTo(2.15);
  expect(t.reveal).toBeCloseTo(7.15);
});

test("a short scene still shows the answer before it ends", () => {
  const t = practiceTiming(6, 5, 3);
  expect(t.reveal).toBeCloseTo(4.5);
});

test("never reveals before the choices are up", () => {
  const t = practiceTiming(1, 5, 4);
  expect(t.reveal).toBe(t.countFrom);
});
