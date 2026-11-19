use std::path::PathBuf;

pub type Result<T, E = Error> = std::result::Result<T, E>;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("could not open {path}: {source}")]
    Open {
        path: PathBuf,
        source: ffmpeg_next::Error,
    },
    #[error("{0} has no video stream")]
    NoVideo(PathBuf),
    #[error("{0} has no audio stream")]
    NoAudio(PathBuf),
    #[error("no {0} encoder in this FFmpeg build")]
    NoEncoder(&'static str),
    #[error("H.264 is turned off (`opencut h264 on`, or the switch in the app's Inspector)")]
    H264Disabled,
    #[error("no frame at {seconds:.3}s (the video ends at {duration:.3}s)")]
    OutOfRange { seconds: f64, duration: f64 },
    #[error("ffmpeg: {0}")]
    Ffmpeg(#[from] ffmpeg_next::Error),
    #[error("png: {0}")]
    Png(#[from] png::EncodingError),
    #[error(transparent)]
    Io(#[from] std::io::Error),
}
