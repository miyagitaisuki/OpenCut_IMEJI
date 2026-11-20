/** Picks a chibi pose for each sentence from what the sentence says. */

type Rule = { test: RegExp; poses: string[] };

// First match wins. Pose names are the keys of a pose sheet's `poses`
// (see scripts/chibi_names.json); a name the avatar lacks is skipped.
const RULES: Rule[] = [
  { test: /こんにちは|こんばんは|おはよう|はじめまして|ようこそ|みなさん/, poses: ["wave"] },
  { test: /さようなら|またね|じゃあ|次回|また.*(会|お会い)/, poses: ["wave", "hand_chest"] },
  { test: /ありがとう|ご視聴|ご清聴/, poses: ["thanks_hands_together", "bow_eyes_closed"] },
  { test: /すみません|ごめん|申し訳/, poses: ["sorry_sweat", "bow_eyes_closed"] },
  { test: /えっ|びっくり|驚|本当に|ほんとうに/, poses: ["surprised"] },
  { test: /なるほど|わかりました|分かりました|そうか/, poses: ["happy_fist_chest", "idea_finger_up"] },
  { test: /残念|悲しい|かなしい|寂しい|さびしい|つらい/, poses: ["sad_rub_eye"] },
  { test: /すばらしい|素晴らしい|正解|よくできました|上手|いいですね|おめでとう|やった/, poses: ["clap_happy", "thumbs_up", "cheer_arms_up", "peace_sign"] },
  { test: /大丈夫|だいじょうぶ|オッケー|OK/, poses: ["ok_signs", "thumbs_up"] },
  { test: /頑張|がんば/, poses: ["cheer_fists", "cheer_arms_up"] },
  { test: /うれしい|嬉しい|よかった|安心/, poses: ["content_hand_chest", "hand_chest"] },
  { test: /違います|ちがいます|間違|ダメ|だめ|いけません|不正解/, poses: ["wrong_cross_arms", "scratch_head", "arms_crossed"] },
  { test: /難しい|むずかしい|わかりません|できません|分かりません/, poses: ["worried_hands_up", "shrug_open_palms", "scratch_head"] },
  { test: /注意|気をつけ|気を付け/, poses: ["finger_up_talk", "idea_finger_up"] },
  { test: /質問|答えて|答え(は|を)|どちら|どれ/, poses: ["hold_mic", "ask_finger_chin"] },
  { test: /聞いて|聞き|聴いて|聴き|音声|リスニング/, poses: ["hand_ear_smile"] },
  { test: /もしもし|電話|メール|スマホ/, poses: ["hold_phone"] },
  { test: /本|ページ|テキスト|教科書|読んで|読み/, poses: ["read_book"] },
  { test: /考え|思います|思う|かもしれ/, poses: ["think_chin", "ask_finger_chin"] },
  { test: /大切|大事|重要|ポイント|覚え|ひらめ|コツ/, poses: ["idea_finger_up", "one_finger_up"] },
  { test: /例えば|たとえば|例文|例$/, poses: ["present_side", "present_left"] },
  { test: /ましょう|ください|お願い/, poses: ["present_open", "peace_sign"] },
  { test: /今日は|今日の|文法|勉強/, poses: ["one_finger_up", "finger_up_talk"] },
];

const QUESTION = /[？?]|ですか[。！]?$|ますか[。！]?$|でしょうか[。！]?$/;
const NEUTRAL = ["present_left", "present_open", "finger_up_talk", "point_right", "present_side", "point_left", "one_finger_up"];

/** Splits Japanese text into sentences at 。！？ and keeps the stop with the sentence. */
export function sentences(text: string): string[] {
  return (text.replace(/\s+/g, "").match(/[^。！？!?]+[。！？!?]*/g) ?? []).filter((s) => s.trim());
}

/** One pose for one sentence, not repeating `previous`; `available` limits the choice. */
export function pickPose(sentence: string, available: string[], previous?: string, index = 0): string {
  const has = (p: string) => available.includes(p);
  const choose = (list: string[]) => {
    const ok = list.filter(has);
    return ok.find((p) => p !== previous) ?? ok[0];
  };
  if (QUESTION.test(sentence)) {
    const q = choose(["ask_finger_chin", "think_chin", "hold_mic"]);
    if (q) return q;
  }
  for (const rule of RULES) if (rule.test.test(sentence)) {
    const p = choose(rule.poses);
    // A rule with one pose that would repeat: let the next rule or the rotation decide.
    if (p && p !== previous) return p;
  }
  const neutral = NEUTRAL.filter(has);
  const pool = neutral.length ? neutral : available;
  // Rotate through the neutral poses so a long talk does not freeze.
  for (let i = 0; i < pool.length; i++) {
    const p = pool[(index + i) % pool.length];
    if (p !== previous) return p;
  }
  return pool[0];
}

/**
 * Poses over time for a spoken text. Sentence timing is its share of the
 * characters over the stretch where the voice speaks (`from`..`to` seconds
 * of speech), which is close enough for a gesture change.
 */
export function autoGestures(
  text: string,
  available: string[],
  from: number,
  to: number,
): { at: number; gesture: string }[] {
  const parts = sentences(text);
  if (!parts.length || !available.length) return [];
  const total = parts.reduce((n, s) => n + s.length, 0);
  const out: { at: number; gesture: string }[] = [];
  let used = 0;
  let previous: string | undefined;
  parts.forEach((s, i) => {
    const gesture = pickPose(s, available, previous, i);
    out.push({ at: Math.round((from + ((to - from) * used) / total) * 100) / 100, gesture });
    previous = gesture;
    used += s.length;
  });
  return out;
}
