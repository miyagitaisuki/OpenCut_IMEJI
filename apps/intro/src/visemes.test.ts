import { expect, test } from "bun:test";

import { type AudioQuery, mouthAt, queryDuration, visemes } from "./visemes";

// 「ようこそ。まあ」 as VOICEVOX describes it (lengths in seconds).
const query: AudioQuery = {
  speedScale: 1,
  prePhonemeLength: 0.1,
  postPhonemeLength: 0.1,
  accent_phrases: [
    {
      moras: [
        { text: "ヨ", consonant: "y", consonant_length: 0.05, vowel: "o", vowel_length: 0.1 },
        { text: "ウ", consonant: null, consonant_length: null, vowel: "o", vowel_length: 0.1 },
        { text: "コ", consonant: "k", consonant_length: 0.06, vowel: "o", vowel_length: 0.1 },
        { text: "ソ", consonant: "s", consonant_length: 0.08, vowel: "o", vowel_length: 0.12 },
      ],
      pause_mora: { text: "、", vowel: "pau", vowel_length: 0.3 },
    },
    {
      moras: [
        { text: "マ", consonant: "m", consonant_length: 0.06, vowel: "a", vowel_length: 0.12 },
        { text: "ア", consonant: null, consonant_length: null, vowel: "a", vowel_length: 0.1 },
        { text: "ン", consonant: null, consonant_length: null, vowel: "N", vowel_length: 0.08 },
      ],
    },
  ],
};

test("one shape per vowel run, closed for pauses, ん and bilabials", () => {
  const list = visemes(query);
  expect(list.map((v) => v.mouth)).toEqual(["o", "n", "a", "n"]);
  // ようこそ: from the end of よ's consonant through そ.
  expect(list[0].start).toBeCloseTo(0.15);
  expect(list[0].end).toBeCloseTo(0.71);
  // The pause and ま's closed lips merge into one closed mouth.
  expect(list[1].end).toBeCloseTo(1.07);
});

test("mouthAt and duration", () => {
  const list = visemes(query);
  expect(mouthAt(list, 0.05)).toBe("n");
  expect(mouthAt(list, 0.5)).toBe("o");
  expect(mouthAt(list, 1.2)).toBe("a");
  expect(mouthAt(list, 5)).toBe("n");
  expect(queryDuration(query)).toBeCloseTo(1.47);
  expect(queryDuration({ ...query, speedScale: 2 })).toBeCloseTo(0.735);
});
