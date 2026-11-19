//! Checks the pinned FFmpeg is in place and tells dependents where its
//! shared libraries are. ffmpeg-sys-next does the linking itself, from
//! FFMPEG_DIR, which `.cargo/config.toml` points at `.cache/media/current`.

use std::{env, path::PathBuf};

fn main() {
    println!("cargo:rerun-if-env-changed=FFMPEG_DIR");
    let Some(dir) = env::var_os("FFMPEG_DIR").map(PathBuf::from) else {
        panic!("FFMPEG_DIR is not set: build from the repository so .cargo/config.toml applies");
    };
    if !dir.join("include").is_dir() {
        panic!(
            "no FFmpeg build at {}: run `moon run media:setup` (or `bun run crates/media/setup/setup.ts`) first",
            dir.display()
        );
    }
    // Shared libraries: lib/ everywhere, except Windows DLLs, which live in bin/.
    let lib_dir = if env::var("CARGO_CFG_WINDOWS").is_ok() {
        dir.join("bin")
    } else {
        dir.join("lib")
    };
    let lib_dir = lib_dir.canonicalize().unwrap_or(lib_dir);
    println!("cargo:rerun-if-changed={}", lib_dir.display());
    println!("cargo:lib_dir={}", lib_dir.display());

    // This crate's own tests and examples.
    if env::var("CARGO_CFG_UNIX").is_ok() {
        println!("cargo:rustc-link-arg=-Wl,-rpath,{}", lib_dir.display());
    }
    if env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("linux") {
        println!("cargo:rustc-link-arg=-Wl,--disable-new-dtags");
    }
}
