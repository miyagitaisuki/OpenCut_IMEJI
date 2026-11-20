import { describe, expect, test } from "bun:test";
import { SHORTS } from "./shorts";

describe("Shorts safe zone", () => {
  test("content starts below the top cover", () => {
    expect(SHORTS.contentTop).toBeGreaterThanOrEqual(SHORTS.coveredTop);
    expect(SHORTS.practiceTop).toBeGreaterThanOrEqual(SHORTS.coveredTop);
  });

  test("the footer sits above the bottom cover", () => {
    expect(SHORTS.height - SHORTS.footerBottom).toBeLessThanOrEqual(SHORTS.height - SHORTS.coveredBottom);
  });

  test("the frame is 9:16", () => {
    expect(SHORTS.width * 16).toBe(SHORTS.height * 9);
  });
});
