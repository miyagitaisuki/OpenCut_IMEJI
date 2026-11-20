// Renders a voiced scene to a video:
//
//   bun run render scenes/n4-teshimau.props.json          # out/n4-teshimau.mp4
//   bun run render scenes/n4-teshimau.props.json -o intro.mp4
//
// Set REMOTION_BROWSER to a Chrome/Chromium binary to use it instead of
// the one Remotion downloads on first use.

import { mkdirSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";

const root = resolve(import.meta.dir, "..");

function option(name: string): string | undefined {
  const i = process.argv.indexOf(name);
  return i === -1 ? undefined : process.argv[i + 1];
}

const props = process.argv[2];
if (!props || props.startsWith("-")) {
  console.error("usage: bun run render scenes/<name>.props.json [-o out.mp4]");
  process.exit(2);
}
const name = basename(props).replace(/\.props\.json$|\.json$/, "");
const output = resolve(option("-o") ?? join(root, "out", `${name}.mp4`));
mkdirSync(dirname(output), { recursive: true });

const args = [
  "remotion",
  "render",
  "src/index.ts",
  "Intro",
  output,
  `--props=${resolve(props)}`,
  // H.264 + AAC, which OpenCut and every player read.
  "--codec=h264",
  // three.js (the VRM avatars) needs ANGLE; the 2D avatars do not mind it.
  "--gl=angle",
  "--log=error",
];
if (process.env.REMOTION_BROWSER) args.push(`--browser-executable=${process.env.REMOTION_BROWSER}`);

const run = Bun.spawnSync(["bunx", ...args], { cwd: root, stdio: ["inherit", "inherit", "inherit"] });
if (run.exitCode !== 0) process.exit(run.exitCode ?? 1);
console.log(output);
