use std::path::Path;

use ffmpeg_next::{codec, ffi::AV_TIME_BASE, format, media};
use serde::Serialize;

use crate::{Error, Result};

/// What a media file holds, read from its container without decoding.
#[derive(Clone, Debug, Serialize)]
pub struct MediaInfo {
    /// Container format, e.g. `mov,mp4,m4a,3gp,3g2,mj2`.
    pub container: String,
    pub duration_seconds: f64,
    /// Overall bit rate in bits per second, when the container gives one.
    pub bit_rate: Option<i64>,
    pub video: Vec<VideoStream>,
    pub audio: Vec<AudioStream>,
    /// Subtitles, data and attachment streams.
    pub other: Vec<OtherStream>,
}

#[derive(Clone, Debug, Serialize)]
pub struct VideoStream {
    pub index: usize,
    pub codec: String,
    pub width: u32,
    pub height: u32,
    /// Average frame rate; `None` when the container does not say.
    pub frame_rate: Option<f64>,
    /// Frame count from the container header, which some formats leave out.
    pub frames: Option<i64>,
    pub pixel_format: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct AudioStream {
    pub index: usize,
    pub codec: String,
    pub sample_rate: u32,
    pub channels: u16,
    pub sample_format: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct OtherStream {
    pub index: usize,
    pub kind: String,
    pub codec: String,
}

impl MediaInfo {
    /// The stream `VideoDecoder` decodes: the one FFmpeg rates best.
    pub fn primary_video(&self) -> Option<&VideoStream> {
        self.video.first()
    }
}

pub fn probe(path: impl AsRef<Path>) -> Result<MediaInfo> {
    crate::init()?;
    let path = path.as_ref();
    let input = format::input(path).map_err(|source| Error::Open {
        path: path.to_owned(),
        source,
    })?;

    let best_video = input
        .streams()
        .best(media::Type::Video)
        .map(|stream| stream.index());
    let mut info = MediaInfo {
        container: input.format().name().to_owned(),
        duration_seconds: positive(input.duration())
            .map_or(0.0, |d| d as f64 / f64::from(AV_TIME_BASE)),
        bit_rate: positive(input.bit_rate()),
        video: Vec::new(),
        audio: Vec::new(),
        other: Vec::new(),
    };

    for stream in input.streams() {
        let parameters = stream.parameters();
        let codec_name = parameters.id().name().to_owned();
        let index = stream.index();
        match parameters.medium() {
            media::Type::Video => {
                let decoder = codec::Context::from_parameters(parameters)?
                    .decoder()
                    .video()?;
                let rate = stream.avg_frame_rate();
                let video = VideoStream {
                    index,
                    codec: codec_name,
                    width: decoder.width(),
                    height: decoder.height(),
                    frame_rate: (rate.numerator() > 0 && rate.denominator() > 0)
                        .then(|| f64::from(rate)),
                    frames: positive(stream.frames()),
                    pixel_format: format!("{:?}", decoder.format()).to_lowercase(),
                };
                // Best stream first, so `primary_video` matches the decoder.
                if Some(index) == best_video {
                    info.video.insert(0, video);
                } else {
                    info.video.push(video);
                }
            }
            media::Type::Audio => {
                let decoder = codec::Context::from_parameters(parameters)?
                    .decoder()
                    .audio()?;
                info.audio.push(AudioStream {
                    index,
                    codec: codec_name,
                    sample_rate: decoder.rate(),
                    channels: decoder.channels(),
                    sample_format: format!("{:?}", decoder.format()).to_lowercase(),
                });
            }
            kind => info.other.push(OtherStream {
                index,
                kind: format!("{kind:?}").to_lowercase(),
                codec: codec_name,
            }),
        }
    }

    // Some containers (raw streams, some WebMs) only know the duration per stream.
    if info.duration_seconds == 0.0 {
        info.duration_seconds = input
            .streams()
            .filter_map(|stream| {
                positive(stream.duration()).map(|d| d as f64 * f64::from(stream.time_base()))
            })
            .fold(0.0, f64::max);
    }

    Ok(info)
}

fn positive(value: i64) -> Option<i64> {
    (value > 0).then_some(value)
}
