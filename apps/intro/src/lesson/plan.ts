/** Puts scenes on the clock: which picture is on screen for which stretch of the lesson. */

import type { AuthoredScene, Cue, KeywordScene, Segment } from "./types";

/** Longest sentence shown whole (the scene shrinks it to fit). */
const WHOLE = 24;
const KANJI_OR_KATAKANA = /[一-鿿々]{2,}|[ァ-ヺー]{3,}/g;

/** `食{た}べる` -> `食べる`. */
export function stripRuby(text: string): string {
  return text.replace(/\{[^}]*\}/g, "").replace(/[（(][぀-ゟ]+[）)]/g, "");
}

/** The cue's most telling word: the longest run of kanji or katakana, else its first sentence. */
export function keywordOf(text: string): string {
  const plain = stripRuby(text).replace(/\s+/g, "");
  const runs = plain.match(KANJI_OR_KATAKANA) ?? [];
  const best = runs.reduce((a, b) => (b.length > a.length ? b : a), "");
  if (best) return best;
  // No kanji or katakana word: the first sentence whole, so it never ends mid-word
  // ("女の人はこれからまずなに"); a very long one is cut at its first comma.
  const sentence = plain.split(/[。！？!?]/)[0];
  if (sentence.length <= WHOLE) return sentence || plain.slice(0, WHOLE);
  const clause = sentence.split(/[、，,]/)[0];
  return clause.length <= WHOLE ? clause : clause.slice(0, WHOLE);
}

function defaultScene(cue: Cue): KeywordScene {
  return { template: "keyword", keyword: keywordOf(cue.text), caption: cue.translation };
}

/**
 * One segment per run of cues that share a scene. A scene covers its `cue` up
 * to the cue before the next scene (or `until_cue`). Cues no scene covers get
 * a keyword scene, so the screen is never empty. Segments tile the whole body:
 * the first starts at 0, each ends where the next begins, the last at `duration`.
 * Apart from the very first, a segment starts at its cue's start.
 */
export function planScenes(cues: Cue[], scenes: AuthoredScene[], bodyStart: number, duration: number): Segment[] {
  if (!cues.length) return [];
  const sorted = [...scenes].sort((a, b) => a.cue - b.cue);
  for (const s of sorted) {
    if (!Number.isInteger(s.cue) || s.cue < 0 || s.cue >= cues.length) {
      throw new Error(`scene "${s.template}" has cue ${s.cue}, but the lesson has ${cues.length} cues (0..${cues.length - 1})`);
    }
  }
  const owner: (number | undefined)[] = new Array(cues.length).fill(undefined);
  sorted.forEach((s, i) => {
    const next = sorted[i + 1]?.cue ?? cues.length;
    const last = Math.min(s.until_cue ?? next - 1, next - 1, cues.length - 1);
    for (let c = s.cue; c <= Math.max(last, s.cue); c++) owner[c] = i;
  });

  const segments: Segment[] = [];
  let c = 0;
  while (c < cues.length) {
    const who = owner[c];
    let end = c;
    // Cues without a scene are not merged: each gets its own keyword.
    if (who !== undefined) while (end + 1 < cues.length && owner[end + 1] === who) end++;
    segments.push({
      start: cues[c].start - bodyStart,
      end: 0,
      cues: [c, end],
      beats: cues.slice(c, end + 1).map((q) => q.start),
      scene: who !== undefined ? sorted[who] : defaultScene(cues[c]),
    });
    c = end + 1;
  }
  segments[0].start = 0;
  const round = (n: number) => Math.round(n * 1000) / 1000;
  for (const s of segments) {
    const first = s.beats?.[0] ?? 0;
    s.beats = s.beats?.map((b) => round(Math.max(0, b - first)));
    s.start = round(Math.max(0, s.start));
  }
  segments.forEach((s, i) => {
    s.end = i + 1 < segments.length ? segments[i + 1].start : round(duration);
  });
  return segments;
}
