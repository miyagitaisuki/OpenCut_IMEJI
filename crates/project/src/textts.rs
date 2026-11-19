//! Builds a project from what textts exports for a dialogue: the audio
//! (`<name>.mp3`), its subtitles (`<name>.srt`) and its timeline
//! (`<name>.timeline.json`: each line's role and times, and scene changes).
//!
//! textts' SRT has no furigana (`[1] 駅はどこですか`). Given the script
//! (`.txt`) or textts' own project (`.json`), subtitles take each line's
//! annotated text instead (`駅{えき}はどこですか`), matched by line id
//! (`L001`…), which textts gives the script and the timeline alike.

use std::path::{Path, PathBuf};

use serde::Deserialize;

use crate::{
    AudioClip, Canvas, Cue, Error, Fit, Marker, Project, Result, Visual, VisualKind, parse_srt,
};

/// What to build a lesson project from. `srt` and `timeline` default to
/// the files textts writes beside `audio`.
#[derive(Clone, Debug, Default)]
pub struct TexttsImport {
    pub audio: PathBuf,
    pub srt: Option<PathBuf>,
    pub timeline: Option<PathBuf>,
    /// The textts script (`.txt`) or project (`.json`): subtitles then keep
    /// its furigana.
    pub script: Option<PathBuf>,
    /// Slides, in order. They are spread over the scenes when there is one
    /// per scene, over the lines when there is one per line, and evenly
    /// over the audio otherwise.
    pub slides: Vec<PathBuf>,
    pub title: Option<String>,
    pub canvas: Option<Canvas>,
}

#[derive(Deserialize)]
struct Timeline {
    #[serde(default)]
    duration_ms: Option<f64>,
    #[serde(default)]
    items: Vec<Line>,
    #[serde(default)]
    scenes: Vec<Scene>,
}

#[derive(Deserialize)]
struct Line {
    #[serde(default)]
    id: String,
    #[serde(default)]
    role: serde_json::Value,
    start_ms: f64,
    #[serde(default)]
    end_ms: f64,
}

#[derive(Deserialize)]
struct Scene {
    #[serde(default)]
    id: String,
    start_ms: f64,
}

/// Builds the project. Paths in it are written relative to `project_dir`
/// (where the project file will be saved) when they are inside it.
pub fn import_textts(import: &TexttsImport, project_dir: &Path) -> Result<Project> {
    let sibling = |suffix: &str| {
        let stem = import
            .audio
            .file_stem()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_default();
        let path = import.audio.with_file_name(format!("{stem}{suffix}"));
        path.is_file().then_some(path)
    };
    if !import.audio.is_file() {
        return Err(Error::Invalid(format!(
            "no audio file at {}",
            import.audio.display()
        )));
    }
    let srt_path = import.srt.clone().or_else(|| sibling(".srt"));
    let timeline_path = import
        .timeline
        .clone()
        .or_else(|| sibling(".timeline.json"));

    let mut cues = match &srt_path {
        Some(path) => parse_srt(&read(path)?),
        None => Vec::new(),
    };
    let timeline: Option<Timeline> = match &timeline_path {
        Some(path) => Some(
            serde_json::from_str(&read(path)?).map_err(|source| Error::Json {
                path: path.clone(),
                source,
            })?,
        ),
        None => None,
    };

    let duration = timeline
        .as_ref()
        .and_then(|t| t.duration_ms)
        .map(|ms| ms / 1000.0)
        .or_else(|| cues.last().map(|cue| cue.end + 0.5))
        .ok_or_else(|| {
            Error::Invalid(format!(
                "cannot tell how long {} is: give its .timeline.json or .srt",
                import.audio.display()
            ))
        })?;

    for cue in &mut cues {
        strip_role_prefix(cue);
    }
    if let Some(timeline) = &timeline {
        assign_roles(&mut cues, &timeline.items);
    }
    if let Some(script) = &import.script {
        let lines = script_lines(script)?;
        cues = with_furigana(cues, timeline.as_ref(), &lines).ok_or_else(|| {
            Error::Invalid(format!(
                "{} does not match the audio: its {} lines are not the timeline's or the subtitles'",
                script.display(),
                lines.len()
            ))
        })?;
    }
    let scenes: Vec<&Scene> = timeline
        .as_ref()
        .map(|t| t.scenes.iter().collect())
        .unwrap_or_default();

    let canvas = import.canvas.clone().unwrap_or_default();
    let visuals = if import.slides.is_empty() {
        vec![Visual {
            kind: VisualKind::Color,
            path: None,
            color: Some(canvas.background.clone()),
            start: 0.0,
            end: duration,
            source_start: 0.0,
            fit: Fit::Contain,
        }]
    } else {
        let starts: Vec<f64> = if !scenes.is_empty() && import.slides.len() == scenes.len() {
            scenes.iter().map(|s| s.start_ms / 1000.0).collect()
        } else if !cues.is_empty() && import.slides.len() == cues.len() {
            cues.iter().map(|cue| cue.start).collect()
        } else {
            let n = import.slides.len() as f64;
            (0..import.slides.len())
                .map(|i| duration * i as f64 / n)
                .collect()
        };
        slides_at(&import.slides, &starts, duration, project_dir)
    };

    let markers = scenes
        .iter()
        .map(|scene| Marker {
            time: scene.start_ms / 1000.0,
            kind: "scene".into(),
            label: scene.id.clone(),
            reference: None,
        })
        .collect();

    let title = import.title.clone().unwrap_or_else(|| {
        import
            .audio
            .file_stem()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_default()
    });

    Ok(Project {
        title,
        canvas,
        visuals,
        audio: vec![AudioClip {
            path: relative(&import.audio, project_dir),
            start: 0.0,
            source_start: 0.0,
            duration: Some(duration),
            gain_db: 0.0,
        }],
        subtitles: cues,
        markers,
        ..Project::default()
    })
}

/// textts writes one SRT cue per line, in timeline order; match them by
/// order when the counts agree, else by start time.
fn assign_roles(cues: &mut [Cue], lines: &[Line]) {
    let role = role_of;
    if cues.len() == lines.len() {
        for (cue, line) in cues.iter_mut().zip(lines) {
            cue.role = role(line);
        }
        return;
    }
    for cue in cues {
        cue.role = lines
            .iter()
            .filter(|line| (line.start_ms / 1000.0 - cue.start).abs() < 0.1)
            .find_map(role);
    }
}

/// textts starts each SRT cue with its speaker, `[1] `: move it to `role`.
fn strip_role_prefix(cue: &mut Cue) {
    let Some(rest) = cue.text.strip_prefix('[') else {
        return;
    };
    let Some((role, text)) = rest.split_once(']') else {
        return;
    };
    if role.is_empty() || !role.chars().all(|c| c.is_ascii_digit()) {
        return;
    }
    cue.role.get_or_insert_with(|| role.to_owned());
    cue.text = text.trim_start().to_owned();
}

/// One spoken line of a textts script: its id and annotated text.
#[derive(Debug, PartialEq)]
struct ScriptLine {
    id: String,
    display: String,
    /// After ` // ` in the script: the line in the learners' language.
    translation: Option<String>,
}

/// Subtitles in the script's own text. Matched by id against the timeline
/// when there is one, else by order against the SRT. `None` if neither fits.
fn with_furigana(
    cues: Vec<Cue>,
    timeline: Option<&Timeline>,
    lines: &[ScriptLine],
) -> Option<Vec<Cue>> {
    if let Some(timeline) =
        timeline.filter(|t| !t.items.is_empty() && t.items.iter().all(|i| !i.id.is_empty()))
    {
        let by_id: std::collections::HashMap<&str, &ScriptLine> =
            lines.iter().map(|line| (line.id.as_str(), line)).collect();
        let rebuilt: Option<Vec<Cue>> = timeline
            .items
            .iter()
            .map(|item| {
                let line = by_id.get(item.id.as_str())?;
                Some(Cue {
                    start: item.start_ms / 1000.0,
                    end: item.end_ms.max(item.start_ms + 1.0) / 1000.0,
                    text: line.display.clone(),
                    role: role_of(item),
                    translation: line.translation.clone(),
                })
            })
            .collect();
        if rebuilt.is_some() {
            return rebuilt;
        }
    }
    (lines.len() == cues.len()).then(|| {
        cues.into_iter()
            .zip(lines)
            .map(|(cue, line)| Cue {
                text: line.display.clone(),
                translation: line.translation.clone(),
                ..cue
            })
            .collect()
    })
}

fn script_lines(path: &Path) -> Result<Vec<ScriptLine>> {
    let text = read(path)?;
    let is_json = path
        .extension()
        .is_some_and(|e| e.eq_ignore_ascii_case("json"));
    if !is_json {
        return Ok(parse_script(&text));
    }
    #[derive(Deserialize)]
    struct Project {
        items: Vec<Item>,
    }
    #[derive(Deserialize)]
    struct Item {
        id: String,
        #[serde(rename = "type", default)]
        kind: String,
        #[serde(default)]
        display: String,
        #[serde(default)]
        translation: String,
    }
    let project: Project = serde_json::from_str(&text).map_err(|source| Error::Json {
        path: path.to_owned(),
        source,
    })?;
    Ok(project
        .items
        .into_iter()
        .filter(|item| item.kind == "line")
        .map(|item| ScriptLine {
            id: item.id,
            display: item.display,
            translation: Some(item.translation.trim().to_owned()).filter(|t| !t.is_empty()),
        })
        .collect())
}

/// textts' script syntax, as far as ids and line text go: every item
/// (line, `[pause=…]`, `[sfx=…]`, `[bgm=…]`) takes the next id `L001`…;
/// lines are `[1]{attrs} text` or `1: text`, indented lines continue the
/// previous one, `#` starts a comment, ` // ` starts a translation.
/// (Readings from textts' readings.yaml are not applied.)
fn parse_script(text: &str) -> Vec<ScriptLine> {
    let mut items: Vec<Option<String>> = Vec::new();
    let mut continuing = false;
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some(text) = spoken_text(line) {
            items.push(Some(text.to_owned()));
            continuing = true;
        } else if line.starts_with('[') {
            // [pause=…], [sfx=…], [bgm=…]: an item without text.
            items.push(None);
            continuing = false;
        } else if continuing && let Some(Some(current)) = items.last_mut() {
            current.push_str(line);
        }
    }
    items
        .into_iter()
        .enumerate()
        .filter_map(|(i, text)| {
            let text = text?;
            let (display, translation) = match text.split_once(" // ") {
                Some((display, translation)) => (display, Some(translation.trim().to_owned())),
                None => (text.as_str(), None),
            };
            Some(ScriptLine {
                id: format!("L{:03}", i + 1),
                display: display.trim().to_owned(),
                translation: translation.filter(|t| !t.is_empty()),
            })
        })
        .collect()
}

/// The text of a spoken line, `[1]{…} text` or `1: text`.
fn spoken_text(line: &str) -> Option<&str> {
    if let Some(rest) = line.strip_prefix('[') {
        let (role, rest) = rest.split_once(']')?;
        if role.is_empty() || !role.chars().all(|c| c.is_ascii_digit()) {
            return None;
        }
        let rest = rest.trim_start();
        let rest = match rest.strip_prefix('{') {
            Some(attrs) => attrs.split_once('}').map_or("", |(_, after)| after),
            None => rest,
        };
        return Some(rest.trim());
    }
    let digits = line
        .find(|c: char| !c.is_ascii_digit())
        .filter(|&n| n > 0)?;
    let rest = &line[digits..];
    let text = rest.trim_start_matches([' ', '\t', ':', '：', '.', '、']);
    (text.len() < rest.len() && !text.is_empty()).then_some(text)
}

fn role_of(line: &Line) -> Option<String> {
    match &line.role {
        serde_json::Value::String(s) if !s.is_empty() => Some(s.clone()),
        serde_json::Value::Number(n) => Some(n.to_string()),
        _ => None,
    }
}

fn slides_at(slides: &[PathBuf], starts: &[f64], duration: f64, project_dir: &Path) -> Vec<Visual> {
    slides
        .iter()
        .enumerate()
        .map(|(i, path)| Visual {
            kind: VisualKind::Image,
            path: Some(relative(path, project_dir)),
            color: None,
            // The first slide covers the start, even before the first line.
            start: if i == 0 { 0.0 } else { starts[i] },
            end: starts
                .get(i + 1)
                .copied()
                .unwrap_or(duration)
                .max(starts[i] + 0.001),
            source_start: 0.0,
            fit: Fit::Contain,
        })
        .collect()
}

fn read(path: &Path) -> Result<String> {
    std::fs::read_to_string(path).map_err(|source| Error::Io {
        path: path.to_owned(),
        source,
    })
}

fn relative(path: &Path, base: &Path) -> PathBuf {
    let absolute = |p: &Path| std::path::absolute(p).unwrap_or_else(|_| p.to_owned());
    let (path, base) = (absolute(path), absolute(base));
    path.strip_prefix(&base).map(Path::to_owned).unwrap_or(path)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lesson_dir() -> PathBuf {
        let dir = std::env::temp_dir().join(format!("opencut-textts-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("bai10.mp3"), b"not really audio").unwrap();
        std::fs::write(
            dir.join("bai10.srt"),
            "1\n00:00:00,500 --> 00:00:02,000\nA\n\n2\n00:00:02,500 --> 00:00:04,000\nB\n\n3\n00:00:05,000 --> 00:00:07,000\nC\n",
        )
        .unwrap();
        std::fs::write(
            dir.join("bai10.timeline.json"),
            r#"{"duration_ms": 8000, "scenes": [{"id": "S1", "type": "scene", "start_ms": 0}, {"id": "S2", "type": "scene", "start_ms": 4500}],
               "items": [{"id": "L001", "role": "1", "start_ms": 500, "end_ms": 2000},
                         {"id": "L002", "role": "2", "start_ms": 2500, "end_ms": 4000},
                         {"id": "L003", "role": "1", "start_ms": 5000, "end_ms": 7000}]}"#,
        )
        .unwrap();
        dir
    }

    #[test]
    fn imports_lines_roles_scenes_and_slides() {
        let dir = lesson_dir();
        let import = TexttsImport {
            audio: dir.join("bai10.mp3"),
            slides: vec![dir.join("a.png"), dir.join("b.png")],
            ..TexttsImport::default()
        };
        let project = import_textts(&import, &dir).unwrap();

        assert_eq!(project.title, "bai10");
        assert_eq!(project.audio[0].path, PathBuf::from("bai10.mp3"));
        assert_eq!(project.audio[0].duration, Some(8.0));
        assert_eq!(project.duration(), 8.0);
        let roles: Vec<_> = project
            .subtitles
            .iter()
            .map(|c| c.role.as_deref())
            .collect();
        assert_eq!(roles, [Some("1"), Some("2"), Some("1")]);
        // Two slides, two scenes: one slide per scene.
        let spans: Vec<_> = project.visuals.iter().map(|v| (v.start, v.end)).collect();
        assert_eq!(spans, [(0.0, 4.5), (4.5, 8.0)]);
        assert_eq!(project.markers.len(), 2);

        // Three slides, three lines: one per line.
        let import = TexttsImport {
            slides: vec![dir.join("a.png"), dir.join("b.png"), dir.join("c.png")],
            ..import
        };
        let spans: Vec<_> = import_textts(&import, &dir)
            .unwrap()
            .visuals
            .iter()
            .map(|v| (v.start, v.end))
            .collect();
        assert_eq!(spans, [(0.0, 2.5), (2.5, 5.0), (5.0, 8.0)]);

        std::fs::remove_dir_all(dir).ok();
    }

    const SCRIPT: &str = "# hỏi đường\n[1] すみません、駅{えき}はどこですか。\n[2]{emotion=happy, speed=slow} あ、駅ですか。 // À, nhà ga à.\n[1] ありがとうございます。\n[pause=1500]\n[3]{emotion=surprised} えっ、田中{たなか}さん！\n    久しぶりですね。\n4: 本当(ほんとう)に。\n";

    #[test]
    fn parses_textts_scripts_with_textts_ids() {
        let lines = parse_script(SCRIPT);
        let pairs: Vec<_> = lines
            .iter()
            .map(|l| (l.id.as_str(), l.display.as_str()))
            .collect();
        assert_eq!(
            pairs,
            [
                ("L001", "すみません、駅{えき}はどこですか。"),
                ("L002", "あ、駅ですか。"),
                ("L003", "ありがとうございます。"),
                ("L005", "えっ、田中{たなか}さん！久しぶりですね。"),
                ("L006", "本当(ほんとう)に。"),
            ]
        );
    }

    #[test]
    fn subtitles_take_the_scripts_furigana() {
        let dir = std::env::temp_dir().join(format!("opencut-textts-ruby-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("hoi.mp3"), b"x").unwrap();
        std::fs::write(dir.join("hoi.txt"), SCRIPT).unwrap();
        // What textts writes: plain text with the speaker in front.
        std::fs::write(
            dir.join("hoi.srt"),
            "1\n00:00:02,000 --> 00:00:04,000\n[1] すみません、駅はどこですか。\n\n2\n00:00:04,600 --> 00:00:06,000\n[2] あ、駅ですか。\n",
        )
        .unwrap();
        std::fs::write(
            dir.join("hoi.timeline.json"),
            r#"{"duration_ms": 9000, "items": [
                {"id": "L001", "role": "1", "start_ms": 2000, "end_ms": 4000},
                {"id": "L002", "role": "2", "start_ms": 4600, "end_ms": 6000},
                {"id": "L005", "role": "3", "start_ms": 7500, "end_ms": 8800}]}"#,
        )
        .unwrap();

        let import = TexttsImport {
            audio: dir.join("hoi.mp3"),
            ..TexttsImport::default()
        };
        // Without the script: textts' plain text, the speaker moved to `role`.
        let plain = import_textts(&import, &dir).unwrap();
        assert_eq!(plain.subtitles[0].text, "すみません、駅はどこですか。");
        assert_eq!(plain.subtitles[1].role.as_deref(), Some("2"));

        let import = TexttsImport {
            script: Some(dir.join("hoi.txt")),
            ..import
        };
        let project = import_textts(&import, &dir).unwrap();
        let texts: Vec<_> = project
            .subtitles
            .iter()
            .map(|c| (c.text.as_str(), c.role.as_deref()))
            .collect();
        assert_eq!(
            texts,
            [
                ("すみません、駅{えき}はどこですか。", Some("1")),
                ("あ、駅ですか。", Some("2")),
                ("えっ、田中{たなか}さん！久しぶりですね。", Some("3")),
            ]
        );
        assert!(
            crate::write_vtt(&project.subtitles)
                .contains("<v 3>えっ、<ruby>田中<rt>たなか</rt></ruby>さん！")
        );
        // The line with ` // ` in the script carries its translation, under it.
        assert_eq!(
            project.subtitles[1].translation.as_deref(),
            Some("À, nhà ga à.")
        );
        assert!(
            crate::write_vtt(&project.subtitles)
                .contains("<v 2>あ、駅ですか。\n<c.tr>À, nhà ga à.</c>")
        );
        assert!(crate::write_srt(&project.subtitles).contains("あ、駅ですか。\nÀ, nhà ga à.\n"));
        assert_eq!(project.subtitles[0].translation, None);
        assert!(crate::write_srt(&project.subtitles).contains("えっ、田中さん！久しぶりですね。"));

        std::fs::remove_dir_all(dir).ok();
    }
}
