//! OpenCut's project format: `project.json`.
//!
//! A project is a timeline in seconds: what is on screen (`visuals`), what
//! is heard (`audio`), the subtitles, and markers (scenes, chapters,
//! questions to pause on). Paths are relative to the project file, so a
//! lesson folder can be moved or zipped whole.
//!
//! It is deliberately plain JSON, so QBank, textts and scripts can write
//! one without OpenCut, and `opencut render` turns it into a video.

mod mascot;
pub mod ruby;
mod subtitles;
mod textts;

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

pub use mascot::{Corner, Mascot, MascotPose, assign_poses, pick_pose};
pub use subtitles::{parse_srt, write_srt, write_vtt};
pub use textts::{TexttsImport, import_textts};

pub const FORMAT_VERSION: u32 = 1;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("{path}: {source}")]
    Io {
        path: PathBuf,
        source: std::io::Error,
    },
    #[error("{path}: {source}")]
    Json {
        path: PathBuf,
        source: serde_json::Error,
    },
    #[error("{0}")]
    Invalid(String),
}

pub type Result<T, E = Error> = std::result::Result<T, E>;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Project {
    #[serde(default = "format_version")]
    pub version: u32,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub canvas: Canvas,
    /// On screen. Where several overlap, later ones are drawn on top.
    #[serde(default)]
    pub visuals: Vec<Visual>,
    /// Mixed together.
    #[serde(default)]
    pub audio: Vec<AudioClip>,
    #[serde(default)]
    pub subtitles: Vec<Cue>,
    #[serde(default)]
    pub markers: Vec<Marker>,
    /// A chibi in a corner who changes pose with each sentence.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mascot: Option<Mascot>,
    /// Integrated loudness the mix is brought to, in LUFS (EBU R128).
    /// -16 by default, what lessons and podcasts use; `null` leaves the
    /// mix as it is.
    #[serde(default = "default_loudness")]
    pub loudness_lufs: Option<f64>,
}

fn format_version() -> u32 {
    FORMAT_VERSION
}

pub const DEFAULT_LOUDNESS_LUFS: f64 = -16.0;

fn default_loudness() -> Option<f64> {
    Some(DEFAULT_LOUDNESS_LUFS)
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Canvas {
    pub width: u32,
    pub height: u32,
    pub fps: u32,
    /// `#rrggbb`, behind every visual.
    pub background: String,
}

impl Default for Canvas {
    fn default() -> Self {
        Self {
            width: 1920,
            height: 1080,
            fps: 30,
            background: "#000000".into(),
        }
    }
}

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum VisualKind {
    /// A still image (PNG, JPEG, …): a slide.
    #[default]
    Image,
    /// A video clip, from `source_start` in the file.
    Video,
    /// A flat `color`.
    Color,
}

#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Fit {
    /// Whole picture visible, bars around it.
    #[default]
    Contain,
    /// Fills the canvas, edges cropped.
    Cover,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Visual {
    #[serde(default)]
    pub kind: VisualKind,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub path: Option<PathBuf>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub color: Option<String>,
    pub start: f64,
    pub end: f64,
    /// For video: where in the file `start` is.
    #[serde(default, skip_serializing_if = "is_zero")]
    pub source_start: f64,
    #[serde(default)]
    pub fit: Fit,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct AudioClip {
    pub path: PathBuf,
    /// Timeline time the clip starts at.
    #[serde(default)]
    pub start: f64,
    /// Where in the file to start.
    #[serde(default, skip_serializing_if = "is_zero")]
    pub source_start: f64,
    /// Plays this long at most; the whole file when absent.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub duration: Option<f64>,
    #[serde(default, skip_serializing_if = "is_zero")]
    pub gain_db: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Cue {
    pub start: f64,
    pub end: f64,
    pub text: String,
    /// Speaker, e.g. textts role `1`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub role: Option<String>,
    /// Shown under `text`, e.g. the Vietnamese under the Japanese.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub translation: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Marker {
    pub time: f64,
    /// `scene`, `chapter`, `question`, or anything a publisher understands.
    pub kind: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub label: String,
    /// What it points at, e.g. `qbank:123` for a question to ask here.
    #[serde(default, skip_serializing_if = "Option::is_none", rename = "ref")]
    pub reference: Option<String>,
}

fn is_zero(value: &f64) -> bool {
    *value == 0.0
}

impl Default for Project {
    fn default() -> Self {
        Self {
            version: FORMAT_VERSION,
            title: String::new(),
            canvas: Canvas::default(),
            visuals: Vec::new(),
            audio: Vec::new(),
            subtitles: Vec::new(),
            markers: Vec::new(),
            mascot: None,
            loudness_lufs: default_loudness(),
        }
    }
}

impl Project {
    pub fn load(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref();
        let text = std::fs::read_to_string(path).map_err(|source| Error::Io {
            path: path.to_owned(),
            source,
        })?;
        let project: Self = serde_json::from_str(&text).map_err(|source| Error::Json {
            path: path.to_owned(),
            source,
        })?;
        if project.version > FORMAT_VERSION {
            return Err(Error::Invalid(format!(
                "{} is format version {}, newer than this OpenCut ({FORMAT_VERSION})",
                path.display(),
                project.version
            )));
        }
        Ok(project)
    }

    pub fn save(&self, path: impl AsRef<Path>) -> Result<()> {
        let path = path.as_ref();
        let json = serde_json::to_string_pretty(self).expect("projects always serialize");
        std::fs::write(path, json + "\n").map_err(|source| Error::Io {
            path: path.to_owned(),
            source,
        })
    }

    /// Moves everything on the timeline `seconds` later.
    pub fn shift(&mut self, seconds: f64) {
        for v in &mut self.visuals {
            v.start += seconds;
            v.end += seconds;
        }
        for a in &mut self.audio {
            a.start += seconds;
        }
        for c in &mut self.subtitles {
            c.start += seconds;
            c.end += seconds;
        }
        for m in &mut self.markers {
            m.time += seconds;
        }
        if let Some(mascot) = &mut self.mascot {
            for p in &mut mascot.timeline {
                p.time += seconds;
            }
        }
    }

    /// Puts a clip (an intro video) before everything, which moves later.
    /// `with_audio`: the file has sound to mix in too.
    pub fn prepend_clip(&mut self, path: PathBuf, duration: f64, with_audio: bool, label: &str) {
        self.shift(duration);
        self.visuals
            .insert(0, clip_visual(path.clone(), 0.0, duration));
        if with_audio {
            self.audio.insert(0, clip_audio(path, 0.0, duration));
        }
        self.markers.insert(0, chapter(0.0, label));
    }

    /// Puts a clip (an outro video) after everything.
    pub fn append_clip(&mut self, path: PathBuf, duration: f64, with_audio: bool, label: &str) {
        let at = self.duration();
        self.visuals
            .push(clip_visual(path.clone(), at, at + duration));
        if with_audio {
            self.audio.push(clip_audio(path, at, duration));
        }
        self.markers.push(chapter(at, label));
    }

    /// Where the timeline ends: the last visual, subtitle or marker, or an
    /// audio clip with a known duration.
    pub fn duration(&self) -> f64 {
        let visuals = self.visuals.iter().map(|v| v.end);
        let cues = self.subtitles.iter().map(|c| c.end);
        let markers = self.markers.iter().map(|m| m.time);
        let audio = self
            .audio
            .iter()
            .filter_map(|a| a.duration.map(|d| a.start + d));
        visuals
            .chain(cues)
            .chain(markers)
            .chain(audio)
            .fold(0.0, f64::max)
    }

    /// Every problem that would stop a render, relative paths resolved
    /// against `base` (the project file's folder). Empty means fine.
    pub fn problems(&self, base: &Path) -> Vec<String> {
        let mut problems = Vec::new();
        let c = &self.canvas;
        if c.width < 16
            || c.height < 16
            || c.width > 7680
            || c.height > 4320
            || !c.width.is_multiple_of(2)
            || !c.height.is_multiple_of(2)
        {
            problems.push(format!(
                "canvas {}x{}: sides must be even, 16 to 7680x4320",
                c.width, c.height
            ));
        }
        if !(1..=120).contains(&c.fps) {
            problems.push(format!("canvas fps {}: must be 1 to 120", c.fps));
        }
        if parse_color(&c.background).is_none() {
            problems.push(format!(
                "canvas background {:?}: expected #rrggbb",
                c.background
            ));
        }
        for (i, v) in self.visuals.iter().enumerate() {
            let at = format!("visuals[{i}]");
            if !(v.start >= 0.0 && v.end > v.start) {
                problems.push(format!(
                    "{at}: needs 0 <= start < end (got {} to {})",
                    v.start, v.end
                ));
            }
            match v.kind {
                VisualKind::Color => {
                    if v.color.as_deref().and_then(parse_color).is_none() {
                        problems.push(format!("{at}: color visuals need color \"#rrggbb\""));
                    }
                }
                VisualKind::Image | VisualKind::Video => match &v.path {
                    None => problems.push(format!("{at}: {:?} visuals need a path", v.kind)),
                    Some(path) if !resolve(base, path).is_file() => problems.push(format!(
                        "{at}: no file at {}",
                        resolve(base, path).display()
                    )),
                    Some(_) => {}
                },
            }
        }
        for (i, a) in self.audio.iter().enumerate() {
            if !resolve(base, &a.path).is_file() {
                problems.push(format!(
                    "audio[{i}]: no file at {}",
                    resolve(base, &a.path).display()
                ));
            }
            if a.start < 0.0 || a.source_start < 0.0 || a.duration.is_some_and(|d| d <= 0.0) {
                problems.push(format!(
                    "audio[{i}]: start, source_start and duration must be positive"
                ));
            }
        }
        for (i, cue) in self.subtitles.iter().enumerate() {
            if !(cue.start >= 0.0 && cue.end > cue.start) {
                problems.push(format!("subtitles[{i}]: needs 0 <= start < end"));
            }
        }
        if let Some(mascot) = &self.mascot {
            if !(mascot.height > 0.0 && mascot.height <= 1.0) {
                problems.push("mascot: height is a fraction of the canvas, above 0 up to 1".into());
            }
            match mascot.poses(base) {
                Err(error) => problems.push(format!("mascot: {error}")),
                Ok(poses) => {
                    for pose in &mascot.timeline {
                        if !poses.contains_key(&pose.pose) {
                            problems.push(format!("mascot: no pose named {:?}", pose.pose));
                        }
                    }
                    for (name, path) in &poses {
                        if !path.is_file() {
                            problems.push(format!(
                                "mascot: pose {name}: no file at {}",
                                path.display()
                            ));
                        }
                    }
                }
            }
        }
        if self
            .loudness_lufs
            .is_some_and(|l| !(-40.0..=-5.0).contains(&l))
        {
            problems
                .push("loudness_lufs: must be -40 to -5 (or null to leave the mix alone)".into());
        }
        if self.duration() <= 0.0 {
            problems.push(
                "the timeline is empty: add a visual, subtitle or audio with a duration".into(),
            );
        }
        problems
    }
}

fn clip_visual(path: PathBuf, start: f64, end: f64) -> Visual {
    Visual {
        kind: VisualKind::Video,
        path: Some(path),
        color: None,
        start,
        end,
        source_start: 0.0,
        fit: Fit::Contain,
    }
}

fn clip_audio(path: PathBuf, start: f64, duration: f64) -> AudioClip {
    AudioClip {
        path,
        start,
        source_start: 0.0,
        duration: Some(duration),
        gain_db: 0.0,
    }
}

fn chapter(time: f64, label: &str) -> Marker {
    Marker {
        time,
        kind: "chapter".into(),
        label: label.into(),
        reference: None,
    }
}

/// `path` as given if absolute, else under `base`.
pub fn resolve(base: &Path, path: &Path) -> PathBuf {
    if path.is_absolute() {
        path.to_owned()
    } else {
        base.join(path)
    }
}

/// `#rrggbb` (or `rrggbb`) to bytes.
pub fn parse_color(text: &str) -> Option<[u8; 3]> {
    let hex = text.strip_prefix('#').unwrap_or(text);
    if hex.len() != 6 || !hex.is_ascii() {
        return None;
    }
    let byte = |i: usize| u8::from_str_radix(&hex[i..i + 2], 16).ok();
    Some([byte(0)?, byte(2)?, byte(4)?])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trips_and_defaults() {
        let json = r#"{"title":"Bài 10","visuals":[{"path":"s1.png","start":0,"end":5}],
            "markers":[{"time":2,"kind":"question","ref":"qbank:7"}]}"#;
        let project: Project = serde_json::from_str(json).unwrap();
        assert_eq!(project.version, FORMAT_VERSION);
        assert_eq!(project.canvas, Canvas::default());
        assert_eq!(project.visuals[0].kind, VisualKind::Image);
        assert_eq!(project.markers[0].reference.as_deref(), Some("qbank:7"));
        assert_eq!(project.duration(), 5.0);
        let again: Project =
            serde_json::from_str(&serde_json::to_string(&project).unwrap()).unwrap();
        assert_eq!(again, project);
    }

    #[test]
    fn reports_problems() {
        let project = Project {
            canvas: Canvas {
                width: 1921,
                ..Canvas::default()
            },
            visuals: vec![Visual {
                kind: VisualKind::Image,
                path: Some("missing.png".into()),
                color: None,
                start: 3.0,
                end: 1.0,
                source_start: 0.0,
                fit: Fit::Contain,
            }],
            ..Project::default()
        };
        let problems = project.problems(Path::new("/nonexistent"));
        assert_eq!(problems.len(), 3, "{problems:#?}");
    }

    #[test]
    fn intro_and_outro_move_the_lesson() {
        let mut project: Project = serde_json::from_str(
            r#"{"visuals":[{"path":"s.png","start":0,"end":10}],"audio":[{"path":"v.mp3","duration":10}],
                "subtitles":[{"start":1,"end":2,"text":"a"}],"markers":[{"time":5,"kind":"scene"}]}"#,
        )
        .unwrap();
        project.prepend_clip("intro.mp4".into(), 4.0, true, "intro");
        project.append_clip("outro.mp4".into(), 3.0, false, "outro");
        assert_eq!(project.duration(), 17.0);
        assert_eq!(
            (project.visuals[0].start, project.visuals[0].end),
            (0.0, 4.0)
        );
        assert_eq!(
            (project.visuals[1].start, project.visuals[1].end),
            (4.0, 14.0)
        );
        assert_eq!(
            (project.visuals[2].start, project.visuals[2].end),
            (14.0, 17.0)
        );
        assert_eq!((project.audio[0].start, project.audio[1].start), (0.0, 4.0));
        assert_eq!(project.audio.len(), 2, "the outro had no sound");
        assert_eq!(project.subtitles[0].start, 5.0);
        let marks: Vec<_> = project
            .markers
            .iter()
            .map(|m| (m.time, m.kind.as_str()))
            .collect();
        assert_eq!(marks, [(0.0, "chapter"), (9.0, "scene"), (14.0, "chapter")]);
    }

    #[test]
    fn parses_colors() {
        assert_eq!(parse_color("#ff8000"), Some([255, 128, 0]));
        assert_eq!(parse_color("102030"), Some([16, 32, 48]));
        assert_eq!(parse_color("#fff"), None);
    }
}
