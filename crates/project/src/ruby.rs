//! Furigana in textts' script syntax: `漢字{かんじ}`, or `漢字(かんじ)` /
//! `漢字（かんじ）`. A run of kanji followed by its reading in kana.
//!
//! Projects keep subtitles in this syntax; each output turns it into what
//! that format can show.

/// Pieces of an annotated text: plain runs and kanji with their reading.
#[derive(Debug, PartialEq, Eq)]
pub enum Segment<'a> {
    Text(&'a str),
    Ruby { base: &'a str, reading: &'a str },
}

fn is_kanji(c: char) -> bool {
    ('\u{4E00}'..='\u{9FFF}').contains(&c) || c == '々'
}

fn is_kana(c: char) -> bool {
    ('\u{3040}'..='\u{30FF}').contains(&c) || c == 'ー'
}

pub fn segments(text: &str) -> Vec<Segment<'_>> {
    let mut out = Vec::new();
    let mut plain_start = 0;
    let mut chars = text.char_indices().peekable();
    while let Some((start, c)) = chars.next() {
        if !is_kanji(c) {
            continue;
        }
        // The whole kanji run.
        let mut end = start + c.len_utf8();
        while let Some(&(i, next)) = chars.peek() {
            if !is_kanji(next) {
                break;
            }
            end = i + next.len_utf8();
            chars.next();
        }
        let rest = &text[end..];
        let close = match rest.chars().next() {
            Some('{') => '}',
            Some('(') => ')',
            Some('（') => '）',
            _ => continue,
        };
        let open_len = rest.chars().next().map_or(0, char::len_utf8);
        let Some(close_at) = rest[open_len..].find(close) else {
            continue;
        };
        let reading = &rest[open_len..open_len + close_at];
        if reading.is_empty() || !reading.chars().all(is_kana) {
            continue;
        }
        if plain_start < start {
            out.push(Segment::Text(&text[plain_start..start]));
        }
        out.push(Segment::Ruby {
            base: &text[start..end],
            reading,
        });
        plain_start = end + open_len + close_at + close.len_utf8();
        // Skip the reading we just consumed.
        while chars.peek().is_some_and(|&(i, _)| i < plain_start) {
            chars.next();
        }
    }
    if plain_start < text.len() {
        out.push(Segment::Text(&text[plain_start..]));
    }
    out
}

/// Without readings: `駅{えき}は` → `駅は`.
pub fn to_plain(text: &str) -> String {
    segments(text)
        .into_iter()
        .map(|segment| match segment {
            Segment::Text(text) => text,
            Segment::Ruby { base, .. } => base,
        })
        .collect()
}

/// WebVTT, readings as ruby: `駅{えき}は` → `<ruby>駅<rt>えき</rt></ruby>は`.
/// `&`, `<` and `>` in the text are escaped, as WebVTT requires.
pub fn to_vtt(text: &str) -> String {
    segments(text)
        .into_iter()
        .map(|segment| match segment {
            Segment::Text(text) => escape(text),
            Segment::Ruby { base, reading } => {
                format!("<ruby>{}<rt>{}</rt></ruby>", escape(base), escape(reading))
            }
        })
        .collect()
}

fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_all_three_notations() {
        let text = "すみません、駅{えき}はどこですか。田中（たなか）さん、本当(ほんとう)に！";
        assert_eq!(
            to_plain(text),
            "すみません、駅はどこですか。田中さん、本当に！"
        );
        assert_eq!(
            to_vtt(text),
            "すみません、<ruby>駅<rt>えき</rt></ruby>はどこですか。<ruby>田中<rt>たなか</rt></ruby>さん、<ruby>本当<rt>ほんとう</rt></ruby>に！"
        );
    }

    #[test]
    fn leaves_other_brackets_alone() {
        // Not kana inside, or not after kanji: not a reading.
        for text in ["駅(1)です", "これ{えき}", "A < B & 駅{eki}"] {
            assert_eq!(to_plain(text), text);
        }
        assert_eq!(to_vtt("A < B"), "A &lt; B");
    }
}
