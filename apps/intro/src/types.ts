import type { Mouth, Viseme } from "./visemes";

/** What a teacher writes: `scenes/<name>.json`. */
export type Scene = {
  scene_type: "intro" | "outro";
  /** Folder under public/avatars/. */
  avatar: string;
  /** What the avatar says, in Japanese (AivisSpeech reads it). */
  text: string;
  /** Big line on the card, e.g. `～てしまう`. */
  title?: string;
  /** Small line above it, e.g. `N4 文法`. */
  subtitle?: string;
  /** Under the Japanese caption, e.g. the Vietnamese. */
  translation?: string;
  /** AivisSpeech / VOICEVOX style id. */
  speaker?: number;
  /** Speech speed (1 = normal). */
  speed?: number;
  /** `#rrggbb` pair for the background gradient. */
  colors?: [string, string];
  /** Gestures over time, for rigged avatars: from `at` seconds of speech on. */
  gestures?: { at: number; gesture: string }[];
  /** Sticker effects (avatar `fx` names) popping beside her head, `at` seconds of speech. */
  effects?: { at: number; type: string; duration?: number }[];
};

export type AvatarManifest = {
  /** Folder under public/avatars/ (set when the manifest is loaded). */
  folder: string;
  name: string;
  size: [number, number];
  /**
   * A rigged avatar moves in parts, like a VTuber: back hair swaying a
   * beat behind, the head tilting about the neck, arms by gesture.
   * Without it, `layers.body` is one still picture.
   */
  rig?: {
    hair_back?: string;
    torso: string;
    head: string;
    /** Gesture name -> arms picture; the first is the default. */
    arms: Record<string, string>;
    /** Neck joint, as fractions of the canvas, for the head's tilt. */
    neck: [number, number];
    /** The cardigan's shoulder caps, drawn over the arms to hide the seam. */
    shoulders?: string;
  };
  /** Sticker effects by name, e.g. lightbulb, sweat, sparkle, exclamation. */
  fx?: Record<string, string>;
  layers: {
    body?: string;
    eyes_open: string;
    eyes_closed: string;
    /** Smiling closed eyes, shown once she has finished speaking. */
    eyes_happy?: string;
    mouth: Record<Mouth, string>;
  };
};

/** What `bun run speak` writes for Remotion: the scene and its voice. */
export type IntroProps = {
  scene: Scene;
  avatar: AvatarManifest;
  /** Path under public/, or null for a silent preview. */
  voice: string | null;
  voiceSeconds: number;
  visemes: Viseme[];
};
