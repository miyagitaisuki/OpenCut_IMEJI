//! Decodes a clip the `ffmpeg` command makes on the spot: 2 s at 25 fps,
//! keyframes every 10 frames, so seeks have to decode forward from one.
//! Skipped where no `ffmpeg` command is installed.

use std::path::PathBuf;
use std::process::Command;

use opencut_media::{Error, PixelFormat, VideoDecoder, probe, thumbnails};

fn clip() -> Option<PathBuf> {
    let path = std::env::temp_dir().join(format!("opencut-media-test-{}.mp4", std::process::id()));
    let made = Command::new("ffmpeg")
        .args([
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=25:duration=2",
        ])
        .args(["-c:v", "mpeg4", "-g", "10", "-bf", "0"])
        .arg(&path)
        .status()
        .is_ok_and(|status| status.success());
    if !made {
        eprintln!("skipping: no ffmpeg command to make a test clip");
    }
    made.then_some(path)
}

#[test]
fn probes_decodes_and_seeks() {
    let Some(path) = clip() else { return };

    let info = probe(&path).unwrap();
    let video = info.primary_video().unwrap();
    assert_eq!((video.width, video.height), (320, 240));
    assert_eq!(video.frame_rate, Some(25.0));
    assert!(
        (info.duration_seconds - 2.0).abs() < 0.05,
        "{}",
        info.duration_seconds
    );

    let mut decoder = VideoDecoder::open(&path, PixelFormat::Rgba, Some(160)).unwrap();
    assert_eq!(decoder.output_size(), (160, 120));

    // Every frame in order, each 1/25 s after the last.
    let mut count = 0;
    while let Some(frame) = decoder.next_frame().unwrap() {
        assert!(
            (frame.seconds - count as f64 / 25.0).abs() < 1e-6,
            "frame {count} at {}",
            frame.seconds
        );
        assert_eq!(frame.data.len(), 160 * 120 * 4);
        count += 1;
    }
    assert_eq!(count, 50);

    // Between keyframes, forwards and backwards: the frame on screen then.
    for (at, expected) in [
        (0.0, 0.0),
        (0.53, 0.52),
        (1.3, 1.28),
        (0.12, 0.12),
        (1.99, 1.96),
    ] {
        let frame = decoder.frame_at(at).unwrap();
        assert!(
            (frame.seconds - expected).abs() < 1e-6,
            "at {at}: got {}",
            frame.seconds
        );
    }
    assert!(matches!(
        decoder.frame_at(5.0),
        Err(Error::OutOfRange { .. })
    ));

    let thumbs = thumbnails(&path, 4, PixelFormat::Bgra, Some(64)).unwrap();
    assert_eq!(thumbs.len(), 4);
    assert!(
        thumbs
            .windows(2)
            .all(|pair| pair[0].seconds < pair[1].seconds)
    );
    let png = thumbs[0].png_bytes().unwrap();
    assert_eq!(&png[..8], b"\x89PNG\r\n\x1a\n");

    std::fs::remove_file(path).ok();
}

#[test]
fn reports_missing_files() {
    assert!(matches!(
        probe("/nonexistent/clip.mp4"),
        Err(Error::Open { .. })
    ));
}
