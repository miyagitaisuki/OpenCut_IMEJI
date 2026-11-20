/**
 * Lesson visuals: what a teacher (or Claude) writes in `<lesson>.visuals.json`.
 * Each scene is tied to a subtitle cue (`cue`), so the picture changes with
 * the sentence being read.
 *
 * Text may carry furigana in textts syntax: `食{た}べる`, `勉強{べんきょう}`.
 */

export type Tone = "pink" | "navy" | "mint" | "sun" | "sky";

type Timing = {
  /** Index of the first subtitle cue (0-based) the scene is shown for. */
  cue: number;
  /** Last cue (inclusive). Default: until the next scene's cue. */
  until_cue?: number;
  /** A small animated sticker in the corner: `check` (right), `cross` (wrong), `star` (well done). */
  accent?: "check" | "cross" | "star";
  /** Seconds into the scene when the accent pops. Default 0.8. */
  accent_at?: number;
};

export type TitleScene = Timing & {
  template: "title";
  title: string;
  subtitle?: string;
  /** Small round badge, e.g. `N4`. */
  badge?: string;
};

export type GrammarScene = Timing & {
  template: "grammar";
  title?: string;
  /** Pieces of the pattern, left to right. */
  parts: { text: string; label?: string; tone?: Tone }[];
  /** Joins the parts: `+` (default) or an arrow. */
  join?: "+" | "→";
  /** What the parts make. */
  result?: { text: string; label?: string };
  note?: string;
};

export type CompareScene = Timing & {
  template: "compare";
  title?: string;
  left: { title: string; items: string[]; tone?: Tone };
  right: { title: string; items: string[]; tone?: Tone };
};

export type ChartScene = Timing & {
  template: "chart";
  title?: string;
  kind: "bar" | "donut";
  items: { label: string; value: number }[];
  unit?: string;
  /** Index of the item to stress (the right answer). */
  highlight?: number;
};

export type DialogueScene = Timing & {
  template: "dialogue";
  title?: string;
  /** `bubbles`: a chat; `timeline`: steps in a row, in order. */
  layout?: "bubbles" | "timeline";
  lines: { who?: string; text: string; side?: "left" | "right" }[];
};

/** Used when no scene covers a cue: the cue's key word, big. */
export type KeywordScene = {
  template: "keyword";
  keyword: string;
  caption?: string;
};

export type ImageScene = Timing & {
  template: "image";
  title?: string;
  /** One to three pictures side by side. `src` is a file next to the visuals file, or an absolute path. */
  images: { src: string; caption?: string }[];
  tone?: Tone;
  note?: string;
};

export type LessonScene =
  | TitleScene
  | ImageScene
  | GrammarScene
  | CompareScene
  | ChartScene
  | DialogueScene
  | KeywordScene;

/** What a teacher writes (`cue` is needed on every scene but the default). */
export type AuthoredScene = Exclude<LessonScene, KeywordScene>;

export type VisualsFile = {
  /** Scenes in cue order. */
  scenes: AuthoredScene[];
};

/** One scene placed on the body's clock (seconds from the body start). */
export type Segment = {
  start: number;
  end: number;
  /** First and last cue the segment covers. */
  cues: [number, number];
  scene: LessonScene;
};

export type LessonProps = {
  segments: Segment[];
  /** Length of the body video in seconds. */
  duration: number;
  /** Subtitles drawn word by word (karaoke) in the picture. Absent: none. */
  captions?: KaraokeCue[];
};

export type Cue = { start: number; end: number; text: string; translation?: string };

/** A piece of a subtitle that lights up as one: a kanji word with its reading, or a character. */
export type Unit = { base: string; reading?: string; start: number; end: number };

/** A subtitle with the time each unit is spoken, in seconds from the start of the body. */
export type KaraokeCue = { start: number; end: number; units: Unit[]; translation?: string };
