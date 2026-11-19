//! `opencut`: OpenCut without a window.
//!
//! The same decoding the desktop app uses, for scripts and batch jobs
//! (`probe`, `frame`, `thumbnails`) and for AI agents (`mcp`, a Model
//! Context Protocol server on stdio).

mod mcp;

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use opencut_media::{PixelFormat, VideoDecoder, probe, thumbnails};

#[derive(Parser)]
#[command(name = "opencut", version, about)]
struct Cli {
    #[command(subcommand)]
    command: Command,
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
