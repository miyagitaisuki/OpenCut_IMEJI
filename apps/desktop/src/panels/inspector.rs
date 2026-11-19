use gpui::{div, prelude::*, Context, Window};

use crate::notices::{FFMPEG_NOTICE, OPENH264_BODY, OPENH264_TITLE};
use crate::theme::ActiveTheme;

pub(crate) struct Inspector;

impl Render for Inspector {
    fn render(&mut self, window: &mut Window, _cx: &mut Context<Self>) -> impl IntoElement {
        let colors = window.theme().colors;

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
                    .child(div().font_weight(gpui::FontWeight::SEMIBOLD).child(OPENH264_TITLE))
                    .child(div().child(OPENH264_BODY))
                    .child(div().child(FFMPEG_NOTICE)),
            )
    }
}
