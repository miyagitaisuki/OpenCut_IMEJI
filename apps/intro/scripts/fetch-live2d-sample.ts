// Fetches what a Live2D avatar needs and the repository must not hold:
//  - Live2D's Cubism Core (a proprietary "Redistributable Code": see
//    https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html)
//    into public/lib/live2dcubismcore.min.js
//  - Live2D's sample model Hiyori (Free Material License) into
//    public/avatars/live2d-hiyori/ (next to the committed avatar.json)
// Businesses with annual revenue over 10 million JPY need a Cubism SDK
// Release License to publish content made with the SDK; check
// https://www.live2d.com/en/sdk/license/ before releasing lessons.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const root = resolve(import.meta.dir, "..", "public");
const core = "https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js";
const hiyori = "https://api.github.com/repos/Live2D/CubismWebSamples/contents/Samples/Resources/Hiyori";

async function save(url: string, to: string) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`download failed: ${response.status} ${url}`);
  mkdirSync(dirname(to), { recursive: true });
  writeFileSync(to, new Uint8Array(await response.arrayBuffer()));
  console.log(to);
}

type Entry = { type: string; name: string; url: string; download_url: string | null };
async function walk(url: string, dir: string) {
  const response = await fetch(url, { headers: { "user-agent": "opencut-intro" } });
  if (!response.ok) throw new Error(`listing failed: ${response.status} ${url}`);
  for (const entry of (await response.json()) as Entry[]) {
    if (entry.type === "dir") await walk(entry.url, join(dir, entry.name));
    else if (entry.download_url) await save(entry.download_url, join(dir, entry.name));
  }
}

await save(core, join(root, "lib", "live2dcubismcore.min.js"));
await walk(hiyori, join(root, "avatars", "live2d-hiyori"));
