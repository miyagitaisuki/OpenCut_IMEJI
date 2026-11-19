//! Renders a small lesson made on the spot (two slides, a WAV, subtitles,
//! a question marker) and checks the video that comes out.

use std::path::Path;

use opencut_media::{Frame, PixelFormat, VideoDecoder, decode_audio, probe};
use opencut_project::{AudioClip, Canvas, Cue, Fit, Marker, Project, Visual, VisualKind};
use opencut_render::{RenderOptions, render};

fn solid_png(path: &Path, width: u32, height: u32, rgb: [u8; 3]) {
    Frame {
        width,
        height,
        format: PixelFormat::Rgba,
        seconds: 0.0,
        data: [rgb[0], rgb[1], rgb[2], 255].repeat((width * height) as usize),
    }
    .save_png(path)
    .unwrap();
}

/// A 440 Hz sine, mono 16-bit PCM.
fn sine_wav(path: &Path, seconds: f64) {
    let rate = 22_050u32;
    let samples: Vec<i16> = (0..(seconds * f64::from(rate)) as u32)
        .map(|i| {
            ((i as f64 * 440.0 * std::f64::consts::TAU / f64::from(rate)).sin() * 12_000.0) as i16
        })
        .collect();
    let data_len = samples.len() as u32 * 2;
    let mut wav = Vec::new();
    wav.extend_from_slice(b"RIFF");
    wav.extend_from_slice(&(36 + data_len).to_le_bytes());
    wav.extend_from_slice(b"WAVEfmt ");
    wav.extend_from_slice(&16u32.to_le_bytes());
    wav.extend_from_slice(&1u16.to_le_bytes()); // PCM
    wav.extend_from_slice(&1u16.to_le_bytes()); // mono
    wav.extend_from_slice(&rate.to_le_bytes());
    wav.extend_from_slice(&(rate * 2).to_le_bytes());
    wav.extend_from_slice(&2u16.to_le_bytes());
    wav.extend_from_slice(&16u16.to_le_bytes());
    wav.extend_from_slice(b"data");
    wav.extend_from_slice(&data_len.to_le_bytes());
    for sample in samples {
        wav.extend_from_slice(&sample.to_le_bytes());
    }
    std::fs::write(path, wav).unwrap();
}

fn image(path: &str, start: f64, end: f64) -> Visual {
    Visual {
        kind: VisualKind::Image,
        path: Some(path.into()),
        color: None,
        start,
        end,
        source_start: 0.0,
        fit: Fit::Contain,
    }
}

#[test]
fn renders_slides_audio_and_sidecars() {
    let dir = std::env::temp_dir().join(format!("opencut-render-test-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    solid_png(&dir.join("red.png"), 400, 300, [220, 30, 30]);
    solid_png(&dir.join("blue.png"), 300, 300, [30, 30, 220]);
    sine_wav(&dir.join("voice.wav"), 2.0);

    let project = Project {
        title: "test".into(),
        canvas: Canvas {
            width: 320,
            height: 240,
            fps: 10,
            background: "#00ff00".into(),
        },
        visuals: vec![image("red.png", 0.0, 1.0), image("blue.png", 1.0, 2.0)],
        audio: vec![AudioClip {
            path: "voice.wav".into(),
            start: 0.0,
            source_start: 0.0,
            duration: None,
            gain_db: -3.0,
        }],
        subtitles: vec![Cue {
            start: 0.2,
            end: 1.5,
            text: "こんにちは".into(),
            role: Some("1".into()),
            translation: Some("Xin chào".into()),
        }],
        markers: vec![Marker {
            time: 1.8,
            kind: "question".into(),
            label: "Câu 1".into(),
            reference: Some("qbank:42".into()),
        }],
        ..Project::default()
    };

    let output = dir.join("lesson.mp4");
    let mut seen = Vec::new();
    let report = render(&project, &dir, &output, &RenderOptions::default(), |p| {
        seen.push(p)
    })
    .unwrap();
    assert_eq!(report.frames, 20);
    assert_eq!(seen.last(), Some(&1.0));
    assert_eq!(report.sidecars.len(), 3);

    let info = probe(&output).unwrap();
    assert!(
        (info.duration_seconds - 2.0).abs() < 0.15,
        "{}",
        info.duration_seconds
    );
    assert_eq!(
        info.primary_video().map(|v| (v.width, v.height)),
        Some((320, 240))
    );
    assert_eq!(info.audio.len(), 1);

    // The red slide fills the 4:3 canvas; the square blue one is
    // pillarboxed in the green background.
    let mut decoder = VideoDecoder::open(&output, PixelFormat::Rgba, None).unwrap();
    let pixel = |frame: &Frame, x: u32, y: u32| {
        let i = ((y * frame.width + x) * 4) as usize;
        [frame.data[i], frame.data[i + 1], frame.data[i + 2]]
    };
    let near = |a: [u8; 3], b: [u8; 3]| a.iter().zip(b).all(|(x, y)| x.abs_diff(y) < 40);
    let first = decoder.frame_at(0.5).unwrap();
    assert!(
        near(pixel(&first, 160, 120), [220, 30, 30]),
        "{:?}",
        pixel(&first, 160, 120)
    );
    assert!(
        near(pixel(&first, 4, 120), [220, 30, 30]),
        "{:?}",
        pixel(&first, 4, 120)
    );
    let second = decoder.frame_at(1.5).unwrap();
    assert!(
        near(pixel(&second, 4, 120), [0, 255, 0]),
        "{:?}",
        pixel(&second, 4, 120)
    );
    assert!(
        near(pixel(&second, 160, 120), [30, 30, 220]),
        "{:?}",
        pixel(&second, 160, 120)
    );

    // Every frame survives muxing, the last one included.
    let mut decoder = VideoDecoder::open(&output, PixelFormat::Rgba, None).unwrap();
    let mut count = 0;
    while decoder.next_frame().unwrap().is_some() {
        count += 1;
    }
    assert_eq!(count, 20);

    // Brought to the project's -16 LUFS, and it measures so in the file.
    let loudness = report.loudness.as_ref().expect("the project has audio");
    assert!((loudness.output_lufs + 16.0).abs() < 0.2, "{loudness:?}");
    let audio = decode_audio(&output, 48_000, 2).unwrap();
    let mut meter = ebur128::EbuR128::new(2, 48_000, ebur128::Mode::I).unwrap();
    meter.add_frames_f32(&audio.samples).unwrap();
    let measured = meter.loudness_global().unwrap();
    assert!(
        (measured + 16.0).abs() < 1.0,
        "rendered file measures {measured} LUFS"
    );

    let vtt = std::fs::read_to_string(dir.join("lesson.vtt")).unwrap();
    assert!(
        vtt.contains("00:00:00.200 --> 00:00:01.500\n<v 1>こんにちは\n<c.tr>Xin chào</c>"),
        "{vtt}"
    );
    let markers = std::fs::read_to_string(dir.join("lesson.markers.json")).unwrap();
    assert!(markers.contains("qbank:42"));

    std::fs::remove_dir_all(dir).ok();
}

#[test]
fn refuses_invalid_projects() {
    let project = Project::default();
    let error = render(
        &project,
        Path::new("."),
        Path::new("never.mp4"),
        &RenderOptions::default(),
        |_| {},
    );
    assert!(matches!(error, Err(opencut_render::Error::Invalid(_))));
}
