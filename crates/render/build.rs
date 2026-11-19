//! This crate's tests run FFmpeg: bake its location in (see apps/cli/build.rs).

fn main() {
    let Ok(lib_dir) = std::env::var("DEP_OPENCUT_FFMPEG_LIB_DIR") else {
        return;
    };
    if std::env::var("CARGO_CFG_UNIX").is_ok() {
        println!("cargo:rustc-link-arg=-Wl,-rpath,{lib_dir}");
    }
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("linux") {
        println!("cargo:rustc-link-arg=-Wl,--disable-new-dtags");
    }
}
