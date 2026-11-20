import { expect, test } from "bun:test";

import { autoGestures, pickPose, sentences } from "./poses";

const all = [
  "wave", "bow_eyes_closed", "cheer_arms_up", "present_left", "finger_up_talk", "peace_sign", "point_right",
  "one_finger_up", "present_open", "think_chin", "present_side", "ask_finger_chin", "scratch_head", "arms_crossed",
  "idea_finger_up", "shrug_open_palms", "read_book",
];

test("splits at sentence stops", () => {
  expect(sentences("こんにちは。 元気ですか？はい！")).toEqual(["こんにちは。", "元気ですか？", "はい！"]);
});

test("picks by what the sentence says", () => {
  expect(pickPose("みなさん、こんにちは。", all)).toBe("wave");
  expect(pickPose("これはなんですか？", all)).toBe("ask_finger_chin");
  expect(pickPose("ありがとうございました。", all)).toBe("bow_eyes_closed");
  expect(pickPose("正解です！", all)).toBe("cheer_arms_up");
  expect(pickPose("違います。", all)).toBe("scratch_head");
});

test("skips poses the avatar lacks, and never repeats back to back", () => {
  expect(pickPose("正解です！", ["present_left", "one_finger_up"])).toBe("present_left");
  const g = autoGestures("今日は勉強します。そして練習します。", ["present_left", "present_open"], 0, 4);
  expect(g[0].gesture).not.toBe(g[1].gesture);
});

test("sentence times follow the characters", () => {
  const g = autoGestures("あああ。いいいいいい。", all, 1, 5);
  expect(g.map((x) => x.at)).toEqual([1, 2.45]);
});
