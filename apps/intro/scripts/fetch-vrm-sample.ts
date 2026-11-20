// Downloads pixiv's sample VRM (VRM Public License 1.0: redistribution,
// modification and commercial use by corporations allowed, no credit needed)
// into public/avatars/vrm-sample/model.vrm. The file is 10 MB, so it is not
// kept in git. Use your own model by putting it in another folder under
// public/avatars/ with an avatar.json like vrm-sample's.
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const url =
  "https://raw.githubusercontent.com/pixiv/three-vrm/dev/packages/three-vrm/examples/models/VRM1_Constraint_Twist_Sample.vrm";
const dir = resolve(import.meta.dir, "..", "public", "avatars", "vrm-sample");
mkdirSync(dir, { recursive: true });
const response = await fetch(url);
if (!response.ok) throw new Error(`download failed: ${response.status} ${url}`);
const bytes = new Uint8Array(await response.arrayBuffer());
writeFileSync(join(dir, "model.vrm"), bytes);
console.log(`${join(dir, "model.vrm")} (${(bytes.length / 1e6).toFixed(1)} MB)`);
