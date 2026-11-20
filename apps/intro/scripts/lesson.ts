// Runs on Node (not Bun): Remotion's headless browser hangs under Bun.
// Lesson visuals: pictures for the body of a lesson, timed by its subtitle cues.
//
//   bun run lesson preview <x.visuals.json> <x.project.json>   stills of every scene, to look at
//   bun run lesson render  <x.visuals.json> <x.project.json>   the background video (1920x1080, silent)
//   bun run lesson apply   <x.project.json> <bg.mp4>           makes it the project's picture
//   bun run lesson build   <x.visuals.json> <x.project.json>   render + apply
//
// The project is what `opencut import-textts` wrote: its subtitles are the
// cues the scenes point at, and its audio tells where the body starts.
//   bun run lesson prompt  <x.project.json>                    the instructions + cues, for a model to write scenes
//   bun run lesson check   <x.visuals.json> <x.project.json>   is the scenes file valid?
//   (prompt and check also take the script, `x.script.vi.txt`, in place of the project:
//    one cue per spoken line, so scenes can be written before the voice exists)
//   bun run lesson thumbnail <thumb.json> [-o x.png]          1280x720 thumbnail: title, badge, chibi pose
//   bun run lesson short   <x.visuals.json> <x.project.json> --grammar <cue> [-o x.mp4]
//                                                              a vertical Short (< 60 s): that grammar scene + its examples
//   bun run lesson whisper-setup                               fetches Whisper (once, ~150 MB)
//   bun run lesson words   <x.project.json>                    when each token of the voice is said
// --captions draws the subtitles into the picture, lit word by word.
// Options: -o <path> (video, or folder for stills). Set REMOTION_BROWSER to
// a Chrome/Chromium binary to use it instead of Remotion's own.

import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { basename, dirname, join, resolve } from "node:path";

import { align, karaoke, type Heard } from "../src/lesson/karaoke.ts";
import { planScenes } from "../src/lesson/plan.ts";
import { buildPrompt } from "../src/lesson/prompt.ts";
import { parseScript } from "../src/lesson/script.ts";
import { validate } from "../src/lesson/validate.ts";
import type { Cue, LessonProps, VisualsFile } from "../src/lesson/types.ts";

const root = resolve(import.meta.dirname, "..");
const FPS = 30;
// ANGLE, as scripts/render.ts: the headless browser here does not start with the default GL.
const chromiumOptions = { gl: "angle" as const };
const timeoutInMilliseconds = 180_000;

type Project = {
  subtitles?: { start: number; end: number; text: string; translation?: string }[];
  audio?: { path: string; start?: number; duration?: number }[];
  visuals: { kind?: string; path?: string; color?: string; start: number; end: number; source_start?: number; fit?: string }[];
  [key: string]: unknown;
};

function option(name: string): string | undefined {
  const i = process.argv.indexOf(name);
  return i === -1 ? undefined : process.argv[i + 1];
}

function readJson<T>(path: string): T {
  // A BOM (PowerShell's Set-Content) would break JSON.parse.
  return JSON.parse(readFileSync(path, "utf8").replace(/^﻿/, "")) as T;
}

/** Where the lesson body sits on the project's clock: the voice, from its start to its end. */
export function bodyRange(project: Project): { start: number; end: number } {
  const cues = project.subtitles ?? [];
  const clips = (project.audio ?? []).filter((a) => a.duration);
  if (clips.length) {
    const start = Math.min(...clips.map((a) => a.start ?? 0));
    const end = Math.max(...clips.map((a) => (a.start ?? 0) + (a.duration ?? 0)));
    return { start, end };
  }
  if (!cues.length) throw new Error("the project has no subtitles and no audio: nothing to time the scenes by");
  return { start: Math.min(...cues.map((c) => c.start)), end: Math.max(...cues.map((c) => c.end)) };
}

const wordsFile = (projectPath: string) => resolve(projectPath).replace(/\.project\.json$|\.json$/, "") + ".words.json";

// Whisper (whisper.cpp) lives outside git: `lesson whisper-setup` fetches it.
const whisperDir = resolve(process.env.WHISPER_DIR || join(root, "..", "..", ".cache", "whisper"));
const whisperModel = "ggml-base.bin";

async function whisperSetup(): Promise<void> {
  const { downloadWhisperModel, installWhisperCpp } = await import("@remotion/install-whisper-cpp");
  mkdirSync(whisperDir, { recursive: true });
  // The installer drops its zip in the working directory.
  process.chdir(whisperDir);
  await installWhisperCpp({ to: whisperDir, version: "1.5.5", printOutput: false });
  await downloadWhisperModel({ model: "base", folder: whisperDir, printOutput: false });
  console.log(`whisper ready in ${whisperDir}`);
}

/**
 * Listens to the lesson's voice and writes when each token was said, next to the
 * project, so `--captions` can light the text at the real pace.
 */
function words(projectPath: string): string {
  const exe = join(whisperDir, process.platform === "win32" ? "main.exe" : "main");
  const model = join(whisperDir, whisperModel);
  if (!existsSync(exe) || !existsSync(model)) throw new Error(`whisper is not set up (${whisperDir}); run: bun run lesson whisper-setup`);
  const project = readJson<Project>(projectPath);
  const { start } = bodyRange(project);
  const out: Heard[] = [];
  for (const clip of (project.audio ?? []).filter((a) => a.duration)) {
    const wav = join(whisperDir, "voice.wav");
    const dec = spawnSync(process.env.OPENCUT_FFMPEG || "ffmpeg", ["-y", "-loglevel", "error", "-i", clip.path, "-ar", "16000", "-ac", "1", wav], { stdio: "inherit" });
    if (dec.status !== 0) throw new Error(`ffmpeg could not read ${clip.path}`);
    const base = join(whisperDir, "voice");
    const run = spawnSync(exe, ["-m", model, "-f", wav, "-l", "ja", "-ojf", "-of", base], { stdio: ["ignore", "ignore", "inherit"] });
    if (run.status !== 0) throw new Error("whisper failed");
    // Latin-1 keeps every byte: a token may hold half of a UTF-8 character.
    const json = JSON.parse(readFileSync(`${base}.json`).toString("latin1"));
    const shift = (clip.start ?? 0) - start;
    let held: number[] = [];
    let from = 0;
    for (const seg of json.transcription) {
      for (const t of seg.tokens) {
        const bytes = [...Buffer.from(t.text, "latin1")];
        if (bytes[0] === 0x5b && t.text.startsWith("[_")) continue; // [_BEG_], [_TT_..]
        if (!held.length) from = t.offsets.from;
        held = held.concat(bytes);
        let text: string;
        try {
          text = new TextDecoder("utf-8", { fatal: true }).decode(Uint8Array.from(held));
        } catch {
          continue; // half a character: wait for the rest
        }
        out.push({ text, start: from / 1000 + shift, end: t.offsets.to / 1000 + shift });
        held = [];
      }
    }
    rmSync(wav, { force: true });
    rmSync(`${base}.json`, { force: true });
  }
  const file = wordsFile(projectPath);
  writeFileSync(file, JSON.stringify(out, null, 1) + "\n", "utf8");
  return file;
}

/**
 * Remotion reads pictures from public/ only. A picture named in a scene (next to the
 * visuals file, or an absolute path) is copied to public/_lesson/ and the scene points there.
 */
export function stageImages(visuals: VisualsFile, visualsPath: string): void {
  const publicDir = join(root, "public");
  for (const scene of visuals.scenes ?? []) {
    if (scene.template === "examples") {
      for (const it of scene.items) {
        if (!it.picture || existsSync(join(publicDir, it.picture))) continue;
        const file = resolve(dirname(resolve(visualsPath)), it.picture);
        if (!existsSync(file)) {
          console.error(`warning: scene at cue ${scene.cue}: picture not found, card shown without it: ${it.picture}`);
          it.picture = undefined;
          continue;
        }
        const name = `${createHash("sha1").update(file).digest("hex").slice(0, 8)}-${basename(file)}`;
        mkdirSync(join(publicDir, "_lesson"), { recursive: true });
        copyFileSync(file, join(publicDir, "_lesson", name));
        it.picture = `_lesson/${name}`;
      }
      continue;
    }
    if (scene.template !== "image") continue;
    for (const im of scene.images) {
      if (/^https?:\/\//.test(im.src) || existsSync(join(publicDir, im.src))) continue;
      const file = resolve(dirname(resolve(visualsPath)), im.src);
      if (!existsSync(file)) throw new Error(`scene at cue ${scene.cue}: picture not found: ${im.src} (looked for ${file})`);
      const name = `${createHash("sha1").update(file).digest("hex").slice(0, 8)}-${basename(file)}`;
      mkdirSync(join(publicDir, "_lesson"), { recursive: true });
      copyFileSync(file, join(publicDir, "_lesson", name));
      im.src = `_lesson/${name}`;
    }
  }
}

export function buildProps(visualsPath: string, projectPath: string): LessonProps {
  const visuals = readJson<VisualsFile>(visualsPath);
  stageImages(visuals, visualsPath);
  const project = readJson<Project>(projectPath);
  const cues: Cue[] = project.subtitles ?? [];
  const { start, end } = bodyRange(project);
  const duration = Math.round((end - start) * 1000) / 1000;
  const props: LessonProps = { duration, segments: planScenes(cues, visuals.scenes ?? [], start, duration) };
  // --captions: the subtitles are drawn here, word by word, instead of by the renderer.
  if (process.argv.includes("--captions")) {
    const wordsPath = wordsFile(projectPath);
    const heard = existsSync(wordsPath) ? readJson<Heard[]>(wordsPath) : null;
    props.captions = cues.map((c) => (heard ? align(c, start, heard) : karaoke(c, start))).filter((k) => k.end > 0 && k.start < duration);
  }
  return props;
}

async function openComposition(props: LessonProps) {
  const serveUrl = await bundle({ entryPoint: join(root, "src", "index.ts") });
  const browserExecutable = process.env.REMOTION_BROWSER || null;
  const composition = await selectComposition({ serveUrl, id: "Lesson", inputProps: props, browserExecutable, chromiumOptions, timeoutInMilliseconds });
  return { serveUrl, composition, browserExecutable };
}


/** A composition by id, for the commands that are not the lesson body. */
async function openById(id: string, props: Record<string, unknown>) {
  const serveUrl = await bundle({ entryPoint: join(root, "src", "index.ts") });
  const browserExecutable = process.env.REMOTION_BROWSER || null;
  const composition = await selectComposition({ serveUrl, id, inputProps: props, browserExecutable, chromiumOptions, timeoutInMilliseconds });
  return { serveUrl, composition, browserExecutable };
}

/** Copies a picture next to a scene into public/_lesson/ and returns where Remotion finds it. */
function stagePicture(src: string, baseDir: string): string | undefined {
  if (/^https?:\/\//.test(src) || existsSync(join(root, "public", src))) return src;
  const file = resolve(baseDir, src);
  if (!existsSync(file)) return undefined;
  const name = `${createHash("sha1").update(file).digest("hex").slice(0, 8)}-${basename(file)}`;
  mkdirSync(join(root, "public", "_lesson"), { recursive: true });
  copyFileSync(file, join(root, "public", "_lesson", name));
  return `_lesson/${name}`;
}

/** A thumbnail PNG from a small JSON: {"title","subtitle","badge","tag","pose"}. */
async function thumbnail(jsonPath: string): Promise<string> {
  const props = readJson<Record<string, unknown>>(jsonPath);
  const out = resolve(option("-o") ?? jsonPath.replace(/\.json$/, "") + ".png");
  const { serveUrl, composition, browserExecutable } = await openById("Thumbnail", props);
  mkdirSync(dirname(out), { recursive: true });
  await renderStill({ composition, serveUrl, output: out, frame: 0, inputProps: props, browserExecutable, chromiumOptions, timeoutInMilliseconds });
  return out;
}

/**
 * A vertical Short about one grammar point: the `grammar` scene at cue `--grammar`, then the
 * `examples` scene that follows it. Picture only (silent); `shortAudio` cuts the voice for it.
 */
export function shortProps(visualsPath: string, projectPath: string, grammarCue: number): { props: Record<string, unknown>; from: number; to: number } {
  const visuals = readJson<VisualsFile>(visualsPath);
  const project = readJson<Project>(projectPath);
  const cues: Cue[] = project.subtitles ?? [];
  const scenes = [...(visuals.scenes ?? [])].sort((a, b) => a.cue - b.cue);
  const gi = scenes.findIndex((s) => s.template === "grammar" && s.cue === grammarCue);
  if (gi < 0) throw new Error(`no grammar scene at cue ${grammarCue}`);
  const g = scenes[gi];
  const ex = scenes[gi + 1];
  if (g.template !== "grammar" || !ex || ex.template !== "examples") throw new Error(`the scene after the grammar one at cue ${grammarCue} must be "examples"`);
  const last = Math.min((ex.until_cue ?? (scenes[gi + 2]?.cue ?? cues.length) - 1), cues.length - 1);
  const from = cues[g.cue].start;
  const to = cues[last].end + 0.8;
  const dir = dirname(resolve(visualsPath));
  const props = {
    duration: Math.round((to - from) * 1000) / 1000,
    title: g.title ?? "",
    badge: option("--badge") ?? "N5",
    parts: g.parts,
    join: g.join,
    note: g.note,
    items: ex.items.map((it, i) => ({
      text: it.text,
      translation: it.translation,
      picture: it.picture ? stagePicture(it.picture, dir) : undefined,
      at: Math.max(0.3, (cues[Math.min(it.cue ?? ex.cue + i, cues.length - 1)].start - from)),
    })),
    footer: option("--footer"),
  };
  return { props, from, to };
}

async function shortVideo(visualsPath: string, projectPath: string): Promise<string> {
  const grammarCue = Number(option("--grammar"));
  if (!Number.isInteger(grammarCue)) throw new Error("--grammar <cue of the grammar scene> is required");
  const { props, from, to } = shortProps(visualsPath, projectPath, grammarCue);
  if ((props.duration as number) >= 60) throw new Error(`the clip is ${(props.duration as number).toFixed(1)} s: a Short must be under 60 s`);
  const out = resolve(option("-o") ?? join(dirname(resolve(projectPath)), `${basename(projectPath).replace(/\.project\.json$|\.json$/, "")}.short-${grammarCue}.mp4`));
  const silent = out.replace(/\.mp4$/, ".silent.mp4");
  const { serveUrl, composition, browserExecutable } = await openById("Short", props);
  mkdirSync(dirname(out), { recursive: true });
  await renderMedia({ composition, serveUrl, codec: "h264", outputLocation: silent, inputProps: props, browserExecutable, chromiumOptions, timeoutInMilliseconds, muted: true, logLevel: "error" });
  const project = readJson<Project>(projectPath);
  const audio = (project.audio ?? []).find((a) => a.duration);
  if (!audio) throw new Error("the project has no voice to cut");
  const shift = from - (audio.start ?? 0);
  const mux = spawnSync(
    process.env.OPENCUT_FFMPEG || "ffmpeg",
    ["-y", "-loglevel", "error", "-i", silent, "-ss", String(Math.max(0, shift)), "-t", String(to - from), "-i", audio.path, "-af", "loudnorm=I=-16:TP=-1.0:LRA=11", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", out],
    { stdio: "inherit" },
  );
  rmSync(silent, { force: true });
  if (mux.status !== 0) throw new Error("ffmpeg could not add the voice");
  return out;
}

async function preview(visualsPath: string, projectPath: string): Promise<string> {
  const props = buildProps(visualsPath, projectPath);
  const dir = resolve(option("-o") ?? join(root, "out", `${basename(visualsPath).replace(/\.visuals\.json$|\.json$/, "")}-preview`));
  mkdirSync(dir, { recursive: true });
  const { serveUrl, composition, browserExecutable } = await openComposition(props);
  let n = 0;
  for (const s of props.segments) {
    // Late enough for everything to have popped in; before the fade-out.
    const at = option("--at"); // e.g. 0.1: shortly after each scene starts, as the video first shows it
    const seconds = at !== undefined ? s.start + (s.end - s.start) * Number(at) : Math.min(s.start + Math.max(0.5, (s.end - s.start) * 0.8), s.end - 0.4);
    const frame = Math.max(0, Math.min(composition.durationInFrames - 1, Math.round(seconds * FPS)));
    const file = join(dir, `${String(n + 1).padStart(2, "0")}-${s.scene.template}-cue${s.cues[0]}.png`);
    await renderStill({ composition, serveUrl, output: file, frame, inputProps: props, browserExecutable, chromiumOptions, timeoutInMilliseconds });
    console.log(`${file}  (${s.start.toFixed(2)}–${s.end.toFixed(2)} s, cues ${s.cues[0]}–${s.cues[1]})`);
    n++;
  }
  return dir;
}

async function render(visualsPath: string, projectPath: string): Promise<string> {
  const props = buildProps(visualsPath, projectPath);
  const name = basename(projectPath).replace(/\.project\.json$|\.json$/, "");
  const output = resolve(option("-o") ?? join(dirname(resolve(projectPath)), `${name}.visuals.mp4`));
  mkdirSync(dirname(output), { recursive: true });
  const { serveUrl, composition, browserExecutable } = await openComposition(props);
  let shown = -1;
  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    outputLocation: output,
    inputProps: props,
    browserExecutable,
    chromiumOptions,
    timeoutInMilliseconds,
    muted: true,
    logLevel: "error",
    onProgress: ({ progress }) => {
      const pct = Math.floor(progress * 10) * 10;
      if (pct !== shown) process.stderr.write(`rendering ${(shown = pct)}%\n`);
    },
  });
  return output;
}

/** Makes `video` the picture of the lesson body; the intro/outro visuals stay. */
export function apply(projectPath: string, video: string): void {
  const project = readJson<Project>(projectPath);
  const { start, end } = bodyRange(project);
  const path = resolve(video);
  if (!existsSync(path)) throw new Error(`no such video: ${path}`);
  const bg = { kind: "video", path, start, end, source_start: 0, fit: "cover" };
  const kept = project.visuals.filter((v) => v.end <= start + 1e-6 || v.start >= end - 1e-6);
  // Visuals under the body (slides, colour) give way; anything before/after (intro, outro) stays.
  project.visuals = [...kept.filter((v) => v.end <= start + 1e-6), bg, ...kept.filter((v) => v.start >= end - 1e-6)];
  writeFileSync(projectPath, JSON.stringify(project, null, 2) + "\n", "utf8");
}

/** The cues of a project, or of a script not voiced yet (one per spoken line). */
function cuesOf(path: string): { cues: Cue[]; title?: string; errors: string[]; warnings: string[] } {
  if (/\.txt$/i.test(path)) {
    const r = parseScript(readFileSync(resolve(path), "utf8"));
    const cues = r.lines.map((l, i) => ({ start: i, end: i + 1, text: l.text, translation: l.translation }));
    return { cues, errors: r.errors.map((e) => `script ${e}`), warnings: r.warnings.map((w) => `script ${w}`) };
  }
  const project = readJson<Project>(resolve(path));
  return { cues: project.subtitles ?? [], title: typeof project.title === "string" ? project.title : undefined, errors: [], warnings: [] };
}

async function main() {
  const [cmd, a, b] = process.argv.slice(2);
  try {
    if (cmd === "prompt" && a) {
      // What to give a language model so it writes the visuals file (see opencut_scenes.py).
      const { cues, title } = cuesOf(a);
      console.log(buildPrompt(cues, title));
    } else if (cmd === "check" && a && b) {
      const { cues, errors: scriptErrors, warnings: scriptWarnings } = cuesOf(b);
      const dir = dirname(resolve(a));
      const found = (src: string) => existsSync(resolve(dir, src)) || existsSync(join(root, "public", src));
      const report = validate(readJson(resolve(a)), cues.length, found);
      const errors = [...scriptErrors, ...report.errors];
      const warnings = [...scriptWarnings, ...report.warnings];
      for (const w of warnings) console.log(`warning: ${w}`);
      for (const e of errors) console.log(`error: ${e}`);
      if (errors.length) process.exit(1);
      console.log(`${a}: ok (${warnings.length} warnings)`);
    } else if (cmd === "thumbnail" && a) {
      console.log(await thumbnail(resolve(a)));
    } else if (cmd === "short" && a && b) {
      console.log(await shortVideo(a, b));
    } else if (cmd === "whisper-setup") {
      await whisperSetup();
    } else if (cmd === "words" && a) {
      console.log(words(resolve(a)));
    } else if (cmd === "apply" && a && b) {
      apply(resolve(a), b);
      console.log(`${a}: body picture is ${resolve(b)}`);
    } else if (cmd === "preview" && a && b) {
      await preview(a, b);
    } else if (cmd === "render" && a && b) {
      console.log(await render(a, b));
    } else if (cmd === "build" && a && b) {
      const video = await render(a, b);
      apply(resolve(b), video);
      console.log(video);
    } else {
      console.error("usage: bun run lesson <preview|render|build> <x.visuals.json> <x.project.json> [-o out]\n       bun run lesson apply <x.project.json> <bg.mp4>");
      process.exit(2);
    }
  } catch (error) {
    console.error(`lesson: ${error instanceof Error ? error.message : error}`);
    process.exit(1);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === import.meta.filename) await main();
