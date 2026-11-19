// Points ffmpeg.json's prebuilts at a release made by the Media
// dependencies workflow (.github/workflows/media-deps.yml):
//
//   bun run crates/media/setup/pin.ts ffmpeg-8.1.3-1
//   bun run crates/media/setup/pin.ts ffmpeg-8.1.3-1 --repo owner/name
//
// The release's checksums.sha256 gives each archive's hash. Every archive
// is downloaded and checked against it, so a pin never names a file that
// is missing or does not match.

import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";
import { join } from "node:path";

import manifest from "./ffmpeg.json";

function option(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

/// owner/name from --repo, $GITHUB_REPOSITORY, or the origin remote.
function repository(): string {
  const given = option("--repo") ?? process.env.GITHUB_REPOSITORY;
  if (given) return given;
  const result = Bun.spawnSync(["git", "remote", "get-url", "origin"], { cwd: import.meta.dir });
  const url = result.stdout.toString().trim();
  // https://github.com/owner/name(.git), git@github.com:owner/name(.git),
  // or a proxy URL ending in /owner/name.
  const match = url.match(/[/:]([^/:]+)\/([^/]+?)(?:\.git)?$/);
  if (result.exitCode !== 0 || !match) throw new Error("cannot tell the repository: pass --repo owner/name");
  return `${match[1]}/${match[2]}`;
}

async function fetchBytes(url: string): Promise<Uint8Array> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`download failed: ${response.status} ${url}`);
  return new Uint8Array(await response.arrayBuffer());
}

async function main() {
  const tag = process.argv[2];
  if (!tag || tag.startsWith("--")) throw new Error("usage: bun run pin.ts <release tag> [--repo owner/name]");
  const base = `https://github.com/${repository()}/releases/download/${tag}`;

  const checksums = new TextDecoder().decode(await fetchBytes(`${base}/checksums.sha256`));
  const prefix = `ffmpeg-${manifest.version}-`;
  const platforms: Record<string, { url: string; sha256: string }> = {};
  for (const line of checksums.split("\n").filter(Boolean)) {
    const [sha256, name] = line.trim().split(/\s+\*?/);
    if (!name?.startsWith(prefix) || !name.endsWith(".tar.gz")) {
      throw new Error(`unexpected entry in checksums.sha256: ${line}`);
    }
    const url = `${base}/${name}`;
    const actual = createHash("sha256").update(await fetchBytes(url)).digest("hex");
    if (actual !== sha256) throw new Error(`checksum mismatch for ${url}\n  listed ${sha256}\n  got    ${actual}`);
    platforms[name.slice(prefix.length, -".tar.gz".length)] = { url, sha256 };
    console.log(`verified ${name}`);
  }
  if (Object.keys(platforms).length === 0) throw new Error(`${tag} lists no archives`);

  const sorted = Object.fromEntries(Object.entries(platforms).sort(([a], [b]) => a.localeCompare(b)));
  writeFileSync(join(import.meta.dir, "ffmpeg.json"), `${JSON.stringify({ ...manifest, platforms: sorted }, null, 2)}\n`);
  console.log(`pinned ${Object.keys(sorted).join(", ")} to ${tag}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
