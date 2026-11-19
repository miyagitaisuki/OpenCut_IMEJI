//! The H.264 switch lives in one settings file; this is the only test that
//! touches it, so it can point `OPENCUT_CONFIG_DIR` at a temporary folder.

use opencut_media::{
    AudioSettings, Error, VideoCodec, VideoSettings, VideoWriter, h264_enabled, set_h264_enabled,
};

fn writer(codec: VideoCodec, path: &std::path::Path) -> opencut_media::Result<VideoWriter> {
    VideoWriter::create(
        path,
        &VideoSettings {
            width: 64,
            height: 64,
            fps: 10,
            codec,
            bit_rate: 200_000,
        },
        Some(&AudioSettings {
            sample_rate: 48_000,
            channels: 1,
            bit_rate: 64_000,
        }),
    )
}

#[test]
fn switch_is_on_by_default_and_gates_h264() {
    let dir = std::env::temp_dir().join(format!("opencut-h264-switch-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    // Safety: the only test in this binary, so no other thread reads the environment.
    unsafe { std::env::set_var("OPENCUT_CONFIG_DIR", &dir) };

    assert!(h264_enabled(), "no settings file means on");

    set_h264_enabled(false).unwrap();
    assert!(!h264_enabled());
    assert!(matches!(
        writer(VideoCodec::H264, &dir.join("a.mp4")),
        Err(Error::H264Disabled)
    ));
    // Auto falls back to MPEG-4 instead of failing.
    let auto = writer(VideoCodec::Auto, &dir.join("b.mp4")).unwrap();
    assert_eq!(auto.codec_name(), "mpeg4");

    set_h264_enabled(true).unwrap();
    assert!(h264_enabled());
    let _ = std::fs::remove_dir_all(&dir);
}
