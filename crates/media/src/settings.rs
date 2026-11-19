//! User settings the media crate honours, kept in one small JSON file so the
//! desktop app, the CLI and the MCP server all agree on them.
//!
//! The only one so far is the H.264 switch. H.264 encoding comes from
//! Cisco's OpenH264 module, which Cisco asks apps to let the user turn off:
//! with it off, nothing here asks FFmpeg for H.264.

use std::path::PathBuf;

use serde::{Deserialize, Serialize};

use crate::Result;

#[derive(Deserialize, Serialize)]
struct Settings {
    #[serde(default = "on")]
    h264: bool,
}

fn on() -> bool {
    true
}

/// `$OPENCUT_CONFIG_DIR`, else the platform's config folder:
/// `%APPDATA%\OpenCut` on Windows, `~/Library/Application Support/OpenCut`
/// on macOS, `$XDG_CONFIG_HOME/opencut` or `~/.config/opencut` elsewhere.
fn config_dir() -> Option<PathBuf> {
    let var = |name: &str| std::env::var_os(name).filter(|value| !value.is_empty());
    if let Some(dir) = var("OPENCUT_CONFIG_DIR") {
        return Some(dir.into());
    }
    if cfg!(windows) {
        return var("APPDATA").map(|dir| PathBuf::from(dir).join("OpenCut"));
    }
    if cfg!(target_os = "macos") {
        return var("HOME")
            .map(|home| PathBuf::from(home).join("Library/Application Support/OpenCut"));
    }
    var("XDG_CONFIG_HOME")
        .map(|dir| PathBuf::from(dir).join("opencut"))
        .or_else(|| var("HOME").map(|home| PathBuf::from(home).join(".config/opencut")))
}

fn settings_path() -> Option<PathBuf> {
    config_dir().map(|dir| dir.join("settings.json"))
}

/// Whether H.264 encoding (Cisco's OpenH264) may be used. On unless the user
/// turned it off; a missing or unreadable settings file means on.
pub fn h264_enabled() -> bool {
    settings_path()
        .and_then(|path| std::fs::read(path).ok())
        .and_then(|bytes| serde_json::from_slice::<Settings>(&bytes).ok())
        .map_or(true, |settings| settings.h264)
}

/// Turns H.264 encoding on or off for every OpenCut program, and keeps it so.
pub fn set_h264_enabled(enabled: bool) -> Result<()> {
    let Some(path) = settings_path() else {
        return Err(std::io::Error::other("no config folder: set OPENCUT_CONFIG_DIR").into());
    };
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let json =
        serde_json::to_vec_pretty(&Settings { h264: enabled }).map_err(std::io::Error::other)?;
    std::fs::write(path, json)?;
    Ok(())
}
