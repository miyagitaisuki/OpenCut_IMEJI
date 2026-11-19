import { afterAll, expect, test } from "bun:test";
import { readFileSync, rmSync } from "node:fs";

import type { IntroProps } from "../src/types";
import { serveMock } from "./mock-engine";
import { speak } from "./speak";

const server = serveMock();
afterAll(() => server.stop());

test("voices a scene and times the mouth to it", async () => {
  const { props, voice } = await speak(`${import.meta.dir}/../scenes/demo.json`, `http://127.0.0.1:${server.port}`);
  const written: IntroProps = JSON.parse(readFileSync(props, "utf8"));
  expect(written.avatar.folder).toBe("demo");
  expect(written.voice).toBe("voices/demo.wav");
  expect(written.voiceSeconds).toBeGreaterThan(3);
  expect(new Set(written.visemes.map((v) => v.mouth))).toEqual(new Set(["a", "i", "u", "e", "o", "n"]));
  // Shapes never overlap and stay inside the voice.
  for (let i = 1; i < written.visemes.length; i++) {
    expect(written.visemes[i].start).toBeGreaterThanOrEqual(written.visemes[i - 1].end - 1e-9);
  }
  expect(written.visemes.at(-1)!.end).toBeLessThanOrEqual(written.voiceSeconds + 1e-6);
  rmSync(voice);
  rmSync(props);
});
