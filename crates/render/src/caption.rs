//! Subtitles drawn into the picture ("burned in"), for places that show
//! no soft subtitles or no ruby, like YouTube: Japanese with furigana
//! above its kanji, the translation on the lines under it, on a dark box
//! near the bottom.

use std::path::{Path, PathBuf};

use ab_glyph::{Font, FontVec, GlyphId, PxScale, ScaleFont, point};
use opencut_media::{Frame, PixelFormat};
use opencut_project::{Cue, ruby};

const TEXT: [u8; 3] = [255, 255, 255];
const TRANSLATION: [u8; 3] = [255, 229, 138];
const BOX: [u8; 4] = [10, 14, 30, 190];

/// A font chain: each character comes from the first font that has it.
pub struct Fonts {
    fonts: Vec<FontVec>,
}

impl Fonts {
    /// Loads `paths`, or the usual Japanese fonts of this system when empty.
    pub fn load(paths: &[PathBuf]) -> Result<Self, String> {
        let candidates: Vec<PathBuf> = if paths.is_empty() {
            system_fonts()
        } else {
            paths.to_vec()
        };
        let fonts: Vec<FontVec> = candidates
            .iter()
            .filter_map(|path| std::fs::read(path).ok())
            .filter_map(|data| FontVec::try_from_vec_and_index(data, 0).ok())
            .collect();
        if fonts.is_empty() {
            return Err(format!(
                "no font for burned-in subtitles: tried {}; pass one with --font",
                candidates
                    .iter()
                    .map(|p| p.display().to_string())
                    .collect::<Vec<_>>()
                    .join(", ")
            ));
        }
        Ok(Self { fonts })
    }

    fn glyph(&self, c: char) -> (&FontVec, GlyphId) {
        self.fonts
            .iter()
            .map(|font| (font, font.glyph_id(c)))
            .find(|(_, id)| id.0 != 0)
            .unwrap_or((&self.fonts[0], self.fonts[0].glyph_id(c)))
    }

    fn advance(&self, c: char, size: f32) -> f32 {
        let (font, id) = self.glyph(c);
        font.as_scaled(PxScale::from(size)).h_advance(id)
    }

    fn width(&self, text: &str, size: f32) -> f32 {
        text.chars().map(|c| self.advance(c, size)).sum()
    }

    /// Draws `text` with its baseline at (`x`, `y`).
    fn draw(&self, frame: &mut Frame, text: &str, size: f32, mut x: f32, y: f32, color: [u8; 3]) {
        for c in text.chars() {
            let (font, id) = self.glyph(c);
            let scaled = font.as_scaled(PxScale::from(size));
            let glyph = id.with_scale_and_position(PxScale::from(size), point(x, y));
            if let Some(outlined) = font.outline_glyph(glyph) {
                let bounds = outlined.px_bounds();
                outlined.draw(|gx, gy, coverage| {
                    let px = bounds.min.x as i64 + i64::from(gx);
                    let py = bounds.min.y as i64 + i64::from(gy);
                    blend(frame, px, py, color, coverage);
                });
            }
            x += scaled.h_advance(id);
        }
    }
}

/// Where Windows, macOS and Linux keep fonts with Japanese and Vietnamese.
fn system_fonts() -> Vec<PathBuf> {
    let windows =
        std::env::var_os("WINDIR").map_or_else(|| PathBuf::from(r"C:\Windows"), PathBuf::from);
    let mut list: Vec<PathBuf> = [
        "YuGothM.ttc",
        "YuGothR.ttc",
        "meiryo.ttc",
        "msgothic.ttc",
        "segoeui.ttf",
        "arial.ttf",
    ]
    .iter()
    .map(|name| windows.join("Fonts").join(name))
    .collect();
    list.extend(
        [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        .map(PathBuf::from),
    );
    list.retain(|path| Path::new(path).is_file());
    list
}

/// One piece of a Japanese line: a character, or kanji with their reading,
/// which never split across lines.
struct Unit {
    base: String,
    reading: Option<String>,
}

fn units(text: &str) -> Vec<Unit> {
    let mut out: Vec<Unit> = Vec::new();
    for segment in ruby::segments(text) {
        match segment {
            ruby::Segment::Ruby { base, reading } => out.push(Unit {
                base: base.to_owned(),
                reading: Some(reading.to_owned()),
            }),
            ruby::Segment::Text(text) => {
                for c in text.chars() {
                    // Closing punctuation never starts a line (kinsoku).
                    if "、。，．！？）」』】ー…ぁぃぅぇぉっゃゅょ".contains(c)
                        && let Some(last) = out.last_mut()
                        && last.reading.is_none()
                    {
                        last.base.push(c);
                        continue;
                    }
                    out.push(Unit {
                        base: c.to_string(),
                        reading: None,
                    });
                }
            }
        }
    }
    out
}

/// Lays a cue out and draws it on a transparent picture no wider than
/// `area_width` (the video's width, less any corner a mascot takes). Returns
/// `None` for a cue with no text.
pub fn render_cue(cue: &Cue, fonts: &Fonts, area_width: u32, video_height: u32) -> Option<Frame> {
    let main = (video_height as f32 * 0.052).max(14.0);
    let small = main * 0.5;
    let tr_size = main * 0.68;
    let pad = main * 0.55;
    let max_width = area_width as f32 * 0.86 - pad * 2.0;

    // Japanese lines, broken between units.
    let mut lines: Vec<Vec<Unit>> = vec![Vec::new()];
    let mut line_width = 0.0;
    for unit in cue.text.lines().flat_map(|line| {
        let mut list = units(line);
        list.push(Unit {
            base: "\n".into(),
            reading: None,
        });
        list
    }) {
        if unit.base == "\n" {
            if !lines.last().is_some_and(Vec::is_empty) {
                lines.push(Vec::new());
                line_width = 0.0;
            }
            continue;
        }
        let w = unit_width(&unit, fonts, main, small);
        if line_width + w > max_width && !lines.last().is_some_and(Vec::is_empty) {
            lines.push(Vec::new());
            line_width = 0.0;
        }
        line_width += w;
        lines.last_mut().expect("never empty").push(unit);
    }
    lines.retain(|line| !line.is_empty());

    let translation = cue
        .translation
        .as_deref()
        .map(str::trim)
        .filter(|t| !t.is_empty());
    let tr_lines = translation
        .map(|t| wrap_words(&ruby::to_plain(t), fonts, tr_size, max_width))
        .unwrap_or_default();
    if lines.is_empty() && tr_lines.is_empty() {
        return None;
    }

    let has_ruby = lines.iter().flatten().any(|u| u.reading.is_some());
    let jp_line = main * 1.3 + if has_ruby { small * 1.05 } else { 0.0 };
    let tr_line = tr_size * 1.4;
    let content_width = lines
        .iter()
        .map(|line| {
            line.iter()
                .map(|u| unit_width(u, fonts, main, small))
                .sum::<f32>()
        })
        .chain(tr_lines.iter().map(|l| fonts.width(l, tr_size)))
        .fold(0.0, f32::max);
    let gap = if tr_lines.is_empty() || lines.is_empty() {
        0.0
    } else {
        main * 0.2
    };
    let width = (content_width + pad * 2.0).ceil() as u32;
    let height = (lines.len() as f32 * jp_line + gap + tr_lines.len() as f32 * tr_line + pad * 1.6)
        .ceil() as u32;

    let mut frame = Frame {
        width,
        height,
        format: PixelFormat::Rgba,
        seconds: 0.0,
        data: vec![0; (width * height * 4) as usize],
    };
    rounded_box(&mut frame, main * 0.45, BOX);

    let mut y = pad * 0.8;
    for line in &lines {
        let line_w: f32 = line.iter().map(|u| unit_width(u, fonts, main, small)).sum();
        let mut x = (width as f32 - line_w) / 2.0;
        let baseline = y + jp_line - main * 0.32;
        for unit in line {
            let unit_w = unit_width(unit, fonts, main, small);
            let base_w = fonts.width(&unit.base, main);
            fonts.draw(
                &mut frame,
                &unit.base,
                main,
                x + (unit_w - base_w) / 2.0,
                baseline,
                TEXT,
            );
            if let Some(reading) = &unit.reading {
                let reading_w = fonts.width(reading, small);
                let ruby_y = baseline - main * 0.9;
                fonts.draw(
                    &mut frame,
                    reading,
                    small,
                    x + (unit_w - reading_w) / 2.0,
                    ruby_y,
                    TEXT,
                );
            }
            x += unit_w;
        }
        y += jp_line;
    }
    y += gap;
    for line in &tr_lines {
        let w = fonts.width(line, tr_size);
        fonts.draw(
            &mut frame,
            line,
            tr_size,
            (width as f32 - w) / 2.0,
            y + tr_size * 1.05,
            TRANSLATION,
        );
        y += tr_line;
    }
    Some(frame)
}

fn unit_width(unit: &Unit, fonts: &Fonts, main: f32, small: f32) -> f32 {
    let base = fonts.width(&unit.base, main);
    match &unit.reading {
        Some(reading) => base.max(fonts.width(reading, small)),
        None => base,
    }
}

/// Breaks at spaces; a single word wider than the line gets a line of its own.
fn wrap_words(text: &str, fonts: &Fonts, size: f32, max_width: f32) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    for paragraph in text.lines() {
        let mut current = String::new();
        for word in paragraph.split_whitespace() {
            let candidate = if current.is_empty() {
                word.to_owned()
            } else {
                format!("{current} {word}")
            };
            if fonts.width(&candidate, size) > max_width && !current.is_empty() {
                lines.push(std::mem::replace(&mut current, word.to_owned()));
            } else {
                current = candidate;
            }
        }
        if !current.is_empty() {
            lines.push(current);
        }
    }
    lines
}

fn blend(frame: &mut Frame, x: i64, y: i64, [r, g, b]: [u8; 3], coverage: f32) {
    if x < 0
        || y < 0
        || x >= i64::from(frame.width)
        || y >= i64::from(frame.height)
        || coverage <= 0.0
    {
        return;
    }
    let i = ((y * i64::from(frame.width) + x) * 4) as usize;
    let a = coverage.min(1.0);
    let px = &mut frame.data[i..i + 4];
    // Over a premultiplied-looking box: blend colour, keep the higher alpha.
    for (c, v) in px[..3].iter_mut().zip([r, g, b]) {
        *c = (f32::from(*c) * (1.0 - a) + f32::from(v) * a).round() as u8;
    }
    px[3] = px[3].max((a * 255.0) as u8);
}

fn rounded_box(frame: &mut Frame, radius: f32, [r, g, b, a]: [u8; 4]) {
    let (w, h) = (frame.width as f32, frame.height as f32);
    for y in 0..frame.height {
        for x in 0..frame.width {
            let (fx, fy) = (x as f32 + 0.5, y as f32 + 0.5);
            // Distance outside the rounded rectangle, for an antialiased edge.
            let dx = (radius - fx).max(fx - (w - radius)).max(0.0);
            let dy = (radius - fy).max(fy - (h - radius)).max(0.0);
            let outside = (dx * dx + dy * dy).sqrt() - radius;
            let cover = (0.5 - outside).clamp(0.0, 1.0);
            if cover > 0.0 {
                let i = ((y * frame.width + x) * 4) as usize;
                frame.data[i..i + 4].copy_from_slice(&[r, g, b, (f32::from(a) * cover) as u8]);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn readings_stay_with_their_kanji_and_punctuation_with_its_word() {
        let list = units("駅{えき}はどこ？");
        let pieces: Vec<_> = list
            .iter()
            .map(|u| (u.base.as_str(), u.reading.as_deref()))
            .collect();
        assert_eq!(
            pieces,
            [
                ("駅", Some("えき")),
                ("は", None),
                ("ど", None),
                ("こ？", None)
            ]
        );
    }

    #[test]
    fn draws_a_cue_when_a_font_is_there() {
        let Ok(fonts) = Fonts::load(&[]) else {
            eprintln!("skipping: no system font with Japanese");
            return;
        };
        let cue = Cue {
            start: 0.0,
            end: 1.0,
            text: "すみません、駅{えき}はどこですか。".into(),
            role: None,
            translation: Some("Xin lỗi, nhà ga ở đâu ạ?".into()),
        };
        let frame = render_cue(&cue, &fonts, 1920, 1080).unwrap();
        assert!(
            frame.width < 1920 && frame.height > 100,
            "{}x{}",
            frame.width,
            frame.height
        );
        // Some white text and some yellow translation got drawn.
        let px: Vec<&[u8]> = frame.data.chunks_exact(4).collect();
        assert!(px.iter().any(|p| p[0] > 240 && p[1] > 240 && p[2] > 240));
        assert!(px.iter().any(|p| p[0] > 240 && p[1] > 200 && p[2] < 160));
    }
}
