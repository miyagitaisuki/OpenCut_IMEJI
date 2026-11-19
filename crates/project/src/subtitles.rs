//! SubRip (`.srt`) in, SubRip and WebVTT (`.vtt`, what HTML players read) out.

use crate::Cue;

/// Parses SubRip. Blocks it cannot read are skipped, not fatal: an SRT
/// written by hand often has a stray blank or number.
pub fn parse_srt(text: &str) -> Vec<Cue> {
    let text = text.trim_start_matches('\u{feff}').replace("\r\n", "\n");
    let mut cues = Vec::new();
    for block in text.split("\n\n") {
        let mut lines = block
            .lines()
            .map(str::trim_end)
            .filter(|line| !line.is_empty())
            .peekable();
        // Optional index line.
        if lines
            .peek()
            .is_some_and(|line| line.chars().all(|c| c.is_ascii_digit()))
        {
            lines.next();
        }
        let Some((start, end)) = lines.next().and_then(parse_timing) else {
            continue;
        };
        let body: Vec<&str> = lines.collect();
        if body.is_empty() {
            continue;
        }
        cues.push(Cue {
            start,
            end,
            text: body.join("\n"),
            role: None,
        });
    }
    cues
}

pub fn write_srt(cues: &[Cue]) -> String {
    let mut out = String::new();
    for (i, cue) in cues.iter().enumerate() {
        out += &format!(
            "{}\n{} --> {}\n{}\n\n",
            i + 1,
            timestamp(cue.start, ','),
            timestamp(cue.end, ','),
            cue.text
        );
    }
    out
}

pub fn write_vtt(cues: &[Cue]) -> String {
    let mut out = String::from("WEBVTT\n\n");
    for cue in cues {
        // A blank line ends a cue in WebVTT, so a cue's own blank lines go.
        let text = cue
            .text
            .lines()
            .filter(|line| !line.trim().is_empty())
            .collect::<Vec<_>>()
            .join("\n");
        let text = match &cue.role {
            Some(role) => format!("<v {role}>{text}"),
            None => text,
        };
        out += &format!(
            "{} --> {}\n{}\n\n",
            timestamp(cue.start, '.'),
            timestamp(cue.end, '.'),
            text
        );
    }
    out
}

fn parse_timing(line: &str) -> Option<(f64, f64)> {
    let (start, end) = line.split_once("-->")?;
    // WebVTT-style settings may follow the end time.
    let end = end.split_whitespace().next()?;
    Some((parse_timestamp(start.trim())?, parse_timestamp(end)?))
}

fn parse_timestamp(text: &str) -> Option<f64> {
    let text = text.replace(',', ".");
    let parts: Vec<&str> = text.split(':').collect();
    let (h, m, s) = match parts.as_slice() {
        [h, m, s] => (
            h.parse::<f64>().ok()?,
            m.parse::<f64>().ok()?,
            s.parse::<f64>().ok()?,
        ),
        [m, s] => (0.0, m.parse::<f64>().ok()?, s.parse::<f64>().ok()?),
        _ => return None,
    };
    Some(h * 3600.0 + m * 60.0 + s)
}

fn timestamp(seconds: f64, separator: char) -> String {
    let ms = (seconds.max(0.0) * 1000.0).round() as u64;
    format!(
        "{:02}:{:02}:{:02}{separator}{:03}",
        ms / 3_600_000,
        ms / 60_000 % 60,
        ms / 1000 % 60,
        ms % 1000
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    const SRT: &str = "\u{feff}1\r\n00:00:00,500 --> 00:00:02,250\r\nこんにちは。\r\n\r\n2\r\n00:00:03,000 --> 00:01:04,125\r\nはじめまして。\r\nよろしく。\r\n\r\n";

    #[test]
    fn parses_and_writes() {
        let cues = parse_srt(SRT);
        assert_eq!(cues.len(), 2);
        assert_eq!((cues[0].start, cues[0].end), (0.5, 2.25));
        assert_eq!(cues[1].end, 64.125);
        assert_eq!(cues[1].text, "はじめまして。\nよろしく。");
        assert_eq!(parse_srt(&write_srt(&cues)), cues);

        let vtt = write_vtt(&cues);
        assert!(vtt.starts_with("WEBVTT\n\n00:00:00.500 --> 00:00:02.250\nこんにちは。\n"));
    }

    #[test]
    fn skips_unreadable_blocks() {
        assert_eq!(
            parse_srt("garbage\n\n1\n00:00:01,000 --> 00:00:02,000\nok\n").len(),
            1
        );
    }
}
