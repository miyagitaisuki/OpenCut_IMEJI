//! Bakes the pinned FFmpeg's location into the binary (rpath), so the app
//! runs straight from target/ without a library path.

fn main() {
    let Ok(lib_dir) = std::env::var("DEP_OPENCUT_FFMPEG_LIB_DIR") else {
        return;
    };
    // (Windows has no rpath: crates/media's build script puts the DLLs
    // beside the binaries instead.)
    if std::env::var("CARGO_CFG_UNIX").is_ok() {
        println!("cargo:rustc-link-arg=-Wl,-rpath,{lib_dir}");
    }
    // DT_RPATH rather than DT_RUNPATH on Linux: it also applies to the
    // libraries' own dependencies (libavcodec needs libswresample).
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("linux") {
        println!("cargo:rustc-link-arg=-Wl,--disable-new-dtags");
    }
}

