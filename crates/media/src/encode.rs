use std::path::Path;

use ffmpeg_next::{
    ChannelLayout, Packet, Rational, codec, encoder, format, frame, threading,
    software::scaling,
    util::format::sample::{Sample, Type as SampleType},
};
use serde::Serialize;

use crate::{Error, Frame, PixelFormat, Result};

/// Which video encoder to use.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum VideoCodec {
    /// H.264 if this FFmpeg has an encoder for it, MPEG-4 Part 2 otherwise.
    #[default]
    Auto,
    /// H.264 (OpenH264): plays everywhere, browsers and LMSs included.
    H264,
    /// MPEG-4 Part 2: always available in the LGPL build, but browsers do not play it.
    Mpeg4,
}

#[derive(Clone, Debug)]
pub struct VideoSettings {
    pub width: u32,
    pub height: u32,
    pub fps: u32,
    pub codec: VideoCodec,
    /// Bits per second.
    pub bit_rate: usize,
}

#[derive(Clone, Debug)]
pub struct AudioSettings {
    pub sample_rate: u32,
    pub channels: u16,
    pub bit_rate: usize,
}

/// Writes an MP4 (or any container FFmpeg infers from the extension) from
/// packed RGBA frames and interleaved `f32` audio.
pub struct VideoWriter {
    output: format::context::Output,
    video: encoder::Video,
    video_stream: usize,
    /// Encoder ticks (1/fps) and the stream's, which the muxer may change.
    encoder_time_base: Rational,
    video_time_base: Rational,
    scaler: scaling::Context,
    width: u32,
    height: u32,
    next_pts: i64,
    audio: Option<AudioTrack>,
    codec_name: String,
}

struct AudioTrack {
    encoder: encoder::Audio,
    stream: usize,
    time_base: Rational,
    channels: u16,
    frame_size: usize,
    pending: Vec<f32>,
    next_pts: i64,
}

// The scaler holds a raw `SwsContext`; the writer owns it exclusively.
unsafe impl Send for VideoWriter {}

impl VideoWriter {
    pub fn create(
        path: impl AsRef<Path>,
        video: &VideoSettings,
        audio: Option<&AudioSettings>,
    ) -> Result<Self> {
        crate::init()?;
        let path = path.as_ref();
        let mut output = format::output(path).map_err(|source| Error::Open {
            path: path.to_owned(),
            source,
        })?;
        let global_header = output
            .format()
            .flags()
            .contains(format::Flags::GLOBAL_HEADER);

        let time_base = Rational::new(1, video.fps as i32);
        let (codec, video_encoder) = open_video_encoder(video, time_base, global_header)?;
        let codec_name = codec.name().to_owned();
        let mut stream = output.add_stream(codec)?;
        let video_stream = stream.index();
        stream.set_parameters(&video_encoder);
        stream.set_time_base(time_base);

        let audio = match audio {
            Some(settings) => Some(add_audio(&mut output, settings, global_header)?),
            None => None,
        };

        output.write_header()?;
        let video_time_base = output.stream(video_stream).expect("just added").time_base();

        let scaler = scaling::Context::get(
            format::Pixel::RGBA,
            video.width,
            video.height,
            format::Pixel::YUV420P,
            video.width,
            video.height,
            scaling::Flags::BILINEAR,
        )?;

        let mut writer = Self {
            output,
            video: video_encoder,
            video_stream,
            encoder_time_base: time_base,
            video_time_base,
            scaler,
            width: video.width,
            height: video.height,
            next_pts: 0,
            audio,
            codec_name,
        };
        if let Some(track) = writer.audio.as_mut() {
            track.time_base = writer
                .output
                .stream(track.stream)
                .expect("just added")
                .time_base();
        }
        Ok(writer)
    }

    /// Encoder actually used, e.g. `libopenh264` or `mpeg4`.
    pub fn codec_name(&self) -> &str {
        &self.codec_name
    }

    /// Appends one frame; it shows for 1/fps seconds.
    pub fn write_video(&mut self, frame: &Frame) -> Result<()> {
        assert_eq!(
            (frame.width, frame.height),
            (self.width, self.height),
            "frame size must match the video"
        );
        assert_eq!(frame.format, PixelFormat::Rgba, "frames to encode are RGBA");
        let mut rgba = frame::Video::new(format::Pixel::RGBA, self.width, self.height);
        let stride = rgba.stride(0);
        let row = self.width as usize * 4;
        let plane = rgba.data_mut(0);
        for y in 0..self.height as usize {
            plane[y * stride..y * stride + row]
                .copy_from_slice(&frame.data[y * row..(y + 1) * row]);
        }
        let mut yuv = frame::Video::empty();
        self.scaler.run(&rgba, &mut yuv)?;
        yuv.set_pts(Some(self.next_pts));
        self.next_pts += 1;
        self.video.send_frame(&yuv)?;
        self.drain_video()
    }

    /// Appends interleaved samples, in the channel count the writer was made with.
    pub fn write_audio(&mut self, samples: &[f32]) -> Result<()> {
        let Some(track) = self.audio.as_mut() else {
            return Ok(());
        };
        track.pending.extend_from_slice(samples);
        let chunk = track.frame_size * usize::from(track.channels);
        while track.pending.len() >= chunk {
            let rest = track.pending.split_off(chunk);
            let full = std::mem::replace(&mut track.pending, rest);
            send_audio(track, &full)?;
            drain_audio(track, &mut self.output)?;
        }
        Ok(())
    }

    /// Flushes both encoders and writes the trailer.
    pub fn finish(mut self) -> Result<()> {
        if let Some(track) = self.audio.as_mut() {
            if !track.pending.is_empty() {
                let rest = std::mem::take(&mut track.pending);
                send_audio(track, &rest)?;
            }
            track.encoder.send_eof()?;
            drain_audio(track, &mut self.output)?;
        }
        self.video.send_eof()?;
        self.drain_video()?;
        self.output.write_trailer()?;
        Ok(())
    }

    fn drain_video(&mut self) -> Result<()> {
        let mut packet = Packet::empty();
        while self.video.receive_packet(&mut packet).is_ok() {
            packet.set_stream(self.video_stream);
            // Every frame lasts one tick. Without it the muxer ends the
            // track at the last frame's start and the edit list drops it.
            packet.set_duration(1);
            packet.rescale_ts(self.encoder_time_base, self.video_time_base);
            packet.write_interleaved(&mut self.output)?;
        }
        Ok(())
    }
}

/// Opens the first candidate encoder that starts. A hardware H.264 encoder
/// (Media Foundation) comes before OpenH264, so a machine whose GPU refuses
/// the session still gets software H.264.
fn open_video_encoder(
    video: &VideoSettings,
    time_base: Rational,
    global_header: bool,
) -> Result<(ffmpeg_next::Codec, encoder::Video)> {
    let candidates = find_video_codecs(video.codec)?;
    let threads = std::thread::available_parallelism().map_or(1, |n| n.get());
    let mut last_error = None;
    for codec in candidates {
        let mut context = codec::Context::new_with_codec(codec).encoder().video()?;
        context.set_width(video.width);
        context.set_height(video.height);
        context.set_format(format::Pixel::YUV420P);
        context.set_time_base(time_base);
        context.set_frame_rate(Some(Rational::new(video.fps as i32, 1)));
        context.set_bit_rate(video.bit_rate);
        context.set_gop(video.fps * 2);
        // Software encoders split each frame into slices, one per thread;
        // encoders without slice threading ignore the count.
        context.set_threading(threading::Config {
            kind: threading::Type::Slice,
            count: threads,
        });
        if global_header {
            context.set_flags(codec::Flags::GLOBAL_HEADER);
        }
        match context.open_as(codec) {
            Ok(opened) => return Ok((codec, opened)),
            Err(error) => last_error = Some(error),
        }
    }
    Err(last_error
        .expect("find_video_codecs returns at least one codec")
        .into())
}

/// Encoders to try for `choice`, in order.
fn find_video_codecs(choice: VideoCodec) -> Result<Vec<ffmpeg_next::Codec>> {
    // Cisco's OpenH264 is the software H.264 encoder: with the user's switch
    // off, Auto falls back to MPEG-4 and asking for H.264 outright is an error.
    let h264_allowed = crate::h264_enabled();
    if choice == VideoCodec::H264 && !h264_allowed {
        return Err(Error::H264Disabled);
    }
    let hardware = || encoder::find_by_name("h264_mf");
    let openh264 = || encoder::find_by_name("libopenh264").or_else(|| encoder::find(codec::Id::H264));
    let mpeg4 = || encoder::find(codec::Id::MPEG4);
    let h264 = || [hardware(), openh264()].into_iter().flatten().collect::<Vec<_>>();
    let found: Vec<_> = match choice {
        VideoCodec::Auto if h264_allowed => {
            let mut list = h264();
            list.extend(mpeg4());
            list
        }
        VideoCodec::Auto => mpeg4().into_iter().collect(),
        VideoCodec::H264 => h264(),
        VideoCodec::Mpeg4 => mpeg4().into_iter().collect(),
    };
    if found.is_empty() {
        return Err(Error::NoEncoder(match choice {
            VideoCodec::H264 => "h264 (this FFmpeg build has no H.264 encoder: it needs OpenH264)",
            _ => "mpeg4",
        }));
    }
    Ok(found)
}

fn add_audio(
    output: &mut format::context::Output,
    settings: &AudioSettings,
    global_header: bool,
) -> Result<AudioTrack> {
    let codec = encoder::find(codec::Id::AAC).ok_or(Error::NoEncoder("aac"))?;
    let mut stream = output.add_stream(codec)?;
    let index = stream.index();
    let mut context = codec::Context::new_with_codec(codec).encoder().audio()?;
    let time_base = Rational::new(1, settings.sample_rate as i32);
    context.set_rate(settings.sample_rate as i32);
    context.set_channel_layout(ChannelLayout::default(i32::from(settings.channels)));
    context.set_format(Sample::F32(SampleType::Planar));
    context.set_bit_rate(settings.bit_rate);
    context.set_time_base(time_base);
    if global_header {
        context.set_flags(codec::Flags::GLOBAL_HEADER);
    }
    let encoder = context.open_as(codec)?;
    stream.set_parameters(&encoder);
    stream.set_time_base(time_base);
    let frame_size = (encoder.frame_size() as usize).max(1024);
    Ok(AudioTrack {
        encoder,
        stream: index,
        time_base,
        channels: settings.channels,
        frame_size,
        pending: Vec::new(),
        next_pts: 0,
    })
}

fn send_audio(track: &mut AudioTrack, interleaved: &[f32]) -> Result<()> {
    let channels = usize::from(track.channels);
    let count = interleaved.len() / channels;
    let mut frame = frame::Audio::new(
        Sample::F32(SampleType::Planar),
        count,
        ChannelLayout::default(i32::from(track.channels)),
    );
    frame.set_rate(track.encoder.rate());
    for channel in 0..channels {
        let plane = frame.plane_mut::<f32>(channel);
        for (i, sample) in plane.iter_mut().take(count).enumerate() {
            *sample = interleaved[i * channels + channel];
        }
    }
    frame.set_pts(Some(track.next_pts));
    track.next_pts += count as i64;
    track.encoder.send_frame(&frame)?;
    Ok(())
}

fn drain_audio(track: &mut AudioTrack, output: &mut format::context::Output) -> Result<()> {
    let mut packet = Packet::empty();
    while track.encoder.receive_packet(&mut packet).is_ok() {
        packet.set_stream(track.stream);
        packet.rescale_ts(
            Rational::new(1, track.encoder.rate() as i32),
            track.time_base,
        );
        packet.write_interleaved(output)?;
    }
    Ok(())
}
