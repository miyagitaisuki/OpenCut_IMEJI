use std::path::PathBuf;

use gpui::{div, prelude::*, App, Context, Entity, Window};

use crate::panels::{Browser, Inspector, Preview, Timeline};
use crate::theme::ActiveTheme;

// Panels are entities created once in `new`, not via `cx.new` inline in
// `render`, so each keeps its own state across renders instead of being
// torn down and rebuilt on every frame.
pub(crate) struct Shell {
    browser: Entity<Browser>,
    preview: Entity<Preview>,
    inspector: Entity<Inspector>,
    timeline: Entity<Timeline>,
}

impl Shell {
    /// `open` is a file to load into the preview straight away.
    pub(crate) fn new(open: Option<PathBuf>, cx: &mut App) -> Self {
        let preview = cx.new(Preview::new);
        if let Some(path) = open {
            preview.update(cx, |preview, cx| preview.open(path, cx));
        }
        Self {
            browser: cx.new(|_| Browser),
            preview,
            inspector: cx.new(|_| Inspector),
            timeline: cx.new(|_| Timeline),
        }
    }
}

impl Render for Shell {
    fn render(&mut self, window: &mut Window, _cx: &mut Context<Self>) -> impl IntoElement {
        let colors = window.theme().colors;

        div()
            .flex()
            .flex_col()
            .size_full()
            .bg(colors.background)
            .text_color(colors.foreground)
            .child(
                div()
                    .flex()
                    .h_2_3()
                    .border_b_1()
                    .border_color(colors.border)
                    .child(self.browser.clone())
                    .child(self.preview.clone())
                    .child(self.inspector.clone()),
            )
            .child(self.timeline.clone())
    }
}
