// Mouth shapes from the timing AivisSpeech (or VOICEVOX) gives for each
// mora of what it reads. Japanese mouths follow the vowel, so five shapes
// あいうえお plus a closed one (ん, っ, pauses) are enough to look right.

export type Mouth = "a" | "i" | "u" | "e" | "o" | "n";

export type Viseme = {
  /** Seconds from the start of the voice audio. */
  start: number;
  end: number;
  mouth: Mouth;
};

/** The parts of an AivisSpeech / VOICEVOX `audio_query` this needs. */
export type Mora = {
  text?: string;
  consonant?: string | null;
  consonant_length?: number | null;
  vowel: string;
  vowel_length: number;
};

export type AudioQuery = {
  accent_phrases: { moras: Mora[]; pause_mora?: Mora | null }[];
  speedScale?: number;
  prePhonemeLength?: number;
  postPhonemeLength?: number;
};

const VOWELS: Record<string, Mouth> = { a: "a", i: "i", u: "u", e: "e", o: "o" };

/** A vowel as the engine names it (`a`, `I` for devoiced i, `N`, `cl`, `pau`). */
export function mouthFor(vowel: string): Mouth {
  return VOWELS[vowel.toLowerCase()] ?? "n";
}

/**
 * The mouth over time for an audio query, in the audio's own seconds.
 * The consonant keeps the previous mouth (lips move to the vowel during
 * it), so each shape spans from its consonant's end to the next one's.
 */
export function visemes(query: AudioQuery): Viseme[] {
  const scale = 1 / (query.speedScale && query.speedScale > 0 ? query.speedScale : 1);
  let time = (query.prePhonemeLength ?? 0.1) * scale;
  const out: Viseme[] = [];
  const push = (mouth: Mouth, start: number, end: number) => {
    if (end <= start) return;
    const last = out[out.length - 1];
    if (last && last.mouth === mouth && Math.abs(last.end - start) < 1e-6) {
      last.end = end;
    } else {
      out.push({ start, end, mouth });
    }
  };
  const mora = (m: Mora) => {
    const consonant = (m.consonant_length ?? 0) * scale;
    const vowel = m.vowel_length * scale;
    // Lips close for the consonant of ま・ぱ・ば行 (bilabials), else hold.
    if (consonant > 0 && m.consonant && /^[mpb]/.test(m.consonant)) {
      push("n", time, time + consonant);
    } else if (consonant > 0 && out.length) {
      out[out.length - 1].end = time + consonant;
    }
    time += consonant;
    push(mouthFor(m.vowel), time, time + vowel);
    time += vowel;
  };
  for (const phrase of query.accent_phrases) {
    phrase.moras.forEach(mora);
    if (phrase.pause_mora) mora({ ...phrase.pause_mora, vowel: "pau" });
  }
  return out;
}

/** The mouth at `seconds`, closed outside any viseme. */
export function mouthAt(list: Viseme[], seconds: number): Mouth {
  // Lists are short (a few hundred entries): a scan is fine per frame.
  for (const v of list) {
    if (seconds < v.start) break;
    if (seconds < v.end) return v.mouth;
  }
  return "n";
}

/** How long the audio for a query lasts, pauses included. */
export function queryDuration(query: AudioQuery): number {
  const scale = 1 / (query.speedScale && query.speedScale > 0 ? query.speedScale : 1);
  let total = (query.prePhonemeLength ?? 0.1) + (query.postPhonemeLength ?? 0.1);
  for (const phrase of query.accent_phrases) {
    for (const m of [...phrase.moras, ...(phrase.pause_mora ? [phrase.pause_mora] : [])]) {
      total += (m.consonant_length ?? 0) + m.vowel_length;
    }
  }
  return total * scale;
}
