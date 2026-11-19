//! Builds a project from what textts exports for a dialogue: the audio
//! (`<name>.mp3`), its subtitles (`<name>.srt`) and its timeline
//! (`<name>.timeline.json`: each line's role and times, and scene changes).

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
    role: serde_json::Value,
    start_ms: f64,
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

    if let Some(timeline) = &timeline {
        assign_roles(&mut cues, &timeline.items);
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
    let role = |line: &Line| match &line.role {
        serde_json::Value::String(s) if !s.is_empty() => Some(s.clone()),
        serde_json::Value::Number(n) => Some(n.to_string()),
        _ => None,
    };
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
}
