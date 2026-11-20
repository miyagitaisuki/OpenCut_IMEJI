/** Checks a visuals file against what the templates need, before a long render finds out. */

import { existsSync } from "node:fs";

const TEMPLATES = ["title", "grammar", "compare", "chart", "dialogue", "image", "practice"];
const TONES = ["pink", "navy", "mint", "sun", "sky"];
const ACCENTS = ["check", "cross", "star"];

export type Report = { errors: string[]; warnings: string[] };

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown) => typeof v === "string" && v.trim().length > 0;
const list = (v: unknown, min = 1) => Array.isArray(v) && v.length >= min;

/**
 * `cueCount`: how many subtitle cues the lesson has. `pictureExists` says whether a
 * picture can be found (default: a file on disk).
 */
export function validate(data: unknown, cueCount: number, pictureExists: (src: string) => boolean = existsSync): Report {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!isObj(data) || !Array.isArray(data.scenes)) return { errors: ['the file must be {"scenes": [...]}'], warnings };
  const seen = new Set<number>();

  data.scenes.forEach((raw, n) => {
    const at = `scenes[${n}]`;
    if (!isObj(raw)) return errors.push(`${at}: not an object`);
    const t = raw.template;
    if (typeof t !== "string" || !TEMPLATES.includes(t)) return errors.push(`${at}: template must be one of ${TEMPLATES.join(", ")} (got ${JSON.stringify(t)})`);
    const here = `${at} (${t})`;
    const cue = raw.cue;
    if (!Number.isInteger(cue) || (cue as number) < 0 || (cue as number) >= cueCount) errors.push(`${here}: cue must be an integer 0..${cueCount - 1} (got ${JSON.stringify(cue)})`);
    else {
      if (seen.has(cue as number)) warnings.push(`${here}: another scene already starts at cue ${cue}`);
      seen.add(cue as number);
    }
    if (raw.until_cue !== undefined && (!Number.isInteger(raw.until_cue) || (raw.until_cue as number) < (cue as number))) errors.push(`${here}: until_cue must be an integer >= cue`);
    if (raw.accent !== undefined && !ACCENTS.includes(raw.accent as string)) errors.push(`${here}: accent must be one of ${ACCENTS.join(", ")}`);
    if (raw.accent_at !== undefined && typeof raw.accent_at !== "number") errors.push(`${here}: accent_at must be a number of seconds`);
    const tone = (v: unknown, where: string) => {
      if (v !== undefined && !TONES.includes(v as string)) errors.push(`${here}: ${where} tone must be one of ${TONES.join(", ")}`);
    };
    tone(raw.tone, "scene");

    switch (t) {
      case "title":
        if (!str(raw.title)) errors.push(`${here}: title is required`);
        else if ((raw.title as string).replace(/\{[^}]*\}/g, "").length > 24) warnings.push(`${here}: title is long: it will shrink to fit`);
        break;
      case "grammar":
        if (!list(raw.parts, 2)) errors.push(`${here}: parts needs at least 2 items`);
        else
          (raw.parts as unknown[]).forEach((p, i) => {
            if (!isObj(p) || !str(p.text)) errors.push(`${here}: parts[${i}].text is required`);
            else tone(p.tone, `parts[${i}]`);
          });
        if (raw.result !== undefined && !(isObj(raw.result) && str(raw.result.text))) errors.push(`${here}: result needs text`);
        if (raw.join !== undefined && raw.join !== "+" && raw.join !== "→") errors.push(`${here}: join must be "+" or "→"`);
        break;
      case "compare":
        for (const side of ["left", "right"] as const) {
          const s = raw[side];
          if (!isObj(s) || !str(s.title) || !list(s.items)) errors.push(`${here}: ${side} needs a title and items`);
          else {
            tone(s.tone, side);
            if ((s.items as unknown[]).length > 5) warnings.push(`${here}: ${side} has more than 5 items`);
            if (!(s.items as unknown[]).every(str)) errors.push(`${here}: ${side}.items must be non-empty strings`);
          }
        }
        break;
      case "chart":
        if (raw.kind !== "bar" && raw.kind !== "donut") errors.push(`${here}: kind must be "bar" or "donut"`);
        if (!list(raw.items, 2)) errors.push(`${here}: items needs at least 2 entries`);
        else {
          (raw.items as unknown[]).forEach((it, i) => {
            if (!isObj(it) || !str(it.label) || typeof it.value !== "number" || !Number.isFinite(it.value) || it.value < 0) errors.push(`${here}: items[${i}] needs a label and a number value >= 0`);
          });
          if ((raw.items as unknown[]).length > 6) warnings.push(`${here}: more than 6 items is crowded`);
          if (raw.highlight !== undefined && !(Number.isInteger(raw.highlight) && (raw.highlight as number) < (raw.items as unknown[]).length)) errors.push(`${here}: highlight must be an index into items`);
        }
        break;
      case "dialogue":
        if (!list(raw.lines)) errors.push(`${here}: lines is required`);
        else {
          (raw.lines as unknown[]).forEach((l, i) => {
            if (!isObj(l) || !str(l.text)) errors.push(`${here}: lines[${i}].text is required`);
          });
          if ((raw.lines as unknown[]).length > 5) warnings.push(`${here}: more than 5 lines is crowded`);
        }
        if (raw.layout !== undefined && raw.layout !== "bubbles" && raw.layout !== "timeline") errors.push(`${here}: layout must be "bubbles" or "timeline"`);
        break;
      case "practice":
        if (!str(raw.question)) errors.push(`${here}: question is required`);
        if (!list(raw.options, 2) || (raw.options as unknown[]).length > 4 || !(raw.options as unknown[]).every(str)) errors.push(`${here}: options needs 2 to 4 non-empty strings`);
        else if (!Number.isInteger(raw.answer) || (raw.answer as number) < 0 || (raw.answer as number) >= (raw.options as unknown[]).length) errors.push(`${here}: answer must be an index into options`);
        if (raw.think !== undefined && (typeof raw.think !== "number" || raw.think < 0 || raw.think > 30)) errors.push(`${here}: think must be 0..30 seconds`);
        break;
      case "image":
        if (!list(raw.images) || (raw.images as unknown[]).length > 3) errors.push(`${here}: images needs 1 to 3 entries`);
        else
          (raw.images as unknown[]).forEach((im, i) => {
            if (!isObj(im) || !str(im.src)) errors.push(`${here}: images[${i}].src is required`);
            else if (!/^https?:\/\//.test(im.src as string) && !pictureExists(im.src as string)) errors.push(`${here}: picture not found: ${im.src}`);
          });
        break;
    }
  });
  if (!data.scenes.length) warnings.push("no scenes: every sentence gets a keyword scene");
  return { errors, warnings };
}
