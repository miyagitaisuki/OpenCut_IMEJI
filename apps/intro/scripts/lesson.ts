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
// Options: -o <path> (video, or folder for stills). Set REMOTION_BROWSER to
// a Chrome/Chromium binary to use it instead of Remotion's own.

import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";

import { planScenes } from "../src/lesson/plan.ts";
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

export function buildProps(visualsPath: string, projectPath: string): LessonProps {
  const visuals = readJson<VisualsFile>(visualsPath);
  const project = readJson<Project>(projectPath);
  const cues: Cue[] = project.subtitles ?? [];
  const { start, end } = bodyRange(project);
  const duration = Math.round((end - start) * 1000) / 1000;
  return { duration, segments: planScenes(cues, visuals.scenes ?? [], start, duration) };
}

async function openComposition(props: LessonProps) {
  const serveUrl = await bundle({ entryPoint: join(root, "src", "index.ts") });
  const browserExecutable = process.env.REMOTION_BROWSER || null;
  const composition = await selectComposition({ serveUrl, id: "Lesson", inputProps: props, browserExecutable, chromiumOptions, timeoutInMilliseconds });
  return { serveUrl, composition, browserExecutable };
}

async function preview(visualsPath: string, projectPath: string): Promise<string> {
  const props = buildProps(visualsPath, projectPath);
  const dir = resolve(option("-o") ?? join(root, "out", `${basename(visualsPath).replace(/\.visuals\.json$|\.json$/, "")}-preview`));
  mkdirSync(dir, { recursive: true });
  const { serveUrl, composition, browserExecutable } = await openComposition(props);
  let n = 0;
  for (const s of props.segments) {
    // Late enough for everything to have popped in; before the fade-out.
    const seconds = Math.min(s.start + Math.max(0.5, (s.end - s.start) * 0.8), s.end - 0.4);
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

async function main() {
  const [cmd, a, b] = process.argv.slice(2);
  try {
    if (cmd === "apply" && a && b) {
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
