// Puts the pinned FFmpeg build this crate decodes with into
// `.cache/media/`, where `build.rs` finds it. Safe to run again: a build
// already in place is left alone.
//
//   moon run media:setup                    # the pinned prebuilt for this machine
//   moon run media:setup -- --from-source   # build the pinned source here instead
//   bun run setup/setup.ts --target <platform>   # build for another platform
//
// The prebuilts are these same source builds, made for every platform by
// .github/workflows/media-deps.yml and pinned in ffmpeg.json. Cross builds
// need the target's toolchain on PATH: llvm-mingw for Windows (built from
// Linux), Xcode for the other Mac architecture.

import { createHash } from "node:crypto";
import { availableParallelism } from "node:os";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  renameSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";

import manifest from "./ffmpeg.json";

type Download = { url: string; sha256: string };
type Platform = { os: "windows" | "macos" | "linux"; arch: "x86_64" | "aarch64" };

const root = resolve(import.meta.dir, "../../..");
const cache = join(root, ".cache", "media");

function hostPlatform(): Platform {
  const os = ({ win32: "windows", darwin: "macos", linux: "linux" } as const)[process.platform as string];
  const arch = ({ x64: "x86_64", arm64: "aarch64" } as const)[process.arch as string];
  if (!os || !arch) throw new Error(`unsupported platform ${process.platform}-${process.arch}`);
  return { os, arch };
}

function parsePlatform(key: string): Platform {
  const [os, arch] = key.split("-");
  if (!["windows", "macos", "linux"].includes(os) || !["x86_64", "aarch64"].includes(arch)) {
    throw new Error(`unknown platform ${key}: expected e.g. linux-x86_64`);
  }
  return { os, arch } as Platform;
}

const keyOf = (platform: Platform) => `${platform.os}-${platform.arch}`;

function option(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

async function download({ url, sha256 }: Download, to: string) {
  console.log(`downloading ${url}`);
  const response = await fetch(url);
  if (!response.ok) throw new Error(`download failed: ${response.status} ${url}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  const actual = createHash("sha256").update(bytes).digest("hex");
  if (actual !== sha256) {
    throw new Error(`checksum mismatch for ${url}\n  expected ${sha256}\n  got      ${actual}`);
  }
  await Bun.write(to, bytes);
}

function run(command: string[], cwd?: string, env?: Record<string, string>) {
  const result = Bun.spawnSync(command, { cwd, env: env && { ...process.env, ...env }, stdio: ["ignore", "inherit", "inherit"] });
  if (result.exitCode !== 0) throw new Error(`failed: ${command.join(" ")}`);
}

function extract(archive: string, into: string) {
  mkdirSync(into, { recursive: true });
  // bsdtar (Windows 10+, macOS) and GNU tar (Linux) both detect the format.
  // On Windows, the system's own: a GNU tar from Git Bash may come first on
  // PATH, and it reads "C:" as a remote host.
  const tar =
    process.platform === "win32" ? join(process.env.SystemRoot ?? "C:\\Windows", "System32", "tar.exe") : "tar";
  run([tar, "-xf", archive, "-C", into]);
}


const hasOpenH264 = (target: Platform) => keyOf(target) in manifest.openh264.binaries;

type OpenH264 = { include: string; lib: string; pkgconfig: string };
const openh264 = manifest.openh264 as {
  version: string;
  tag: string;
  repository: string;
  binaries: Record<string, { url: string; sha256?: string }>;
};

/// Decompresses a Cisco `.bz2` with whatever this machine has: bzip2, or
/// Python's bz2 module (every Windows machine running textts has Python).
function bunzip2(from: string, to: string) {
  for (const command of [["bzip2", "-dc", from], ["python3", "-c", PY_BZ2, from], ["python", "-c", PY_BZ2, from]]) {
    if (!Bun.which(command[0])) continue;
    const result = Bun.spawnSync(command, { stdout: "pipe", stderr: "ignore" });
    if (result.exitCode === 0) {
      writeFileSync(to, result.stdout);
      return;
    }
  }
  throw new Error("cannot decompress .bz2: install bzip2 or Python");
}
const PY_BZ2 = "import bz2,sys;sys.stdout.buffer.write(bz2.open(sys.argv[1]).read())";

/// Cisco's OpenH264 binary for `target`, saved as `name` in `dir`. FFmpeg
/// loads it at run time. It is Cisco's own unmodified build, fetched from
/// Cisco: that build is the one Cisco's patent licence covers, and it is
/// never repackaged into our archives.
async function fetchOpenH264Binary(target: Platform, dir: string, name: string) {
  const binary = openh264.binaries[keyOf(target)];
  if (!binary) throw new Error(`no OpenH264 binary for ${keyOf(target)}`);
  console.log(`downloading ${binary.url}`);
  const response = await fetch(binary.url);
  if (!response.ok) throw new Error(`download failed: ${response.status} ${binary.url}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  const actual = createHash("sha256").update(bytes).digest("hex");
  if (binary.sha256 && actual !== binary.sha256) {
    throw new Error(`checksum mismatch for ${binary.url}\n  expected ${binary.sha256}\n  got      ${actual}`);
  }
  if (!binary.sha256) console.warn(`OpenH264 ${keyOf(target)} is not pinned; sha256 ${actual}`);
  mkdirSync(dir, { recursive: true });
  const compressed = join(dir, `${name}.bz2`);
  writeFileSync(compressed, bytes);
  bunzip2(compressed, join(dir, name));
  rmSync(compressed);
}

/// What `./configure --enable-libopenh264` links against: OpenH264's headers
/// (from its tagged source) and a library to link. The library itself is
/// Cisco's binary; on Windows an import library is made from its exports.
async function prepareOpenH264(staging: string, target: Platform): Promise<OpenH264> {
  const root = join(staging, "openh264");
  const source = join(root, "source");
  run(["git", "clone", "--depth", "1", "--branch", openh264.tag, openh264.repository, source]);
  const include = join(root, "include");
  mkdirSync(join(include, "wels"), { recursive: true });
  for (const header of readdirSync(join(source, "codec", "api", "wels"))) {
    copyFileSync(join(source, "codec", "api", "wels", header), join(include, "wels", header));
  }
  const lib = join(root, "lib");
  if (target.os === "windows") {
    const arch = target.arch === "x86_64" ? "win64" : "win-arm64";
    const dll = `openh264-${openh264.version}-${arch}.dll`;
    mkdirSync(lib, { recursive: true });
    // The exports FFmpeg's libopenh264 wrappers (encoder and decoder) use.
    writeFileSync(
      join(lib, "openh264.def"),
      [`LIBRARY ${dll}`, "EXPORTS", ...[
          "WelsCreateSVCEncoder",
          "WelsDestroySVCEncoder",
          "WelsCreateDecoder",
          "WelsDestroyDecoder",
          "WelsGetCodecVersion",
          "WelsGetCodecVersionEx",
        ].map((n) => `    ${n}`), ""].join("\n"),
    );
    const machine = target.arch === "x86_64" ? "i386:x86-64" : "arm64";
    run([`${target.arch}-w64-mingw32-dlltool`, "-d", join(lib, "openh264.def"), "-l", join(lib, "libopenh264.dll.a"), "-m", machine]);
  } else {
    await fetchOpenH264Binary(target, lib, "libopenh264.so.8");
    symlinkSync("libopenh264.so.8", join(lib, "libopenh264.so"));
  }
  // FFmpeg's configure finds libopenh264 only through pkg-config.
  const pkgconfig = join(lib, "pkgconfig");
  mkdirSync(pkgconfig, { recursive: true });
  const dir = (path: string) => path.replaceAll("\\", "/");
  writeFileSync(
    join(pkgconfig, "openh264.pc"),
    [
      "Name: openh264",
      "Description: OpenH264 (headers from source, library from Cisco's binary)",
      `Version: ${openh264.version}`,
      `Libs: -L${dir(lib)} -lopenh264`,
      `Cflags: -I${dir(include)}`,
      "",
    ].join("\n"),
  );
  return { include, lib, pkgconfig };
}

/// Puts Cisco's binary where FFmpeg finds it at run time: beside the DLLs
/// on Windows, in lib/ (on the rpath) elsewhere.
async function installOpenH264Runtime(prefix: string, target: Platform) {
  if (target.os === "windows") {
    const arch = target.arch === "x86_64" ? "win64" : "win-arm64";
    await fetchOpenH264Binary(target, join(prefix, "bin"), `openh264-${openh264.version}-${arch}.dll`);
  } else {
    await fetchOpenH264Binary(target, join(prefix, "lib"), "libopenh264.so.8");
  }
}

/// Configure flags for building FFmpeg for `target` on `host`. The same
/// everywhere but for what a platform needs, so every platform decodes the
/// same formats: shared LGPL libraries only, nothing picked up from
/// whatever else the building machine has installed.
function configureFlags(target: Platform, host: Platform): string[] {
  const flags = [
    "--enable-shared",
    "--disable-static",
    "--disable-programs",
    "--disable-doc",
    "--disable-avdevice",
    "--disable-avfilter",
    "--disable-network",
    "--disable-autodetect",
  ];
  const cross = target.os !== host.os || target.arch !== host.arch;
  // H.264 encoding through Cisco's OpenH264 (everything else here is
  // LGPL-only, and FFmpeg has no other H.264 encoder that is).
  if (hasOpenH264(target)) flags.push("--enable-libopenh264");

  switch (target.os) {
    case "windows": {
      if (host.os !== "linux") throw new Error("Windows builds are cross-compiled from Linux with llvm-mingw");
      const prefix = `${target.arch}-w64-mingw32-`;
      if (!Bun.which(`${prefix}clang`)) throw new Error(`${prefix}clang not on PATH: add llvm-mingw's bin/`);
      flags.push(
        "--target-os=mingw32",
        `--arch=${target.arch}`,
        `--cross-prefix=${prefix}`,
        "--enable-cross-compile",
        // Cross builds default to no pkg-config at all ("false"), and
        // libopenh264 is found only through it.
        "--pkg-config=pkg-config",
        // Windows' own threads, so the DLLs need nothing but the system.
        "--disable-pthreads",
        "--enable-w32threads",
      );
      break;
    }
    case "macos": {
      if (host.os !== "macos") throw new Error("macOS builds need a Mac");
      const arch = target.arch === "aarch64" ? "arm64" : "x86_64";
      const machine = `-arch ${arch} -mmacosx-version-min=11.0`;
      // Found through the app's rpath: beside it in development, in the
      // bundle's Frameworks when shipped.
      flags.push("--install-name-dir=@rpath", `--extra-cflags=${machine}`, `--extra-ldflags=${machine}`);
      if (cross) flags.push("--enable-cross-compile", "--target-os=darwin", `--arch=${target.arch}`);
      break;
    }
    case "linux":
      if (cross) throw new Error("Linux builds are made on a machine of the same architecture");
      // libavcodec finds libopenh264 beside itself, wherever the app puts them.
      flags.push("--extra-ldflags=-Wl,-rpath,'$ORIGIN'");
      break;
  }

  if (target.arch === "x86_64" && !Bun.which("nasm")) {
    console.warn("nasm not found: building without x86 assembly, so decoding is slower");
    flags.push("--disable-x86asm");
  }
  return flags;
}

/// Builds the pinned source for `target` into `prefix`, with the licence
/// and the exact recipe beside the libraries, as the LGPL asks of anyone
/// who ships them.
async function buildFromSource(staging: string, target: Platform, flags: string[]): Promise<string> {
  const archive = join(staging, "source.tar.xz");
  await download(manifest.source, archive);
  extract(archive, staging);
  const source = join(staging, readdirSync(staging).find((name) => name !== "source.tar.xz")!);
  const prefix = join(staging, `ffmpeg-${manifest.version}-${keyOf(target)}`);

  const linked = hasOpenH264(target) ? await prepareOpenH264(staging, target) : undefined;
  const openh264Flags = linked
    ? [`--extra-cflags=-I${linked.include}`, `--extra-ldflags=-L${linked.lib}`]
    : [];

  console.log(`building FFmpeg ${manifest.version} for ${keyOf(target)}; this takes a few minutes`);
  run(["./configure", `--prefix=${prefix}`, ...flags, ...openh264Flags], source, linked && { PKG_CONFIG_PATH: linked.pkgconfig });
  run(["make", `-j${availableParallelism()}`], source);
  run(["make", "install"], source);
  // Example programs; nothing the libraries need.
  rmSync(join(prefix, "share"), { recursive: true, force: true });
  if (linked) await installOpenH264Runtime(prefix, target);

  if (target.os === "windows") {
    // DLLs stay in bin/; the import libraries MSVC links against go in lib/.
    for (const name of readdirSync(join(prefix, "bin")).filter((name) => name.endsWith(".lib"))) {
      renameSync(join(prefix, "bin", name), join(prefix, "lib", name));
    }
  }

  copyFileSync(join(source, "COPYING.LGPLv2.1"), join(prefix, "COPYING.LGPLv2.1"));
  copyFileSync(join(source, "LICENSE.md"), join(prefix, "LICENSE.md"));
  writeFileSync(
    join(prefix, "BUILD.md"),
    [
      `# FFmpeg ${manifest.version} for ${keyOf(target)}`,
      "",
      `Built from ${manifest.source.url}`,
      `(SHA-256 ${manifest.source.sha256}), unmodified, configured with:`,
      "",
      "```",
      ...flags,
      "```",
      "",
      "Licensed under the LGPL 2.1 or later: see COPYING.LGPLv2.1 and LICENSE.md.",
      ...(hasOpenH264(target)
        ? [
            "",
            `H.264 encoding uses OpenH264 ${openh264.version} (BSD-2-Clause). Its binary is Cisco's own,`,
            "downloaded from Cisco when this build is set up and not part of the archive.",
          ]
        : []),
      "",
    ].join("\n"),
  );
  return prefix;
}

/// Unpacks a prebuilt archive: one top-level folder with include/, lib/
/// and, on Windows, bin/.
async function installPrebuilt(prebuilt: Download, staging: string): Promise<string> {
  const archive = join(staging, "archive");
  await download(prebuilt, archive);
  extract(archive, staging);
  rmSync(archive);
  return join(staging, readdirSync(staging)[0]);
}

/// Archives leave Cisco's binary out: it is fetched from Cisco here.
async function installPrebuiltWithOpenH264(prebuilt: Download, staging: string, target: Platform) {
  const prefix = await installPrebuilt(prebuilt, staging);
  if (hasOpenH264(target)) await installOpenH264Runtime(prefix, target);
  return prefix;
}

/// Source build flags, or `undefined` where this machine cannot build the
/// target from source (e.g. Windows, which cross-compiles from Linux).
function sourceFlagsIfBuildable(target: Platform, host: Platform): string[] | undefined {
  try {
    return configureFlags(target, host);
  } catch {
    return undefined;
  }
}

/// Points `.cache/media/current` at the host's build: `.cargo/config.toml`
/// hands that path to ffmpeg-sys-next as FFMPEG_DIR. A junction on Windows,
/// which needs no admin rights. Builds for other platforms are left unlinked.
function linkCurrent(destination: string, target: Platform, host: Platform) {
  if (keyOf(target) !== keyOf(host)) return;
  const current = join(cache, "current");
  rmSync(current, { recursive: true, force: true });
  symlinkSync(destination, current, process.platform === "win32" ? "junction" : "dir");
}

async function main() {
  const host = hostPlatform();
  const target = option("--target") ? parsePlatform(option("--target")!) : host;
  const key = keyOf(target);
  const prebuilt = (manifest.platforms as Record<string, Download | undefined>)[key];
  const fromSource = process.argv.includes("--from-source") || key !== keyOf(host) || !prebuilt;

  // What this build is made of: a different pin or recipe rebuilds it.
  const flags = fromSource ? configureFlags(target, host) : [];
  const stamp = fromSource
    ? `source ${manifest.source.sha256} ${createHash("sha256").update(flags.join(" ")).digest("hex")}`
    : `prebuilt ${prebuilt!.sha256} openh264 ${hasOpenH264(target) ? manifest.openh264.version : "none"}`;

  const destination = join(cache, `ffmpeg-${manifest.version}-${key}`);
  const marker = join(destination, ".complete");
  // A source build of the same pin also satisfies a request for the
  // prebuilt: it is what the prebuilt is made from (and what a failed
  // prebuilt download falls back to).
  const sourceFlags = fromSource ? flags : sourceFlagsIfBuildable(target, host);
  const sourceStamp = sourceFlags && `source ${manifest.source.sha256} ${createHash("sha256").update(sourceFlags.join(" ")).digest("hex")}`;
  const accepted = sourceStamp ? [stamp, sourceStamp] : [stamp];
  if (existsSync(marker) && accepted.includes((await Bun.file(marker).text()).trim())) {
    linkCurrent(destination, target, host);
    console.log(`FFmpeg ${manifest.version} for ${key} is ready in ${destination}`);
    return;
  }

  // Made beside the destination and moved in whole, so an interrupted run
  // never leaves a half-finished build that looks complete.
  const staging = `${destination}.partial`;
  rmSync(staging, { recursive: true, force: true });
  mkdirSync(staging, { recursive: true });
  let built: string;
  let builtStamp = stamp;
  if (fromSource) {
    built = await buildFromSource(staging, target, flags);
  } else {
    try {
      built = await installPrebuiltWithOpenH264(prebuilt!, staging, target);
    } catch (error) {
      // Prebuilt hosts prune old builds; the pinned source still builds
      // wherever this machine can build it.
      if (!sourceFlags || !sourceStamp) throw error;
      console.warn(`${error instanceof Error ? error.message : error}\nfalling back to building from source`);
      rmSync(staging, { recursive: true, force: true });
      mkdirSync(staging, { recursive: true });
      built = await buildFromSource(staging, target, sourceFlags);
      builtStamp = sourceStamp;
    }
  }

  rmSync(destination, { recursive: true, force: true });
  renameSync(built, destination);
  rmSync(staging, { recursive: true, force: true });
  writeFileSync(marker, `${builtStamp}\n`);
  linkCurrent(destination, target, host);
  console.log(`FFmpeg ${manifest.version} for ${key} is ready in ${destination}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
