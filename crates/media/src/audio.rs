use std::path::Path;

use ffmpeg_next::{
    ChannelLayout, codec, format, frame, media,
    software::resampling,
    util::format::sample::{Sample, Type as SampleType},
};

use crate::{Error, Result};

/// Decoded audio, interleaved `f32` samples (`[L, R, L, R, …]` for stereo).
#[derive(Clone, Debug)]
pub struct AudioBuffer {
    pub sample_rate: u32,
    pub channels: u16,
    pub samples: Vec<f32>,
}

impl AudioBuffer {
    pub fn duration(&self) -> f64 {
        self.frames() as f64 / f64::from(self.sample_rate)
    }

    /// Samples per channel.
    pub fn frames(&self) -> usize {
        self.samples.len() / usize::from(self.channels.max(1))
    }
}

/// Decodes the best audio stream of `path`, resampled to `sample_rate` and
/// mixed to `channels` (1 or 2), whatever the source is.
pub fn decode_audio(
    path: impl AsRef<Path>,
    sample_rate: u32,
    channels: u16,
) -> Result<AudioBuffer> {
    crate::init()?;
    let path = path.as_ref();
    let mut input = format::input(path).map_err(|source| Error::Open {
        path: path.to_owned(),
        source,
    })?;
    let stream = input
        .streams()
        .best(media::Type::Audio)
        .ok_or_else(|| Error::NoAudio(path.to_owned()))?;
    let stream_index = stream.index();
    let mut decoder = codec::Context::from_parameters(stream.parameters())?
        .decoder()
        .audio()?;

    let target_layout = ChannelLayout::default(i32::from(channels));
    let target_format = Sample::F32(SampleType::Packed);
    let mut resampler: Option<resampling::Context> = None;
    let mut samples = Vec::new();

    let drain = |decoder: &mut ffmpeg_next::decoder::Audio,
                 resampler: &mut Option<resampling::Context>,
                 samples: &mut Vec<f32>|
     -> Result<()> {
        let mut decoded = frame::Audio::empty();
        while decoder.receive_frame(&mut decoded).is_ok() {
            // Sources often leave the layout unspecified ("1 channel"), which
            // the resampler then sees as changed from frame to frame. Use the
            // standard layout for the channel count, always.
            decoded.set_channel_layout(ChannelLayout::default(i32::from(decoded.channels())));
            if resampler.is_none() {
                *resampler = Some(resampling::Context::get(
                    decoded.format(),
                    decoded.channel_layout(),
                    decoded.rate(),
                    target_format,
                    target_layout,
                    sample_rate,
                )?);
            }
            // Room for every resampled sample, so none pile up inside the resampler.
            let capacity =
                decoded.samples() * sample_rate as usize / decoded.rate().max(1) as usize + 256;
            let mut converted = frame::Audio::new(target_format, capacity, target_layout);
            resampler
                .as_mut()
                .expect("set above")
                .run(&decoded, &mut converted)?;
            push_packed(&converted, channels, samples);
        }
        Ok(())
    };

    for (stream, packet) in input.packets() {
        if stream.index() != stream_index {
            continue;
        }
        match decoder.send_packet(&packet) {
            Ok(()) | Err(ffmpeg_next::Error::InvalidData) => {}
            Err(error) => return Err(error.into()),
        }
        drain(&mut decoder, &mut resampler, &mut samples)?;
    }
    decoder.send_eof()?;
    drain(&mut decoder, &mut resampler, &mut samples)?;

    // What the resampler still holds (its filter delay).
    if let Some(resampler) = resampler.as_mut() {
        loop {
            // A frame of the output's own layout: an empty one reads as "output changed".
            let mut converted = frame::Audio::new(target_format, 4096, target_layout);
            let delay = resampler.flush(&mut converted)?;
            push_packed(&converted, channels, &mut samples);
            if delay.is_none() || converted.samples() == 0 {
                break;
            }
        }
    }

    Ok(AudioBuffer {
        sample_rate,
        channels,
        samples,
    })
}

fn push_packed(frame: &frame::Audio, channels: u16, out: &mut Vec<f32>) {
    let count = frame.samples() * usize::from(channels);
    if count == 0 {
        return;
    }
    let bytes = &frame.data(0)[..count * 4];
    out.extend(
        bytes
            .chunks_exact(4)
            .map(|b| f32::from_ne_bytes([b[0], b[1], b[2], b[3]])),
    );
}
