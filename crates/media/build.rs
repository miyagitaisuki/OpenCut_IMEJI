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

    // Windows has no rpath: a program finds DLLs beside its .exe. Put them
    // where Cargo writes binaries (target/<profile>) and tests (…/deps), so
    // every binary and test that links this crate runs as built.
    if env::var("CARGO_CFG_WINDOWS").is_ok() {
        copy_dlls(&lib_dir);
    }

    // This crate's own tests and examples.
    if env::var("CARGO_CFG_UNIX").is_ok() {
        println!("cargo:rustc-link-arg=-Wl,-rpath,{}", lib_dir.display());
    }
    if env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("linux") {
        println!("cargo:rustc-link-arg=-Wl,--disable-new-dtags");
    }
}

/// OUT_DIR is target/<profile>/build/<crate>-<hash>/out: three folders up
/// is the profile folder.
fn copy_dlls(from: &std::path::Path) {
    let Some(out_dir) = env::var_os("OUT_DIR") else {
        return;
    };
    let Some(profile_dir) = std::path::Path::new(&out_dir).ancestors().nth(3) else {
        return;
    };
    let Ok(entries) = std::fs::read_dir(from) else {
        return;
    };
    let dlls: Vec<_> = entries
        .flatten()
        .map(|entry| entry.path())
        .filter(|path| {
            path.extension()
                .is_some_and(|e| e.eq_ignore_ascii_case("dll"))
        })
        .collect();
    for dir in [
        profile_dir.to_owned(),
        profile_dir.join("deps"),
        profile_dir.join("examples"),
    ] {
        let _ = std::fs::create_dir_all(&dir);
        for dll in &dlls {
            if let Some(name) = dll.file_name() {
                let _ = std::fs::copy(dll, dir.join(name));
            }
        }
    }
}
