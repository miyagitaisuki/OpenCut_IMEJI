//! Media probing and decoding for OpenCut.
//!
//! Everything here runs on the pinned FFmpeg build that `setup/setup.ts`
//! puts in `.cache/media/`. The crate is UI-free so the desktop app, the
//! headless CLI and the MCP server all decode the same way.
//!
//! ```no_run
//! use opencut_media::{probe, PixelFormat, VideoDecoder};
//!
//! let info = probe("clip.mp4")?;
//! let mut decoder = VideoDecoder::open("clip.mp4", PixelFormat::Rgba, Some(640))?;
//! let frame = decoder.frame_at(info.duration_seconds / 2.0)?;
//! frame.save_png("middle.png")?;
//! # Ok::<(), opencut_media::Error>(())
//! ```

mod audio;
mod decode;
mod encode;
mod error;
mod frame;
mod probe;

pub use audio::{AudioBuffer, decode_audio};
pub use decode::{VideoDecoder, thumbnails};
pub use encode::{AudioSettings, VideoCodec, VideoSettings, VideoWriter};
pub use error::{Error, Result};
pub use frame::{Frame, PixelFormat};
pub use probe::{AudioStream, MediaInfo, OtherStream, VideoStream, probe};

use std::sync::Once;

/// Initialises FFmpeg once per process. Every public entry point calls it,
/// so callers never need to.
pub(crate) fn init() -> Result<()> {
    static INIT: Once = Once::new();
    let mut result = Ok(());
    INIT.call_once(|| {
        result = ffmpeg_next::init().map_err(Error::from);
        // Decoding problems are reported through `Error`, not stderr.
        ffmpeg_next::util::log::set_level(ffmpeg_next::util::log::Level::Error);
    });
    result
}
