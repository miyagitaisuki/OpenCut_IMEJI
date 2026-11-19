use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::Path;

use crate::Result;

/// Byte order of a decoded frame's pixels. Both are 8 bits per channel,
/// 4 channels, no padding between rows.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum PixelFormat {
    /// What image files and most libraries expect.
    #[default]
    Rgba,
    /// What GPUI (and most GPU texture uploads) expect.
    Bgra,
}

impl PixelFormat {
    pub(crate) fn to_ffmpeg(self) -> ffmpeg_next::format::Pixel {
        match self {
            Self::Rgba => ffmpeg_next::format::Pixel::RGBA,
            Self::Bgra => ffmpeg_next::format::Pixel::BGRA,
        }
    }
}

/// One decoded video frame, tightly packed (`width * 4` bytes per row).
#[derive(Clone, Debug)]
pub struct Frame {
    pub width: u32,
    pub height: u32,
    pub format: PixelFormat,
    /// Presentation time from the start of the stream.
    pub seconds: f64,
    pub data: Vec<u8>,
}

impl Frame {
    /// Encodes the frame as a PNG.
    pub fn write_png(&self, out: impl Write) -> Result<()> {
        let mut encoder = png::Encoder::new(out, self.width, self.height);
        encoder.set_color(png::ColorType::Rgba);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder.write_header()?;
        match self.format {
            PixelFormat::Rgba => writer.write_image_data(&self.data)?,
            PixelFormat::Bgra => writer.write_image_data(&self.to_rgba_bytes())?,
        }
        writer.finish()?;
        Ok(())
    }

    pub fn png_bytes(&self) -> Result<Vec<u8>> {
        let mut bytes = Vec::new();
        self.write_png(&mut bytes)?;
        Ok(bytes)
    }

    pub fn save_png(&self, path: impl AsRef<Path>) -> Result<()> {
        let mut file = BufWriter::new(File::create(path)?);
        self.write_png(&mut file)?;
        file.flush()?;
        Ok(())
    }

    fn to_rgba_bytes(&self) -> Vec<u8> {
        let mut data = self.data.clone();
        for pixel in data.chunks_exact_mut(4) {
            pixel.swap(0, 2);
        }
        data
    }
}
