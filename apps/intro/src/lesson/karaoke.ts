/** Word-level timing for a subtitle, worked out from its text alone. */

import type { Cue, KaraokeCue, Unit } from "./types";

const RUBY = /([一-鿿々〆ヶ]+)\{([^}]*)\}/g;
const PAUSE = /[。！？!?]/;
const SHORT_PAUSE = /[、，,]/;

type Piece = { base: string; reading?: string; weight: number };

/** A mora is a kana, less the small ya/yu/yo that join the one before. */
function morae(kana: string): number {
  return [...kana].filter((c) => !"ゃゅょャュョぁぃぅぇぉァィゥェォ".includes(c)).length || 1;
}

/**
 * Splits `食{た}べる。` into units and gives each a weight, its share of the
 * time: a kanji word by the length of its reading, a kana by one, a mark by a
 * pause. Spaces and other marks take no time.
 */
export function pieces(text: string): Piece[] {
  const out: Piece[] = [];
  let last = 0;
  const plain = (s: string) => {
    for (const c of s) {
      if (/\s/.test(c)) continue;
      if (PAUSE.test(c)) out.push({ base: c, weight: 2 });
      else if (SHORT_PAUSE.test(c)) out.push({ base: c, weight: 1 });
      else if ("ゃゅょャュョぁぃぅぇぉァィゥェォっッー".includes(c) && out.length) {
        // Joins the sound before it; a long mark and a small tsu take a beat.
        const prev = out[out.length - 1];
        prev.base += c;
        if ("っッー".includes(c)) prev.weight += 1;
      } else out.push({ base: c, weight: /[一-鿿々]/.test(c) ? 2 : 1 });
    }
  };
  for (const m of text.matchAll(RUBY)) {
    const at = m.index ?? 0;
    plain(text.slice(last, at));
    out.push({ base: m[1], reading: m[2], weight: morae(m[2]) });
    last = at + m[0].length;
  }
  plain(text.slice(last));
  return out;
}

/**
 * Spreads the cue's time over its units by weight. `offset` is where the body
 * starts on the project's clock. The last mark is not waited for: speech ends
 * with the last sound, so the weight of closing marks is only a small tail.
 */
export function karaoke(cue: Cue, offset: number): KaraokeCue {
  const list = pieces(cue.text);
  const total = list.reduce((a, p) => a + p.weight, 0) || 1;
  const start = cue.start - offset;
  const span = cue.end - cue.start;
  let at = 0;
  const units: Unit[] = list.map((p) => {
    const u = { base: p.base, reading: p.reading, start: start + (at / total) * span, end: start + ((at + p.weight) / total) * span };
    at += p.weight;
    return u;
  });
  return { start, end: cue.end - offset, units, translation: cue.translation };
}

/** A spoken piece heard by Whisper: its text and when it was said (seconds on the body's clock). */
export type Heard = { text: string; start: number; end: number };

const spoken = (s: string) => [...s].filter((c) => !/[\s、。，．！？!?,.「」]/.test(c)).length;

/**
 * Like `karaoke`, but with the pace of the real voice: the tokens Whisper heard
 * inside the cue pin parts of the text to times, and the units between them are
 * spread evenly. Whisper may hear other words than the script (kanji, mistakes),
 * so only how far through the sentence it was counts, never what it heard.
 * Too few tokens: the plain even spread.
 */
export function align(cue: Cue, offset: number, heard: Heard[]): KaraokeCue {
  const base = karaoke(cue, offset);
  const start = cue.start - offset;
  const end = cue.end - offset;
  const tokens = heard.filter((h) => h.end > start - 0.05 && h.start < end + 0.05 && spoken(h.text) > 0);
  const total = tokens.reduce((a, h) => a + spoken(h.text), 0);
  if (tokens.length < 3 || !total) return base;

  // (how far through the text, when): from the first sound to the last.
  const anchors: [number, number][] = [[0, Math.max(start, tokens[0].start)]];
  let seen = 0;
  for (const h of tokens) {
    seen += spoken(h.text);
    anchors.push([seen / total, Math.min(end, Math.max(h.start, h.end))]);
  }
  // Time never runs backwards, and one fraction has one time.
  for (let i = 1; i < anchors.length; i++) anchors[i][1] = Math.max(anchors[i][1], anchors[i - 1][1]);
  const at = (f: number): number => {
    for (let i = 1; i < anchors.length; i++) {
      const [f1, t1] = anchors[i];
      const [f0, t0] = anchors[i - 1];
      if (f <= f1) return f1 === f0 ? t1 : t0 + ((f - f0) / (f1 - f0)) * (t1 - t0);
    }
    return anchors[anchors.length - 1][1];
  };

  const list = pieces(cue.text);
  const sum = list.reduce((a, p) => a + p.weight, 0) || 1;
  let w = 0;
  const units: Unit[] = list.map((p) => {
    const u = { base: p.base, reading: p.reading, start: at(w / sum), end: at((w + p.weight) / sum) };
    w += p.weight;
    return u;
  });
  return { ...base, units };
}
