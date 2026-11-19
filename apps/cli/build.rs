//! Bakes the pinned FFmpeg's location into the binary (rpath), so
//! `opencut` runs straight from target/ without a library path, which is
//! how MCP clients launch it.

fn main() {
    let Ok(lib_dir) = std::env::var("DEP_OPENCUT_FFMPEG_LIB_DIR") else {
        return;
    };
    // Windows has no rpath: it looks for DLLs beside the .exe. Copy them
    // into the profile folder (target/debug, target/release) the .exe goes in.
    if std::env::var("CARGO_CFG_WINDOWS").is_ok() {
        copy_dlls(std::path::Path::new(&lib_dir));
    }
    if std::env::var("CARGO_CFG_UNIX").is_ok() {
        println!("cargo:rustc-link-arg=-Wl,-rpath,{lib_dir}");
    }
    // DT_RPATH rather than DT_RUNPATH on Linux: it also applies to the
    // libraries' own dependencies (libavcodec needs libswresample).
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("linux") {
        println!("cargo:rustc-link-arg=-Wl,--disable-new-dtags");
    }
}

/// OUT_DIR is target/<profile>/build/<crate>-<hash>/out: three folders up
/// is where Cargo puts the binaries.
fn copy_dlls(from: &std::path::Path) {
    let Some(out_dir) = std::env::var_os("OUT_DIR") else {
        return;
    };
    let Some(profile_dir) = std::path::Path::new(&out_dir).ancestors().nth(3) else {
        return;
    };
    let Ok(entries) = std::fs::read_dir(from) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path
            .extension()
            .is_some_and(|e| e.eq_ignore_ascii_case("dll"))
            && let Some(name) = path.file_name()
        {
            let _ = std::fs::copy(&path, profile_dir.join(name));
        }
    }
    println!("cargo:rerun-if-changed={}", from.display());
}
