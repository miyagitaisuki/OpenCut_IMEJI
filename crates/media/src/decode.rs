use std::path::{Path, PathBuf};

use ffmpeg_next::{
    codec::{self, threading},
    decoder,
    ffi::{AV_NOPTS_VALUE, AV_TIME_BASE},
    format, frame, media,
    software::scaling,
};

use crate::{Error, Frame, PixelFormat, Result};

/// Decodes the primary video stream of a file, frame by frame or at any
/// time, into packed RGBA or BGRA.
///
/// Holding one open is cheap to step forward with (`next_frame`, for
/// playback) and to jump around in (`frame_at`, for scrubbing). It is
/// `Send`, so it can live on a background thread.
pub struct VideoDecoder {
    path: PathBuf,
    input: format::context::Input,
    stream_index: usize,
    decoder: decoder::Video,
    /// Seconds per stream timestamp tick.
    time_base: f64,
    /// Stream timestamp of its first frame, so times start at zero.
    start_pts: i64,
    duration: f64,
    frame_rate: Option<f64>,
    format: PixelFormat,
    max_size: Option<u32>,
    /// Exact output size, overriding `max_size` (up or down).
    forced_size: Option<(u32, u32)>,
    scaler: Option<Scaler>,
    eof_sent: bool,
}

struct Scaler {
    source: (format::Pixel, u32, u32),
    context: scaling::Context,
    width: u32,
    height: u32,
}

// The scaler holds a raw `SwsContext`, which FFmpeg lets any one thread use
// at a time; `VideoDecoder` owns it exclusively.
unsafe impl Send for Scaler {}

impl VideoDecoder {
    /// Opens `path`. Frames come out in `format`, scaled down (never up) so
    /// neither side exceeds `max_size` when one is given.
    pub fn open(
        path: impl AsRef<Path>,
        format: PixelFormat,
        max_size: Option<u32>,
    ) -> Result<Self> {
        crate::init()?;
        let path = path.as_ref().to_owned();
        let input = format::input(&path).map_err(|source| Error::Open {
            path: path.clone(),
            source,
        })?;

        let stream = input
            .streams()
            .best(media::Type::Video)
            .ok_or_else(|| Error::NoVideo(path.clone()))?;
        let stream_index = stream.index();
        let time_base = f64::from(stream.time_base());
        let start_pts = match stream.start_time() {
            AV_NOPTS_VALUE => 0,
            start => start,
        };
        let rate = stream.avg_frame_rate();
        let frame_rate = (rate.numerator() > 0 && rate.denominator() > 0).then(|| f64::from(rate));

        let mut context = codec::Context::from_parameters(stream.parameters())?;
        // Let FFmpeg pick the thread count; frame threading is what makes
        // H.264/HEVC decode at playback speed on large sources.
        context.set_threading(threading::Config {
            kind: threading::Type::Frame,
            count: 0,
        });
        let decoder = context.decoder().video()?;

        let duration = match input.duration() {
            d if d > 0 => d as f64 / f64::from(AV_TIME_BASE),
            _ => stream.duration().max(0) as f64 * time_base,
        };

        Ok(Self {
            path,
            input,
            stream_index,
            decoder,
            time_base,
            start_pts,
            duration,
            frame_rate,
            format,
            max_size,
            forced_size: None,
            scaler: None,
            eof_sent: false,
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn duration(&self) -> f64 {
        self.duration
    }

    pub fn frame_rate(&self) -> Option<f64> {
        self.frame_rate
    }

    /// The stream's own frame size.
    pub fn source_size(&self) -> (u32, u32) {
        (self.decoder.width(), self.decoder.height())
    }

    /// Size frames come out at, after `max_size` or `set_output_size`.
    pub fn output_size(&self) -> (u32, u32) {
        self.forced_size
            .unwrap_or_else(|| fit(self.decoder.width(), self.decoder.height(), self.max_size))
    }

    /// Scales every frame to exactly `width`×`height` from now on, up or
    /// down, without keeping the aspect ratio (the caller picks a size that does).
    pub fn set_output_size(&mut self, width: u32, height: u32) {
        self.forced_size = Some((width.max(1), height.max(1)));
        self.scaler = None;
    }

    /// The next frame in presentation order, or `None` at the end.
    pub fn next_frame(&mut self) -> Result<Option<Frame>> {
        let mut decoded = frame::Video::empty();
        loop {
            if self.decoder.receive_frame(&mut decoded).is_ok() {
                return self.convert(&decoded).map(Some);
            }
            if self.eof_sent {
                return Ok(None);
            }
            match self.input.packets().next() {
                Some((stream, packet)) if stream.index() == self.stream_index => {
                    match self.decoder.send_packet(&packet) {
                        // A damaged packet costs a frame, not the whole clip.
                        Ok(()) | Err(ffmpeg_next::Error::InvalidData) => {}
                        Err(error) => return Err(error.into()),
                    }
                }
                Some(_) => {}
                None => {
                    self.decoder.send_eof()?;
                    self.eof_sent = true;
                }
            }
        }
    }

    /// Moves to the keyframe at or before `seconds`; the next `next_frame`
    /// continues from there.
    pub fn seek(&mut self, seconds: f64) -> Result<()> {
        let pts = self.start_pts + (seconds.max(0.0) / self.time_base) as i64;
        let target = rescale(pts, self.time_base);
        // `..target` is passed to FFmpeg as max_ts, inclusive: the keyframe at
        // or before the target.
        self.input.seek(target, ..target)?;
        self.decoder.flush();
        self.eof_sent = false;
        Ok(())
    }

    /// The frame showing at `seconds`: the last one that starts at or before it.
    pub fn frame_at(&mut self, seconds: f64) -> Result<Frame> {
        if !(0.0..=self.duration).contains(&seconds) {
            return Err(Error::OutOfRange {
                seconds,
                duration: self.duration,
            });
        }
        self.seek(seconds)?;

        // A millisecond of slack absorbs rounding between seconds and stream
        // ticks, so asking for a frame's own start time returns that frame.
        let slack = 0.001;
        let mut shown: Option<Frame> = None;
        while let Some(frame) = self.next_frame()? {
            if frame.seconds > seconds + slack {
                // Past the target: the previous frame was on screen, unless
                // the seek landed after it (a missing keyframe index).
                return Ok(shown.unwrap_or(frame));
            }
            shown = Some(frame);
        }
        shown.ok_or(Error::OutOfRange {
            seconds,
            duration: self.duration,
        })
    }

    fn convert(&mut self, decoded: &frame::Video) -> Result<Frame> {
        let source = (decoded.format(), decoded.width(), decoded.height());
        if self
            .scaler
            .as_ref()
            .is_none_or(|scaler| scaler.source != source)
        {
            let (width, height) = self
                .forced_size
                .unwrap_or_else(|| fit(source.1, source.2, self.max_size));
            let context = scaling::Context::get(
                source.0,
                source.1,
                source.2,
                self.format.to_ffmpeg(),
                width,
                height,
                scaling::Flags::BILINEAR,
            )?;
            self.scaler = Some(Scaler {
                source,
                context,
                width,
                height,
            });
        }
        let scaler = self.scaler.as_mut().expect("scaler was just set");

        let mut scaled = frame::Video::empty();
        scaler.context.run(decoded, &mut scaled)?;

        let row = scaler.width as usize * 4;
        let stride = scaled.stride(0);
        let plane = scaled.data(0);
        let mut data = Vec::with_capacity(row * scaler.height as usize);
        for y in 0..scaler.height as usize {
            data.extend_from_slice(&plane[y * stride..y * stride + row]);
        }

        let pts = decoded
            .timestamp()
            .or(decoded.pts())
            .unwrap_or(self.start_pts);
        Ok(Frame {
            width: scaler.width,
            height: scaler.height,
            format: self.format,
            seconds: ((pts - self.start_pts) as f64 * self.time_base).max(0.0),
            data,
        })
    }
}

/// `count` frames spread evenly over the video, each from the middle of
/// its slice so the first is not a black fade-in.
pub fn thumbnails(
    path: impl AsRef<Path>,
    count: usize,
    format: PixelFormat,
    max_size: Option<u32>,
) -> Result<Vec<Frame>> {
    let mut decoder = VideoDecoder::open(path, format, max_size)?;
    let duration = decoder.duration();
    (0..count)
        .map(|i| decoder.frame_at(duration * (i as f64 + 0.5) / count as f64))
        .collect()
}

/// Stream timestamp to `AV_TIME_BASE` units, which `Input::seek` takes.
fn rescale(pts: i64, time_base: f64) -> i64 {
    (pts as f64 * time_base * f64::from(AV_TIME_BASE)) as i64
}

/// Scales `width`×`height` down to fit in `max_size`, keeping the aspect
/// ratio and even sides (which YUV-based consumers need).
fn fit(width: u32, height: u32, max_size: Option<u32>) -> (u32, u32) {
    let Some(max) = max_size.filter(|&max| max > 0 && width.max(height) > max) else {
        return (width, height);
    };
    let scale = f64::from(max) / f64::from(width.max(height));
    let even = |side: u32| ((f64::from(side) * scale / 2.0).round() as u32 * 2).max(2);
    (even(width), even(height))
}

#[cfg(test)]
mod tests {
    use super::fit;

    #[test]
    fn fit_keeps_aspect_and_never_upscales() {
        assert_eq!(fit(1920, 1080, Some(640)), (640, 360));
        assert_eq!(fit(1080, 1920, Some(640)), (360, 640));
        assert_eq!(fit(320, 240, Some(640)), (320, 240));
        assert_eq!(fit(1920, 1080, None), (1920, 1080));
    }
}
