use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use gpui::{
    Context, ExternalPaths, FontWeight, ObjectFit, PathPromptOptions, RenderImage, SharedString,
    Task, Window, div, img, prelude::*, px, relative,
};
use opencut_media::{Frame, PixelFormat, VideoDecoder};

use crate::components::{Button, ButtonSize, ButtonVariant, Label};
use crate::theme::ActiveTheme;

/// Frames are decoded no larger than this; the preview never needs more.
const MAX_PREVIEW_SIZE: u32 = 1920;
/// Behind schedule by more than this, playback drops frames to catch up.
const LATE: f64 = 0.1;

/// The loaded clip. The decoder sits behind a mutex because decoding runs
/// on the background executor while the panel stays on the main thread.
struct Clip {
    name: SharedString,
    decoder: Arc<Mutex<VideoDecoder>>,
    duration: f64,
    frame_rate: f64,
}

pub(crate) struct Preview {
    clip: Option<Clip>,
    image: Option<Arc<RenderImage>>,
    /// Replaced images, released from the GPU atlas on the next render
    /// (dropping the `Arc` alone would leak their textures).
    retired: Vec<Arc<RenderImage>>,
    position: f64,
    status: Option<SharedString>,
    playback: Option<Task<()>>,
    /// Bumped by every seek, so a slow decode never overwrites a newer one.
    generation: u64,
    _pending: Option<Task<()>>,
}

impl Preview {
    pub(crate) fn new(_cx: &mut Context<Self>) -> Self {
        Self {
            clip: None,
            image: None,
            retired: Vec::new(),
            position: 0.0,
            status: None,
            playback: None,
            generation: 0,
            _pending: None,
        }
    }

    pub(crate) fn open(&mut self, path: PathBuf, cx: &mut Context<Self>) {
        self.pause(cx);
        self.generation += 1;
        let generation = self.generation;
        self.status = Some(format!("Opening {}…", file_name(&path)).into());
        cx.notify();

        let load = cx.background_spawn(async move {
            let mut decoder = VideoDecoder::open(&path, PixelFormat::Bgra, Some(MAX_PREVIEW_SIZE))?;
            let first = decoder.frame_at(0.0)?;
            anyhow::Ok((path, decoder, first))
        });
        self._pending = Some(cx.spawn(async move |this, cx| {
            let result = load.await;
            this.update(cx, |this, cx| {
                if this.generation != generation {
                    return;
                }
                match result {
                    Ok((path, decoder, first)) => {
                        this.clip = Some(Clip {
                            name: file_name(&path).into(),
                            duration: decoder.duration(),
                            frame_rate: decoder.frame_rate().unwrap_or(30.0),
                            decoder: Arc::new(Mutex::new(decoder)),
                        });
                        this.status = None;
                        this.show(first, cx);
                    }
                    Err(error) => {
                        this.status = Some(format!("{error:#}").into());
                        cx.notify();
                    }
                }
            })
            .ok();
        }));
    }

    fn prompt_open(&mut self, cx: &mut Context<Self>) {
        let paths = cx.prompt_for_paths(PathPromptOptions {
            files: true,
            directories: false,
            multiple: false,
            prompt: Some("Open".into()),
        });
        cx.spawn(async move |this, cx| {
            if let Ok(Ok(Some(mut paths))) = paths.await
                && let Some(path) = paths.pop()
            {
                this.update(cx, |this, cx| this.open(path, cx)).ok();
            }
        })
        .detach();
    }

    /// Shows the frame at `seconds`, clamped to the clip.
    fn seek(&mut self, seconds: f64, cx: &mut Context<Self>) {
        if self.clip.is_none() {
            return;
        }
        self.pause(cx);
        let Some(clip) = &self.clip else { return };
        // The last frame starts one frame before the end.
        let seconds = seconds.clamp(0.0, (clip.duration - 1.0 / clip.frame_rate).max(0.0));
        self.position = seconds;
        self.generation += 1;
        let generation = self.generation;
        let decoder = clip.decoder.clone();
        cx.notify();

        let decode = cx.background_spawn(async move {
            decoder.lock().expect("decoder poisoned").frame_at(seconds)
        });
        self._pending = Some(cx.spawn(async move |this, cx| {
            let result = decode.await;
            this.update(cx, |this, cx| {
                if this.generation != generation {
                    return;
                }
                match result {
                    Ok(frame) => this.show(frame, cx),
                    Err(error) => {
                        this.status = Some(error.to_string().into());
                        cx.notify();
                    }
                }
            })
            .ok();
        }));
    }

    fn step(&mut self, frames: f64, cx: &mut Context<Self>) {
        if let Some(clip) = &self.clip {
            // Aim at the middle of the target frame, clear of rounding.
            let target = self.position + (frames + 0.5) / clip.frame_rate;
            self.seek(target, cx);
        }
    }

    fn toggle_playback(&mut self, cx: &mut Context<Self>) {
        if self.playback.is_some() {
            self.pause(cx);
        } else {
            self.play(cx);
        }
    }

    fn pause(&mut self, cx: &mut Context<Self>) {
        if self.playback.take().is_some() {
            cx.notify();
        }
    }

    fn play(&mut self, cx: &mut Context<Self>) {
        let Some(clip) = &self.clip else { return };
        let frame_interval = 1.0 / clip.frame_rate;
        // At the end, play from the start again.
        let from = if self.position + frame_interval >= clip.duration {
            0.0
        } else {
            self.position
        };
        let decoder = clip.decoder.clone();
        self.generation += 1;
        let generation = self.generation;

        self.playback = Some(cx.spawn(async move |this, cx| {
            let seek = {
                let decoder = decoder.clone();
                cx.background_spawn(
                    async move { decoder.lock().expect("decoder poisoned").seek(from) },
                )
            };
            if seek.await.is_err() {
                return;
            }
            let started = Instant::now();
            loop {
                let next = {
                    let decoder = decoder.clone();
                    cx.background_spawn(async move {
                        decoder.lock().expect("decoder poisoned").next_frame()
                    })
                };
                let frame = match next.await {
                    Ok(Some(frame)) => frame,
                    Ok(None) | Err(_) => break,
                };
                // The seek lands on a keyframe: decode up to where play started.
                if frame.seconds + 0.001 < from {
                    continue;
                }
                let due = frame.seconds - from;
                let elapsed = started.elapsed().as_secs_f64();
                if due > elapsed {
                    cx.background_executor()
                        .timer(Duration::from_secs_f64(due - elapsed))
                        .await;
                } else if elapsed - due > LATE {
                    continue;
                }
                let shown = this.update(cx, |this, cx| {
                    if this.generation != generation {
                        return false;
                    }
                    this.position = frame.seconds;
                    this.show(frame, cx);
                    true
                });
                if !matches!(shown, Ok(true)) {
                    return;
                }
            }
            this.update(cx, |this, cx| {
                if this.generation == generation {
                    this.playback = None;
                    cx.notify();
                }
            })
            .ok();
        }));
        cx.notify();
    }

    fn show(&mut self, frame: Frame, cx: &mut Context<Self>) {
        self.position = frame.seconds;
        let image = to_render_image(frame);
        if let Some(old) = self.image.replace(image) {
            self.retired.push(old);
        }
        cx.notify();
    }

    fn render_controls(&self, cx: &mut Context<Self>) -> impl IntoElement {
        let loaded = self.clip.is_some();
        let duration = self.clip.as_ref().map_or(0.0, |clip| clip.duration);
        let playing = self.playback.is_some();
        let control = |id: &'static str, label: &'static str| {
            Button::new(id, label)
                .variant(ButtonVariant::Ghost)
                .size(ButtonSize::Small)
                .disabled(!loaded)
        };

        div()
            .flex()
            .items_center()
            .gap_1()
            .px_2()
            .py_1()
            .child(
                control("preview-start", "⏮")
                    .on_click(cx.listener(|this, _, _, cx| this.seek(0.0, cx))),
            )
            .child(
                control("preview-back-second", "−1s")
                    .on_click(cx.listener(|this, _, _, cx| this.seek(this.position - 1.0, cx))),
            )
            .child(
                control("preview-back-frame", "◀")
                    .on_click(cx.listener(|this, _, _, cx| this.step(-1.0, cx))),
            )
            .child(
                control("preview-play", if playing { "Pause" } else { "Play" })
                    .variant(ButtonVariant::Secondary)
                    .on_click(cx.listener(|this, _, _, cx| this.toggle_playback(cx))),
            )
            .child(
                control("preview-forward-frame", "▶")
                    .on_click(cx.listener(|this, _, _, cx| this.step(1.0, cx))),
            )
            .child(
                control("preview-forward-second", "+1s")
                    .on_click(cx.listener(|this, _, _, cx| this.seek(this.position + 1.0, cx))),
            )
            .child(
                div().ml_2().child(
                    Label::new(format!(
                        "{} / {}",
                        timecode(self.position),
                        timecode(duration)
                    ))
                    .muted(),
                ),
            )
    }
}

impl Render for Preview {
    fn render(&mut self, window: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        for image in self.retired.drain(..) {
            window.drop_image(image).ok();
        }
        let colors = window.theme().colors;
        let progress = self.clip.as_ref().map_or(0.0, |clip| {
            (self.position / clip.duration.max(f64::EPSILON)).clamp(0.0, 1.0)
        });

        let screen = div()
            .flex()
            .flex_1()
            .min_h_0()
            .items_center()
            .justify_center()
            .bg(gpui::black())
            .child(match (&self.image, &self.status) {
                (_, Some(status)) if self.clip.is_none() || self.image.is_none() => div()
                    .text_sm()
                    .text_color(colors.muted_foreground)
                    .child(status.clone())
                    .into_any_element(),
                (Some(image), _) => img(image.clone())
                    .size_full()
                    .object_fit(ObjectFit::Contain)
                    .into_any_element(),
                _ => div()
                    .text_sm()
                    .text_color(colors.muted_foreground)
                    .child("Drop a video here or click Open")
                    .into_any_element(),
            });

        div()
            .id("preview")
            .flex()
            .flex_col()
            .w_1_2()
            .h_full()
            .bg(colors.background)
            .on_drop(cx.listener(|this, paths: &ExternalPaths, _, cx| {
                if let Some(path) = paths.paths().first() {
                    this.open(path.clone(), cx);
                }
            }))
            .child(
                div()
                    .flex()
                    .items_center()
                    .justify_between()
                    .px_2()
                    .py_1()
                    .border_b_1()
                    .border_color(colors.border)
                    .child(
                        div().text_xs().font_weight(FontWeight::MEDIUM).child(
                            self.clip
                                .as_ref()
                                .map_or(SharedString::from("Preview"), |clip| clip.name.clone()),
                        ),
                    )
                    .child(
                        Button::new("preview-open", "Open…")
                            .variant(ButtonVariant::Outline)
                            .size(ButtonSize::XSmall)
                            .on_click(cx.listener(|this, _, _, cx| this.prompt_open(cx))),
                    ),
            )
            .child(screen)
            .child(
                div().h(px(3.)).w_full().bg(colors.muted).child(
                    div()
                        .h_full()
                        .w(relative(progress as f32))
                        .bg(colors.primary),
                ),
            )
            .when_some(
                self.status.clone().filter(|_| self.clip.is_some()),
                |panel, status| {
                    panel.child(
                        div()
                            .px_2()
                            .text_xs()
                            .text_color(colors.destructive)
                            .child(status),
                    )
                },
            )
            .child(self.render_controls(cx))
    }
}

fn to_render_image(frame: Frame) -> Arc<RenderImage> {
    debug_assert_eq!(frame.format, PixelFormat::Bgra, "GPUI images are BGRA");
    let buffer = image::RgbaImage::from_raw(frame.width, frame.height, frame.data)
        .expect("decoder returns width * height * 4 bytes");
    Arc::new(RenderImage::new(vec![image::Frame::new(buffer)]))
}

fn file_name(path: &Path) -> String {
    path.file_name().map_or_else(
        || path.display().to_string(),
        |name| name.to_string_lossy().into_owned(),
    )
}

/// `mm:ss.cc`, or `h:mm:ss.cc` past an hour.
fn timecode(seconds: f64) -> String {
    let centis = (seconds.max(0.0) * 100.0).round() as u64;
    let (hours, minutes, secs, cs) = (
        centis / 360_000,
        centis / 6_000 % 60,
        centis / 100 % 60,
        centis % 100,
    );
    if hours > 0 {
        format!("{hours}:{minutes:02}:{secs:02}.{cs:02}")
    } else {
        format!("{minutes:02}:{secs:02}.{cs:02}")
    }
}

#[cfg(test)]
mod tests {
    use super::timecode;

    #[test]
    fn timecode_formats() {
        assert_eq!(timecode(0.0), "00:00.00");
        assert_eq!(timecode(65.5), "01:05.50");
        assert_eq!(timecode(3725.25), "1:02:05.25");
    }
}
