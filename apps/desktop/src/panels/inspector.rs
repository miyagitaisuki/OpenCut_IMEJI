use gpui::{Context, Window, div, prelude::*};

use crate::components::{Button, ButtonSize, ButtonVariant};
use crate::notices::{FFMPEG_NOTICE, OPENH264_BODY, OPENH264_TITLE};
use crate::theme::ActiveTheme;

pub(crate) struct Inspector {
    /// The shared H.264 switch (`opencut h264 on|off` sets the same one).
    h264: bool,
    /// Why the last change could not be saved.
    error: Option<String>,
}

impl Inspector {
    pub(crate) fn new() -> Self {
        Self {
            h264: opencut_media::h264_enabled(),
            error: None,
        }
    }

    fn toggle_h264(&mut self, cx: &mut Context<Self>) {
        match opencut_media::set_h264_enabled(!self.h264) {
            Ok(()) => {
                self.h264 = !self.h264;
                self.error = None;
            }
            Err(error) => self.error = Some(error.to_string()),
        }
        cx.notify();
    }
}

impl Render for Inspector {
    fn render(&mut self, window: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let colors = window.theme().colors;
        let h264 = self.h264;

        div()
            .flex()
            .flex_col()
            .w_1_4()
            .h_full()
            .border_l_1()
            .border_color(colors.border)
            .bg(colors.card)
            .text_color(colors.card_foreground)
            .child(
                div()
                    .flex()
                    .flex_1()
                    .items_center()
                    .justify_center()
                    .child("Inspector"),
            )
            // H.264 comes from Cisco's OpenH264 module, which Cisco asks apps
            // to let the user turn off; off, exports use MPEG-4 instead.
            .child(
                div()
                    .flex()
                    .flex_col()
                    .gap_1()
                    .p_2()
                    .border_t_1()
                    .border_color(colors.border)
                    .text_xs()
                    .child(
                        Button::new(
                            "h264-switch",
                            if h264 {
                                "H.264 export: On"
                            } else {
                                "H.264 export: Off"
                            },
                        )
                        .variant(if h264 {
                            ButtonVariant::Default
                        } else {
                            ButtonVariant::Outline
                        })
                        .size(ButtonSize::Small)
                        .on_click(cx.listener(|this, _, _, cx| this.toggle_h264(cx))),
                    )
                    .child(div().child(if h264 {
                        "Exports play everywhere."
                    } else {
                        "Exports use MPEG-4: browsers and most LMSs will not play them."
                    }))
                    .children(
                        self.error
                            .clone()
                            .map(|error| div().child(format!("Could not save: {error}"))),
                    ),
            )
            // Third-party notices: Cisco asks that apps using its OpenH264
            // binary show its attribution and licence terms.
            .child(
                div()
                    .flex()
                    .flex_col()
                    .gap_1()
                    .p_2()
                    .border_t_1()
                    .border_color(colors.border)
                    .text_xs()
                    .child(
                        div()
                            .font_weight(gpui::FontWeight::SEMIBOLD)
                            .child(OPENH264_TITLE),
                    )
                    .child(div().child(OPENH264_BODY))
                    .child(div().child(FFMPEG_NOTICE)),
            )
    }
}
