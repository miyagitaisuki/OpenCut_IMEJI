//! `opencut env`: which FFmpeg and tools this OpenCut uses, where they are, and what is missing.
//!
//! The pinned FFmpeg (`.cache/media/current`, set by `FFMPEG_DIR` at build time) is shared
//! libraries only: it is built without programs. The `ffmpeg` and `ffprobe` *binaries* that
//! textts and `lesson.ts words` call come from elsewhere, so they are resolved here and
//! reported, not left to whatever PATH happens to hold.

use std::net::{SocketAddr, TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use serde::Serialize;

/// The pinned FFmpeg folder this binary was built against (`.cargo/config.toml`).
const PINNED_DIR: &str = env!("FFMPEG_DIR");

#[derive(Serialize)]
pub struct Tool {
    pub path: String,
    pub version: Option<String>,
    /// Every line of `-version`, kept for checks (not printed unless it is short).
    #[serde(skip)]
    pub version_full: Option<String>,
}

#[derive(Serialize)]
pub struct FfmpegLibs {
    pub dir: String,
    pub present: bool,
    pub libraries: Vec<String>,
}

#[derive(Serialize)]
pub struct Report {
    pub opencut: Tool,
    pub ffmpeg_libs: FfmpegLibs,
    pub ffmpeg: Option<Tool>,
    pub ffprobe: Option<Tool>,
    pub node: Option<Tool>,
    pub h264: bool,
    /// Missing things that stop a lesson build. Any entry makes `opencut env` exit 1.
    pub issues: Vec<String>,
    /// Things that work but may not match what the pipeline was tested with.
    pub warnings: Vec<String>,
}

pub fn report() -> Report {
    let mut issues = Vec::new();
    let mut warnings = Vec::new();

    let libs = ffmpeg_libs();
    if !libs.present {
        issues.push(format!("pinned FFmpeg libraries not found in {}: run `moon run media:setup`", libs.dir));
    }

    let pinned_avcodec = libs.libraries.iter().find_map(|name| avcodec_major_from_file(name));
    let ffmpeg = resolve("ffmpeg", "OPENCUT_FFMPEG").map(|p| tool(&p, &["-version"]));
    let ffprobe = resolve("ffprobe", "OPENCUT_FFPROBE").map(|p| tool(&p, &["-version"]));
    let node = resolve("node", "OPENCUT_NODE").map(|p| tool(&p, &["--version"]));

    match &ffmpeg {
        None => issues.push(
            "no ffmpeg binary: textts and `lesson words` need one; set OPENCUT_FFMPEG or put ffmpeg on PATH".into(),
        ),
        Some(found) if found.path.contains("textts-gui") => warnings.push(format!(
            "using textts' bundled ffmpeg ({}); the pinned build is {}",
            found.version.as_deref().unwrap_or("unknown version"),
            libs.dir
        )),
        Some(found) => {
            // `ffmpeg -version` lists "libavcodec 62.x.x": the binary must match the pinned libraries' major.
            let binary = found.version_full.as_deref().and_then(libavcodec_major);
            if let (Some(pinned), Some(binary)) = (pinned_avcodec.as_deref(), binary.as_deref()) {
                if pinned != binary {
                    warnings.push(format!(
                        "ffmpeg binary has libavcodec {binary}, but the pinned libraries are libavcodec {pinned}: textts and lesson.ts use the binary, the render uses the pinned libraries; use a matching FFmpeg"
                    ));
                }
            }
        }
    }
    if ffprobe.is_none() {
        warnings.push("no ffprobe binary: `lesson words` may fail; set OPENCUT_FFPROBE or put it on PATH".into());
    }
    if node.is_none() {
        issues.push("no node: `lesson.ts` (intro, lesson build, words) needs Node 22+ on PATH or OPENCUT_NODE".into());
    }

    // The homograph tagger (fugashi + a dictionary) runs in OPENCUT_TAGGER_PYTHON if set, else python on PATH.
    // An explicitly configured interpreter that fails is an issue; the default one only a warning (the step is optional).
    let tagger_set = std::env::var_os("OPENCUT_TAGGER_PYTHON").filter(|v| !v.is_empty()).is_some();
    match resolve("python", "OPENCUT_TAGGER_PYTHON") {
        None if tagger_set => issues.push("OPENCUT_TAGGER_PYTHON is set but is not a file".into()),
        None => warnings.push("no python on PATH: homograph suggestions run rules only".into()),
        Some(py) => {
            let works = Command::new(&py)
                .args(["-c", "import fugashi; fugashi.Tagger()('日本語')"])
                .output()
                .map(|out| out.status.success())
                .unwrap_or(false);
            if !works {
                let msg = format!(
                    "fugashi with a dictionary does not run in {}: run `pip install fugashi unidic-lite` there, or homograph suggestions use rules only",
                    py.display()
                );
                if tagger_set { issues.push(msg) } else { warnings.push(msg) }
            }
        }
    }

    // textts is the voice engine: a lesson build cannot start without it.
    match textts_addr() {
        Err(url) => issues.push(format!("TEXTTS_URL must be http://host:port, got {url}")),
        Ok(addr) => {
            if TcpStream::connect_timeout(&addr, Duration::from_secs(1)).is_err() {
                issues.push(format!("textts is not reachable at {addr}: start textts or set TEXTTS_URL"));
            }
        }
    }

    let h264 = opencut_media::h264_enabled();
    if h264 && !opencut_media::hardware_h264_available() {
        warnings.push("the pinned FFmpeg has no h264_mf encoder: H.264 renders use OpenH264, which is slower and differs in quality".into());
    }
    if h264 {
        // Ask the FFmpeg binary which H.264 encoder it has: a library file name does not show that.
        let has_encoder = ffmpeg.as_ref().map_or(false, |f| {
            Command::new(&f.path)
                .args(["-hide_banner", "-encoders"])
                .output()
                .map(|out| String::from_utf8_lossy(&out.stdout).contains("libopenh264") || String::from_utf8_lossy(&out.stdout).contains("libx264"))
                .unwrap_or(false)
        });
        if !has_encoder {
            warnings.push("H.264 is on but ffmpeg has no libopenh264/libx264 encoder; renders fall back to MPEG-4".into());
        }
    }

    Report {
        opencut: Tool {
            path: std::env::current_exe().map(|p| p.display().to_string()).unwrap_or_default(),
            version: Some(env!("CARGO_PKG_VERSION").into()),
            version_full: None,
        },
        ffmpeg_libs: libs,
        ffmpeg,
        ffprobe,
        node,
        h264,
        issues,
        warnings,
    }
}

fn ffmpeg_libs() -> FfmpegLibs {
    // Windows keeps its DLLs in bin/; Linux and macOS keep shared libraries in lib/.
    let bin = Path::new(PINNED_DIR).join(if cfg!(windows) { "bin" } else { "lib" });
    let mut libraries: Vec<String> = std::fs::read_dir(&bin)
        .map(|entries| {
            entries
                .flatten()
                .map(|e| e.file_name().to_string_lossy().into_owned())
                .filter(|name| name.ends_with(".dll") || name.contains(".so") || name.ends_with(".dylib"))
                .collect()
        })
        .unwrap_or_default();
    libraries.sort();
    let present = libraries.iter().any(|name| avcodec_major_from_file(name).is_some());
    FfmpegLibs { dir: bin.display().to_string(), present, libraries }
}

/// `TEXTTS_URL` (default http://127.0.0.1:8000) as a socket address.
fn textts_addr() -> Result<SocketAddr, String> {
    let url = std::env::var("TEXTTS_URL")
        .ok()
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| "http://127.0.0.1:8000".into());
    parse_http_addr(&url)
}

/// `http://host:port[/...]` as a socket address. Err carries the input when it is not that form.
fn parse_http_addr(url: &str) -> Result<SocketAddr, String> {
    let rest = url.trim_end_matches('/').strip_prefix("http://").ok_or_else(|| url.to_string())?;
    let host_port = rest.split('/').next().unwrap_or_default();
    host_port
        .to_socket_addrs()
        .ok()
        .and_then(|mut addrs| addrs.next())
        .ok_or_else(|| url.to_string())
}

/// `OPENCUT_<TOOL>` if set, else the tool on PATH, else (ffmpeg on Windows) the copy textts ships.
fn resolve(name: &str, override_var: &str) -> Option<PathBuf> {
    if let Some(path) = std::env::var_os(override_var).filter(|v| !v.is_empty()) {
        let path = PathBuf::from(path);
        return path.is_file().then_some(path);
    }
    let exe = if cfg!(windows) { format!("{name}.exe") } else { name.to_string() };
    if let Some(path) = std::env::var_os("PATH") {
        for dir in std::env::split_paths(&path) {
            let candidate = dir.join(&exe);
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    if name == "ffmpeg" && cfg!(windows) {
        let bundled = std::env::var_os("LOCALAPPDATA")
            .map(|dir| PathBuf::from(dir).join("Programs/textts-gui/resources/ffmpeg").join(&exe));
        return bundled.filter(|p| p.is_file());
    }
    None
}

fn tool(path: &Path, args: &[&str]) -> Tool {
    let text = Command::new(path)
        .args(args)
        .output()
        .ok()
        .map(|out| String::from_utf8_lossy(&out.stdout).into_owned());
    let version = text
        .as_deref()
        .and_then(|t| t.lines().next().map(|l| l.trim().to_string()))
        .filter(|l| !l.is_empty());
    Tool { path: path.display().to_string(), version, version_full: text }
}

/// The libavcodec major from a library file name: `avcodec-62.dll` (Windows), `libavcodec.so.62` (Linux).
fn avcodec_major_from_file(name: &str) -> Option<String> {
    if let Some(rest) = name.strip_prefix("avcodec-").and_then(|r| r.strip_suffix(".dll")) {
        return Some(rest.to_string());
    }
    name.strip_prefix("libavcodec.so.")
        .and_then(|rest| rest.split('.').next())
        .map(str::to_string)
}

/// The major of the `libavcodec` line in `ffmpeg -version`, e.g. "libavcodec 62.3.100" -> "62".
fn libavcodec_major(text: &str) -> Option<String> {
    text.lines()
        .find_map(|l| l.trim().strip_prefix("libavcodec "))
        .and_then(|rest| rest.trim().split('.').next())
        .map(str::to_string)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn textts_url_must_be_http_host_port() {
        assert!(parse_http_addr("http://127.0.0.1:8000/").is_ok());
        assert!(parse_http_addr("http://127.0.0.1:8000/api").is_ok());
        assert!(parse_http_addr("https://example.com:443").is_err());
        assert!(parse_http_addr("127.0.0.1:8000").is_err());
    }
}
