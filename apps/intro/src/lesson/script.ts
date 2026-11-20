/**
 * A lesson script before it is voiced: what textts reads, one line per sentence,
 * `[1] 日本語{にほんご}の文。 // bản dịch`. Each spoken line becomes one subtitle cue,
 * in order, so scenes can be written (and checked) before the audio exists.
 */

const SPEECH = /^\s*\[?(\d+)\]?[\s　:：]*(\S.*)$/;

export type ScriptLine = { role: number; text: string; translation?: string; line: number };
export type ScriptReport = { lines: ScriptLine[]; errors: string[]; warnings: string[] };

export function parseScript(source: string): ScriptReport {
  const lines: ScriptLine[] = [];
  const errors: string[] = [];
  const warnings: string[] = [];
  source.split(/\r?\n/).forEach((raw, i) => {
    const n = i + 1;
    const trimmed = raw.trim();
    if (!trimmed || trimmed.startsWith("#")) return;
    if (/^\[(pause|sfx|bgm)[=\]]/.test(trimmed)) return;
    const m = SPEECH.exec(raw);
    if (!m) return errors.push(`line ${n}: not a spoken line (start with the role number: "[1] ..."): ${trimmed}`);
    const [body, ...rest] = m[2].split(" // ");
    const text = body.trim();
    const translation = rest.join(" // ").trim() || undefined;
    if (!text) return errors.push(`line ${n}: no Japanese text`);
    if (!translation) warnings.push(`line ${n}: no Vietnamese translation (" // ...")`);
    if (/[一-鿿々]/.test(text.replace(/[一-鿿々]+\{[^}]+\}/g, ""))) warnings.push(`line ${n}: kanji without furigana: ${text}`);
    if (/\{[^}]*$|^[^{]*\}/.test(text)) errors.push(`line ${n}: unbalanced { } in furigana`);
    if ([...text.replace(/\{[^}]*\}/g, "")].length > 60) warnings.push(`line ${n}: long sentence (> 60 characters): split it for the subtitles`);
    lines.push({ role: Number(m[1]), text, translation, line: n });
  });
  if (!lines.length) errors.push("no spoken lines");
  return { lines, errors, warnings };
}
