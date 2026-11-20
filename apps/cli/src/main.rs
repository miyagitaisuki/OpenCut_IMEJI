//! `opencut`: OpenCut without a window.
//!
//! The same decoding the desktop app uses, for scripts and batch jobs
//! (`probe`, `frame`, `thumbnails`) and for AI agents (`mcp`, a Model
//! Context Protocol server on stdio).

mod env;
mod lesson;
mod mcp;

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use clap::ValueEnum;
use clap::{Parser, Subcommand};
use opencut_media::{PixelFormat, VideoDecoder, probe, thumbnails};

#[derive(Parser)]
#[command(name = "opencut", version, about)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Clone, Copy, Eq, PartialEq, ValueEnum)]
enum Switch {
    On,
    Off,
}

#[derive(Subcommand)]
enum Command {
    /// Print a file's container, duration and streams as JSON.
    Probe { file: PathBuf },
    /// Save the frame showing at a time as a PNG.
    Frame {
        file: PathBuf,
        /// Time in seconds.
        #[arg(long, short = 't', default_value_t = 0.0)]
        at: f64,
        #[arg(long, short)]
        output: PathBuf,
        /// Longest side in pixels; frames are never scaled up.
        #[arg(long)]
        max_size: Option<u32>,
    },
    /// Save frames spread evenly over the video as PNGs.
    Thumbnails {
        file: PathBuf,
        #[arg(long, short = 'n', default_value_t = 6)]
        count: usize,
        #[arg(long, short)]
        out_dir: PathBuf,
        #[arg(long, default_value_t = 320)]
        max_size: u32,
    },
    /// Build a lesson project from the audio, .srt and .timeline.json textts made.
    ImportTextts {
        /// The audio textts made (`<name>.mp3`).
        audio: PathBuf,
        /// Where to save the project.
        #[arg(long, short)]
        output: PathBuf,
        /// Defaults to `<name>.srt` beside the audio.
        #[arg(long)]
        srt: Option<PathBuf>,
        /// Defaults to `<name>.timeline.json` beside the audio.
        #[arg(long)]
        timeline: Option<PathBuf>,
        /// textts script (.txt) or project (.json): keeps furigana in the subtitles.
        #[arg(long)]
        script: Option<PathBuf>,
        /// Loudness to bring the mix to, in LUFS (default -16).
        #[arg(long, allow_hyphen_values = true)]
        loudness: Option<f64>,
        /// Video to open the lesson with (e.g. a Remotion intro from apps/intro).
        #[arg(long)]
        intro: Option<PathBuf>,
        /// Video to close the lesson with.
        #[arg(long)]
        outro: Option<PathBuf>,
        /// Slide image; repeat in order (one per scene, one per line, or spread evenly).
        #[arg(long = "slide")]
        slides: Vec<PathBuf>,
        #[arg(long)]
        title: Option<String>,
        #[arg(long)]
        width: Option<u32>,
        #[arg(long)]
        height: Option<u32>,
        #[arg(long)]
        fps: Option<u32>,
        /// `#rrggbb`.
        #[arg(long)]
        background: Option<String>,
    },
    /// Put a chibi mascot in a corner of the lesson, changing pose with each
    /// sentence (poses picked from the subtitles). Run it after intro/outro are added.
    Mascot {
        project: PathBuf,
        /// Avatar folder with `avatar.json` and a `poses` map (apps/intro/public/avatars/chibi).
        #[arg(long)]
        avatar: Option<PathBuf>,
        /// bottom-right (default) or bottom-left.
        #[arg(long)]
        corner: Option<String>,
        /// Height as a fraction of the picture (default 0.55).
        #[arg(long)]
        height: Option<f64>,
        /// Take the mascot out of the project.
        #[arg(long)]
        remove: bool,
    },
    /// List what would stop a project from rendering.
    Check { project: PathBuf },
    /// Render a project to a video, with .vtt/.srt subtitles and .markers.json beside it.
    Render {
        project: PathBuf,
        /// Defaults to `<project>.mp4`.
        #[arg(long, short)]
        output: Option<PathBuf>,
        /// auto (H.264 when available), h264 or mpeg4.
        #[arg(long, default_value = "auto")]
        codec: String,
        /// Draw the subtitles into the picture, furigana and translation
        /// included (for YouTube, which shows neither from a .vtt).
        #[arg(long)]
        burn_subtitles: bool,
        /// Font for burned-in subtitles; repeat to add fallbacks. Defaults
        /// to the system's Japanese fonts (Yu Gothic, Meiryo, Noto Sans CJK).
        #[arg(long = "font")]
        fonts: Vec<PathBuf>,
    },
    /// Turn H.264 encoding (Cisco's OpenH264) on or off, or show the setting.
    /// Off: `render` falls back to MPEG-4 and `--codec h264` is refused.
    H264 {
        /// on or off; omit to show the current setting.
        state: Option<Switch>,
    },
    /// Show the FFmpeg binaries and tools the pipeline uses, and what is missing (exit 1 on issues).
    Env,
    /// Serve the editor's tools to AI agents over MCP (stdio).
    Mcp,
}

fn main() -> Result<()> {
    match Cli::parse().command {
        Command::Probe { file } => {
            let info = probe(&file)?;
            println!("{}", serde_json::to_string_pretty(&info)?);
        }
        Command::Frame {
            file,
            at,
            output,
            max_size,
        } => {
            let frame = VideoDecoder::open(&file, PixelFormat::Rgba, max_size)?.frame_at(at)?;
            frame
                .save_png(&output)
                .with_context(|| format!("writing {}", output.display()))?;
            eprintln!(
                "{}: {}x{} frame at {:.3}s",
                output.display(),
                frame.width,
                frame.height,
                frame.seconds
            );
        }
        Command::Thumbnails {
            file,
            count,
            out_dir,
            max_size,
        } => {
            for path in save_thumbnails(&file, count, max_size, &out_dir)? {
                println!("{}", path.display());
            }
        }
        Command::ImportTextts {
            audio,
            output,
            srt,
            timeline,
            script,
            loudness,
            intro,
            outro,
            slides,
            title,
            width,
            height,
            fps,
            background,
        } => {
            let result = lesson::import(&lesson::ImportRequest {
                audio,
                project: output,
                srt,
                timeline,
                script,
                loudness_lufs: loudness,
                intro,
                outro,
                slides,
                title,
                width,
                height,
                fps,
                background,
            })?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Command::Mascot {
            project,
            avatar,
            corner,
            height,
            remove,
        } => {
            let result = lesson::set_mascot(&project, avatar, corner.as_deref(), height, remove)?;
            println!("{}", serde_json::to_string_pretty(&result)?);
        }
        Command::Check { project } => {
            let result = lesson::check(&project)?;
            println!("{}", serde_json::to_string_pretty(&result)?);
            if !result.ok {
                std::process::exit(1);
            }
        }
        Command::Render {
            project,
            output,
            codec,
            burn_subtitles,
            fonts,
        } => {
            let choices = lesson::RenderChoices {
                codec: lesson::parse_codec(Some(&codec))?,
                burn_subtitles,
                fonts,
            };
            let report = lesson::render_project(&project, output.as_deref(), choices, |done| {
                eprint!("\rrendering {:>3.0}%", done * 100.0);
            })?;
            eprintln!();
            for warning in &report.warnings {
                eprintln!("warning: {warning}");
            }
            println!("{}", serde_json::to_string_pretty(&report)?);
        }
        Command::H264 { state } => {
            if let Some(state) = state {
                opencut_media::set_h264_enabled(state == Switch::On)?;
            }
            let on = opencut_media::h264_enabled();
            println!("H.264 is {}", if on { "on" } else { "off" });
        }
        Command::Env => {
            let report = env::report();
            println!("{}", serde_json::to_string_pretty(&report)?);
            if !report.issues.is_empty() {
                std::process::exit(1);
            }
        }
        Command::Mcp => {
            tokio::runtime::Runtime::new()?.block_on(mcp::serve())?;
        }
    }
    Ok(())
}

/// Writes `<stem>-<n>.png` files into `out_dir`, returning their paths.
pub(crate) fn save_thumbnails(
    file: &Path,
    count: usize,
    max_size: u32,
    out_dir: &Path,
) -> Result<Vec<PathBuf>> {
    std::fs::create_dir_all(out_dir).with_context(|| format!("creating {}", out_dir.display()))?;
    let stem = file
        .file_stem()
        .map_or("frame".into(), |stem| stem.to_string_lossy());
    let width = count.to_string().len();
    thumbnails(file, count, PixelFormat::Rgba, Some(max_size))?
        .iter()
        .enumerate()
        .map(|(i, frame)| {
            let path = out_dir.join(format!("{stem}-{:0width$}.png", i + 1));
            frame.save_png(&path)?;
            Ok(path)
        })
        .collect()
}
