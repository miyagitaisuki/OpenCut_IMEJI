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
};

export type AvatarManifest = {
  /** Folder under public/avatars/ (set when the manifest is loaded). */
  folder: string;
  name: string;
  size: [number, number];
  layers: {
    body: string;
    eyes_open: string;
    eyes_closed: string;
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
