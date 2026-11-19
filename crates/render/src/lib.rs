//! Renders an OpenCut project to a video: visuals composited on the
//! canvas, every audio clip mixed, encoded with FFmpeg.
//!
//! Beside the video it writes what a publisher needs and a video file
//! cannot carry well: `<name>.vtt` and `<name>.srt` subtitles (soft, so
//! learners can turn them off) and `<name>.markers.json` (scenes,
//! chapters and the questions to stop on).

mod caption;

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use opencut_media::{
    AudioSettings, Frame, PixelFormat, VideoCodec, VideoDecoder, VideoSettings, VideoWriter,
    decode_audio,
};
use opencut_project::{
    Fit, Project, Visual, VisualKind, parse_color, resolve, write_srt, write_vtt,
};
use serde::Serialize;

const SAMPLE_RATE: u32 = 48_000;
const CHANNELS: u16 = 2;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("the project cannot be rendered:\n- {}", .0.join("\n- "))]
    Invalid(Vec<String>),
    #[error("{path}: {source}")]
    Media {
        path: PathBuf,
        source: opencut_media::Error,
    },
    #[error("writing {path}: {source}")]
    Output {
        path: PathBuf,
        source: opencut_media::Error,
    },
    #[error("{0}")]
    Font(String),
    #[error("{path}: {message}")]
    Image { path: PathBuf, message: String },
    #[error("{path}: {source}")]
    Io {
        path: PathBuf,
        source: std::io::Error,
    },
}

pub type Result<T, E = Error> = std::result::Result<T, E>;

#[derive(Clone, Debug)]
pub struct RenderOptions {
    pub codec: VideoCodec,
    /// Video bits per second; scaled to the canvas when absent.
    pub bit_rate: Option<usize>,
    /// Write `.vtt`, `.srt` and `.markers.json` beside the video.
    pub sidecars: bool,
    /// Draw the subtitles into the picture (furigana and translation
    /// included), for players that show no soft subtitles or no ruby.
    pub burn_subtitles: bool,
    /// Fonts for burned-in subtitles, tried in order for each character;
    /// the system's Japanese fonts when empty.
    pub fonts: Vec<PathBuf>,
}

impl Default for RenderOptions {
    fn default() -> Self {
        Self {
            codec: VideoCodec::Auto,
            bit_rate: None,
            sidecars: true,
            burn_subtitles: false,
            fonts: Vec::new(),
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct RenderReport {
    pub output: PathBuf,
    pub duration_seconds: f64,
    pub frames: u64,
    pub width: u32,
    pub height: u32,
    pub fps: u32,
    /// The encoder used, e.g. `libopenh264` or `mpeg4`.
    pub video_codec: String,
    pub sidecars: Vec<PathBuf>,
    /// What loudness normalization did, when the project asks for it.
    pub loudness: Option<LoudnessReport>,
    pub warnings: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct LoudnessReport {
    pub measured_lufs: f64,
    pub target_lufs: f64,
    pub gain_db: f64,
    /// Below the target when the true-peak ceiling limited the gain.
    pub output_lufs: f64,
    pub true_peak_dbtp: f64,
}

/// Highest true peak allowed after normalization (EBU R128 / podcast specs).
const TRUE_PEAK_CEILING_DBTP: f64 = -1.0;

/// Renders `project` (its relative paths resolved against `base`) to `output`.
/// `progress` is called with the fraction done, about once a second of video.
pub fn render(
    project: &Project,
    base: &Path,
    output: &Path,
    options: &RenderOptions,
    mut progress: impl FnMut(f64),
) -> Result<RenderReport> {
    let problems = project.problems(base);
    if !problems.is_empty() {
        return Err(Error::Invalid(problems));
    }
    let canvas = &project.canvas;
    let (width, height, fps) = (canvas.width, canvas.height, canvas.fps);
    let duration = project.duration();
    let frames = (duration * f64::from(fps)).ceil().max(1.0) as u64;
    let mut warnings = Vec::new();
    let mut mix = mix_audio(project, base, frames as f64 / f64::from(fps))?;
    let loudness = match (mix.as_mut(), project.loudness_lufs) {
        (Some(mix), Some(target)) => normalize(mix, target, &mut warnings),
        _ => None,
    };
    if let Some(mix) = mix.as_mut() {
        for sample in mix.iter_mut() {
            *sample = sample.clamp(-1.0, 1.0);
        }
    }

    let bit_rate = options.bit_rate.unwrap_or_else(|| {
        (f64::from(width * height) * f64::from(fps) * 0.1).clamp(1e6, 2e7) as usize
    });
    let mut writer = VideoWriter::create(
        output,
        &VideoSettings {
            width,
            height,
            fps,
            codec: options.codec,
            bit_rate,
        },
        mix.as_ref()
            .map(|_| AudioSettings {
                sample_rate: SAMPLE_RATE,
                channels: CHANNELS,
                bit_rate: 160_000,
            })
            .as_ref(),
    )
    .map_err(|source| Error::Output {
        path: output.to_owned(),
        source,
    })?;
    let video_codec = writer.codec_name().to_owned();
    if video_codec == "mpeg4" {
        warnings.push(
            "encoded as MPEG-4 Part 2 because this FFmpeg has no H.264 encoder: it plays in VLC, not in browsers or Moodle"
                .into(),
        );
    }

    let background = parse_color(&canvas.background).expect("checked by problems()");
    let mut layers = Layers::new(base, width, height);
    let mut picture = Frame {
        width,
        height,
        format: PixelFormat::Rgba,
        seconds: 0.0,
        data: vec![0; (width * height * 4) as usize],
    };
    let failed = |source| Error::Output {
        path: output.to_owned(),
        source,
    };

    let fonts = if options.burn_subtitles {
        Some(caption::Fonts::load(&options.fonts).map_err(Error::Font)?)
    } else {
        None
    };
    // Each cue is laid out once, the first time it shows.
    let mut captions: HashMap<usize, Option<Frame>> = HashMap::new();
    let bottom_margin = (f64::from(height) * 0.06) as i64;

    for index in 0..frames {
        let time = index as f64 / f64::from(fps);
        fill(&mut picture.data, background);
        for (layer, visual) in project.visuals.iter().enumerate() {
            if time >= visual.start && time < visual.end {
                layers.draw(layer, visual, time, &mut picture)?;
            } else if time >= visual.end {
                layers.release(layer);
            }
        }
        if let Some(fonts) = &fonts
            && let Some(cue_index) = project
                .subtitles
                .iter()
                .position(|c| time >= c.start && time < c.end)
        {
            let drawn = captions.entry(cue_index).or_insert_with(|| {
                caption::render_cue(&project.subtitles[cue_index], fonts, width, height)
            });
            if let Some(drawn) = drawn {
                let x = (i64::from(width) - i64::from(drawn.width)) / 2;
                let y = i64::from(height) - i64::from(drawn.height) - bottom_margin;
                blit(&mut picture, drawn, x, y);
            }
        }
        picture.seconds = time;
        writer.write_video(&picture).map_err(failed)?;

        if let Some(mix) = &mix {
            let from = sample_index(index, fps);
            let to = sample_index(index + 1, fps);
            writer.write_audio(&mix[from * 2..to * 2]).map_err(failed)?;
        }
        if index % u64::from(fps) == 0 {
            progress(index as f64 / frames as f64);
        }
    }
    writer.finish().map_err(failed)?;
    progress(1.0);

    let sidecars = if options.sidecars {
        write_sidecars(project, output, duration)?
    } else {
        Vec::new()
    };
    warnings.extend(layers.warnings);

    Ok(RenderReport {
        output: output.to_owned(),
        duration_seconds: frames as f64 / f64::from(fps),
        frames,
        width,
        height,
        fps,
        video_codec,
        sidecars,
        loudness,
        warnings,
    })
}

/// First audio sample (per channel) of video frame `index`.
fn sample_index(index: u64, fps: u32) -> usize {
    (index * u64::from(SAMPLE_RATE) / u64::from(fps)) as usize
}

/// Every audio clip mixed into one interleaved stereo buffer as long as
/// the video, or `None` when the project has no audio.
fn mix_audio(project: &Project, base: &Path, seconds: f64) -> Result<Option<Vec<f32>>> {
    if project.audio.is_empty() {
        return Ok(None);
    }
    let length = (seconds * f64::from(SAMPLE_RATE)).ceil() as usize + SAMPLE_RATE as usize;
    let mut mix = vec![0.0f32; length * 2];
    for clip in &project.audio {
        let path = resolve(base, &clip.path);
        let buffer = decode_audio(&path, SAMPLE_RATE, CHANNELS).map_err(|source| Error::Media {
            path: path.clone(),
            source,
        })?;
        let gain = 10f32.powf(clip.gain_db as f32 / 20.0);
        let skip = (clip.source_start * f64::from(SAMPLE_RATE)) as usize;
        let take = clip
            .duration
            .map_or(usize::MAX, |d| (d * f64::from(SAMPLE_RATE)) as usize);
        let at = (clip.start * f64::from(SAMPLE_RATE)) as usize;
        for (i, frame) in buffer
            .samples
            .chunks_exact(2)
            .skip(skip)
            .take(take)
            .enumerate()
        {
            let Some(out) = mix.get_mut((at + i) * 2..(at + i) * 2 + 2) else {
                break;
            };
            out[0] += frame[0] * gain;
            out[1] += frame[1] * gain;
        }
    }
    // Not clamped yet: normalization may bring loud overlaps back in range.
    Ok(Some(mix))
}

/// Measures the mix (EBU R128, integrated) and applies one gain that brings
/// it to `target` LUFS, or as close as the -1 dBTP ceiling allows.
fn normalize(mix: &mut [f32], target: f64, warnings: &mut Vec<String>) -> Option<LoudnessReport> {
    use ebur128::{EbuR128, Mode};
    let mut meter =
        EbuR128::new(u32::from(CHANNELS), SAMPLE_RATE, Mode::I | Mode::TRUE_PEAK).ok()?;
    meter.add_frames_f32(mix).ok()?;
    let measured = meter.loudness_global().ok()?;
    if !measured.is_finite() {
        // Silence: nothing to bring up.
        return None;
    }
    let peak = (0..u32::from(CHANNELS))
        .filter_map(|channel| meter.true_peak(channel).ok())
        .fold(0.0f64, f64::max);
    let peak_db = 20.0 * peak.max(1e-9).log10();

    let wanted = target - measured;
    let gain_db = wanted.min(TRUE_PEAK_CEILING_DBTP - peak_db);
    if gain_db < wanted - 0.1 {
        warnings.push(format!(
            "loudness reached {:.1} LUFS, not {target:.1}: more gain would clip (peaks at {peak_db:.1} dBTP)",
            measured + gain_db
        ));
    }
    let gain = 10f64.powf(gain_db / 20.0) as f32;
    for sample in mix.iter_mut() {
        *sample = (*sample * gain).clamp(-1.0, 1.0);
    }
    Some(LoudnessReport {
        measured_lufs: round1(measured),
        target_lufs: target,
        gain_db: round1(gain_db),
        output_lufs: round1(measured + gain_db),
        true_peak_dbtp: round1(peak_db + gain_db),
    })
}

fn round1(value: f64) -> f64 {
    (value * 10.0).round() / 10.0
}

/// Decoded pictures for the visuals: images once, at their size on the
/// canvas; videos as an open decoder that follows the timeline.
struct Layers<'a> {
    base: &'a Path,
    width: u32,
    height: u32,
    images: HashMap<usize, Placed>,
    videos: HashMap<usize, VideoLayer>,
    warnings: Vec<String>,
}

struct Placed {
    frame: Frame,
    x: i64,
    y: i64,
}

struct VideoLayer {
    decoder: VideoDecoder,
    x: i64,
    y: i64,
    current: Option<Frame>,
    next: Option<Frame>,
}

impl<'a> Layers<'a> {
    fn new(base: &'a Path, width: u32, height: u32) -> Self {
        Self {
            base,
            width,
            height,
            images: HashMap::new(),
            videos: HashMap::new(),
            warnings: Vec::new(),
        }
    }

    fn release(&mut self, layer: usize) {
        self.images.remove(&layer);
        self.videos.remove(&layer);
    }

    fn draw(
        &mut self,
        layer: usize,
        visual: &Visual,
        time: f64,
        picture: &mut Frame,
    ) -> Result<()> {
        match visual.kind {
            VisualKind::Color => {
                fill(
                    &mut picture.data,
                    parse_color(visual.color.as_deref().unwrap_or_default()).unwrap_or([0; 3]),
                );
            }
            VisualKind::Image => {
                if !self.images.contains_key(&layer) {
                    let placed = self.load_image(visual)?;
                    self.images.insert(layer, placed);
                }
                let placed = &self.images[&layer];
                blit(picture, &placed.frame, placed.x, placed.y);
            }
            VisualKind::Video => {
                if !self.videos.contains_key(&layer) {
                    let video = self.open_video(visual, time)?;
                    self.videos.insert(layer, video);
                }
                let video = self.videos.get_mut(&layer).expect("inserted above");
                let source_time = visual.source_start + (time - visual.start);
                while video
                    .next
                    .as_ref()
                    .is_some_and(|next| next.seconds <= source_time + 1e-6)
                {
                    video.current = video.next.take();
                    video.next = video.decoder.next_frame().unwrap_or(None);
                }
                if let Some(frame) = &video.current {
                    blit(picture, frame, video.x, video.y);
                }
            }
        }
        Ok(())
    }

    fn load_image(&mut self, visual: &Visual) -> Result<Placed> {
        let path = resolve(
            self.base,
            visual.path.as_deref().expect("checked by problems()"),
        );
        let decoded = image::open(&path)
            .map_err(|error| Error::Image {
                path: path.clone(),
                message: error.to_string(),
            })?
            .into_rgba8();
        let (w, h, x, y) = place(decoded.dimensions(), (self.width, self.height), visual.fit);
        let resized = if decoded.dimensions() == (w, h) {
            decoded
        } else {
            image::imageops::resize(&decoded, w, h, image::imageops::FilterType::CatmullRom)
        };
        let frame = Frame {
            width: w,
            height: h,
            format: PixelFormat::Rgba,
            seconds: 0.0,
            data: resized.into_raw(),
        };
        Ok(Placed { frame, x, y })
    }

    fn open_video(&mut self, visual: &Visual, time: f64) -> Result<VideoLayer> {
        let path = resolve(
            self.base,
            visual.path.as_deref().expect("checked by problems()"),
        );
        let media = |source| Error::Media {
            path: path.clone(),
            source,
        };
        let mut decoder = VideoDecoder::open(&path, PixelFormat::Rgba, None).map_err(media)?;
        let (w, h, x, y) = place(decoder.source_size(), (self.width, self.height), visual.fit);
        decoder.set_output_size(w, h);
        let start = visual.source_start + (time - visual.start);
        if start > decoder.duration() {
            self.warnings.push(format!(
                "{} is shorter than its place on the timeline",
                path.display()
            ));
        }
        decoder.seek(start).map_err(media)?;
        // Decode up to the start: the seek lands on the keyframe before it.
        let mut current = None;
        let mut next = decoder.next_frame().map_err(media)?;
        while next
            .as_ref()
            .is_some_and(|frame| frame.seconds <= start + 1e-6)
        {
            current = next;
            next = decoder.next_frame().map_err(media)?;
        }
        Ok(VideoLayer {
            decoder,
            x,
            y,
            current: current.or_else(|| next.take()),
            next,
        })
    }
}

/// Size and position of a `source`-sized picture on the canvas.
fn place(source: (u32, u32), canvas: (u32, u32), fit: Fit) -> (u32, u32, i64, i64) {
    let (sw, sh) = (f64::from(source.0.max(1)), f64::from(source.1.max(1)));
    let (cw, ch) = (f64::from(canvas.0), f64::from(canvas.1));
    let scale = match fit {
        Fit::Contain => (cw / sw).min(ch / sh),
        Fit::Cover => (cw / sw).max(ch / sh),
    };
    let (w, h) = (
        (sw * scale).round().max(1.0) as u32,
        (sh * scale).round().max(1.0) as u32,
    );
    (
        w,
        h,
        (i64::from(canvas.0) - i64::from(w)) / 2,
        (i64::from(canvas.1) - i64::from(h)) / 2,
    )
}

fn fill(data: &mut [u8], [r, g, b]: [u8; 3]) {
    for pixel in data.chunks_exact_mut(4) {
        pixel.copy_from_slice(&[r, g, b, 255]);
    }
}

/// Draws `source` onto `target` at (`x`, `y`), alpha-blended, clipped to the target.
fn blit(target: &mut Frame, source: &Frame, x: i64, y: i64) {
    let (tw, th) = (i64::from(target.width), i64::from(target.height));
    let (sw, sh) = (i64::from(source.width), i64::from(source.height));
    let (x0, y0) = (x.max(0), y.max(0));
    let (x1, y1) = ((x + sw).min(tw), (y + sh).min(th));
    if x0 >= x1 || y0 >= y1 {
        return;
    }
    for ty in y0..y1 {
        let sy = ty - y;
        let target_row =
            &mut target.data[((ty * tw + x0) * 4) as usize..((ty * tw + x1) * 4) as usize];
        let source_row =
            &source.data[((sy * sw + (x0 - x)) * 4) as usize..((sy * sw + (x1 - x)) * 4) as usize];
        for (t, s) in target_row
            .chunks_exact_mut(4)
            .zip(source_row.chunks_exact(4))
        {
            let alpha = u32::from(s[3]);
            if alpha == 255 {
                t[..3].copy_from_slice(&s[..3]);
            } else if alpha > 0 {
                for c in 0..3 {
                    t[c] = ((u32::from(s[c]) * alpha + u32::from(t[c]) * (255 - alpha) + 127) / 255)
                        as u8;
                }
            }
        }
    }
}

#[derive(Serialize)]
struct MarkersFile<'a> {
    title: &'a str,
    duration_seconds: f64,
    markers: &'a [opencut_project::Marker],
}

fn write_sidecars(project: &Project, output: &Path, duration: f64) -> Result<Vec<PathBuf>> {
    let mut written = Vec::new();
    let mut write = |extension: &str, contents: String| -> Result<()> {
        let path = output.with_extension(extension);
        std::fs::write(&path, contents).map_err(|source| Error::Io {
            path: path.clone(),
            source,
        })?;
        written.push(path);
        Ok(())
    };
    if !project.subtitles.is_empty() {
        write("vtt", write_vtt(&project.subtitles))?;
        write("srt", write_srt(&project.subtitles))?;
    }
    let markers = MarkersFile {
        title: &project.title,
        duration_seconds: duration,
        markers: &project.markers,
    };
    write(
        "markers.json",
        serde_json::to_string_pretty(&markers).expect("serializes") + "\n",
    )?;
    Ok(written)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn places_contain_and_cover() {
        assert_eq!(
            place((1000, 1000), (1920, 1080), Fit::Contain),
            (1080, 1080, 420, 0)
        );
        assert_eq!(
            place((1000, 1000), (1920, 1080), Fit::Cover),
            (1920, 1920, 0, -420)
        );
        assert_eq!(
            place((3840, 2160), (1920, 1080), Fit::Contain),
            (1920, 1080, 0, 0)
        );
    }

    #[test]
    fn blits_with_alpha_and_clipping() {
        let mut target = Frame {
            width: 4,
            height: 2,
            format: PixelFormat::Rgba,
            seconds: 0.0,
            data: vec![0; 32],
        };
        fill(&mut target.data, [0, 0, 0]);
        let source = Frame {
            width: 2,
            height: 2,
            format: PixelFormat::Rgba,
            seconds: 0.0,
            data: [
                [255, 255, 255, 255],
                [255, 0, 0, 128],
                [255, 255, 255, 255],
                [0, 0, 0, 0],
            ]
            .concat(),
        };
        blit(&mut target, &source, 3, 0);
        assert_eq!(&target.data[12..16], &[255, 255, 255, 255]);
        blit(&mut target, &source, 0, 0);
        assert_eq!(&target.data[4..8], &[128, 0, 0, 255]);
        assert_eq!(&target.data[20..24], &[0, 0, 0, 255]);
    }
}
