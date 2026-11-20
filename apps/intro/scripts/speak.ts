// Voices a scene with AivisSpeech (or VOICEVOX, same API) and works out the
// avatar's mouth from the engine's own mora timing.
//
//   bun run speak scenes/n4-teshimau.json
//   bun run speak scenes/n4-teshimau.json --engine http://127.0.0.1:50021   # VOICEVOX
//
// Writes public/voices/<name>.wav and scenes/<name>.props.json, which
// `bun run render` turns into out/<name>.mp4.

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, join, resolve } from "node:path";

import type { AvatarManifest, IntroProps, Scene } from "../src/types";
import { type AudioQuery, lacksTiming, queryDuration, retime, visemes } from "../src/visemes";

const root = resolve(import.meta.dir, "..");
// AivisSpeech listens on 10101; VOICEVOX on 50021.
const DEFAULT_ENGINE = "http://127.0.0.1:10101";

function option(name: string): string | undefined {
  const i = process.argv.indexOf(name);
  return i === -1 ? undefined : process.argv[i + 1];
}

export async function speak(scenePath: string, engine: string): Promise<{ props: string; voice: string }> {
  const scene: Scene = JSON.parse(readFileSync(scenePath, "utf8"));
  if (!scene.text?.trim()) throw new Error(`${scenePath}: "text" is empty`);
  const name = basename(scenePath).replace(/\.json$/, "");
  const avatar = loadAvatar(scene.avatar);
  const speaker = scene.speaker ?? (await firstSpeaker(engine));

  const query: AudioQuery & Record<string, unknown> = await call(
    engine,
    `/audio_query?${new URLSearchParams({ text: scene.text, speaker: String(speaker) })}`,
  ).then((r) => r.json());
  if (scene.speed) query.speedScale = scene.speed;

  const wav = await call(engine, `/synthesis?speaker=${speaker}`, JSON.stringify(query)).then((r) => r.arrayBuffer());
  const voiceRel = `voices/${name}.wav`;
  mkdirSync(join(root, "public", "voices"), { recursive: true });
  writeFileSync(join(root, "public", voiceRel), new Uint8Array(wav));

  // AivisSpeech reports no mora lengths: find where the voice really speaks
  // and spread the moras over that stretch.
  const span = lacksTiming(query) ? speechSpan(new Uint8Array(wav)) : undefined;
  const timing = span ? retime(query, span.start, span.end - span.start) : query;

  const props: IntroProps = {
    scene,
    avatar,
    voice: voiceRel,
    voiceSeconds: wavSeconds(new Uint8Array(wav)) ?? queryDuration(query),
    visemes: visemes(timing),
  };
  const propsPath = join(root, "scenes", `${name}.props.json`);
  writeFileSync(propsPath, `${JSON.stringify(props, null, 2)}\n`);
  return { props: propsPath, voice: join(root, "public", voiceRel) };
}

export function loadAvatar(folder: string): AvatarManifest {
  const path = join(root, "public", "avatars", folder, "avatar.json");
  const manifest = JSON.parse(readFileSync(path, "utf8")) as Omit<AvatarManifest, "folder">;
  return { ...manifest, folder };
}

async function call(engine: string, path: string, body?: string): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(engine + path, {
      method: "POST",
      headers: body ? { "content-type": "application/json" } : undefined,
      body,
    });
  } catch {
    throw new Error(`cannot reach the speech engine at ${engine}: start AivisSpeech (or pass --engine)`);
  }
  if (!response.ok) throw new Error(`${engine}${path.split("?")[0]}: ${response.status} ${await response.text()}`);
  return response;
}

/** The first style of the first voice, when the scene names none. */
async function firstSpeaker(engine: string): Promise<number> {
  const speakers = (await fetch(`${engine}/speakers`)
    .then((r) => r.json())
    .catch(() => [])) as { styles: { id: number }[] }[];
  const id = speakers[0]?.styles[0]?.id;
  if (id === undefined) throw new Error(`no voices at ${engine}/speakers: set "speaker" in the scene`);
  return id;
}

/** Length of a PCM WAV, from its header. */
function wavSeconds(bytes: Uint8Array): number | undefined {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.length < 44 || view.getUint32(0, false) !== 0x52494646) return undefined; // "RIFF"
  let offset = 12;
  let byteRate = 0;
  while (offset + 8 <= bytes.length) {
    const id = view.getUint32(offset, false);
    const size = view.getUint32(offset + 4, true);
    if (id === 0x666d7420) byteRate = view.getUint32(offset + 16, true); // "fmt "
    if (id === 0x64617461 && byteRate) return size / byteRate; // "data"
    offset += 8 + size + (size % 2);
  }
  return undefined;
}

/** First and last second the 16-bit PCM wav is louder than silence (ends trimmed of breath and room noise). */
export function speechSpan(bytes: Uint8Array): { start: number; end: number } | undefined {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.length < 44 || view.getUint32(0, false) !== 0x52494646) return undefined;
  let offset = 12;
  let rate = 0;
  let channels = 1;
  let bits = 16;
  while (offset + 8 <= bytes.length) {
    const id = view.getUint32(offset, false);
    const size = view.getUint32(offset + 4, true);
    if (id === 0x666d7420) {
      channels = view.getUint16(offset + 10, true);
      rate = view.getUint32(offset + 12, true);
      bits = view.getUint16(offset + 22, true);
    }
    if (id === 0x64617461 && rate && bits === 16) {
      const frames = Math.floor(Math.min(size, bytes.length - offset - 8) / (2 * channels));
      const window = Math.max(1, Math.round(rate * 0.01));
      const loud: boolean[] = [];
      let peak = 0;
      const rms: number[] = [];
      for (let w = 0; w + window <= frames; w += window) {
        let sum = 0;
        for (let i = 0; i < window; i++) {
          const v = view.getInt16(offset + 8 + (w + i) * 2 * channels, true);
          sum += v * v;
        }
        const level = Math.sqrt(sum / window);
        rms.push(level);
        peak = Math.max(peak, level);
      }
      for (const level of rms) loud.push(level > peak * 0.05);
      const first = loud.indexOf(true);
      const last = loud.lastIndexOf(true);
      if (first < 0) return undefined;
      return { start: (first * window) / rate, end: ((last + 1) * window) / rate };
    }
    offset += 8 + size + (size % 2);
  }
  return undefined;
}

if (import.meta.main) {
  const scene = process.argv[2];
  if (!scene) {
    console.error("usage: bun run speak scenes/<name>.json [--engine http://127.0.0.1:10101]");
    process.exit(2);
  }
  speak(scene, (option("--engine") ?? DEFAULT_ENGINE).replace(/\/$/, ""))
    .then(({ props, voice }) => console.log(`voice: ${voice}\nprops: ${props}`))
    .catch((error) => {
      console.error(error instanceof Error ? error.message : error);
      process.exit(1);
    });
}
