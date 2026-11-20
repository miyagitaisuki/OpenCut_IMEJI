//! Lesson projects: what `import-textts`, `check` and `render` do, shared
//! by the command line and the MCP server.

use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use opencut_media::VideoCodec;
use opencut_project::{Canvas, Project, TexttsImport, import_textts};
use opencut_render::{RenderOptions, RenderReport, render};
use rmcp::schemars::JsonSchema;
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, JsonSchema)]
#[schemars(crate = "rmcp::schemars")]
pub(crate) struct ImportRequest {
    /// The audio textts made (`<name>.mp3` or `.wav`).
    pub audio: PathBuf,
    /// Where to save the project; also the folder its paths are relative to.
    pub project: PathBuf,
    /// Subtitles; defaults to `<name>.srt` beside the audio.
    #[serde(default)]
    pub srt: Option<PathBuf>,
    /// textts timeline; defaults to `<name>.timeline.json` beside the audio.
    #[serde(default)]
    pub timeline: Option<PathBuf>,
    /// The textts script (.txt) or textts project (.json) the audio was made
    /// from: subtitles then keep its furigana (漢字{かな}), shown as ruby in the .vtt.
    #[serde(default)]
    pub script: Option<PathBuf>,
    /// Loudness to bring the mix to, in LUFS (default -16).
    #[serde(default)]
    pub loudness_lufs: Option<f64>,
    /// A video to open the lesson with (e.g. the Remotion intro); the lesson moves after it.
    #[serde(default)]
    pub intro: Option<PathBuf>,
    /// A video to close the lesson with.
    #[serde(default)]
    pub outro: Option<PathBuf>,
    /// Slide images in order: one per scene, one per line, or spread evenly.
    #[serde(default)]
    pub slides: Vec<PathBuf>,
    #[serde(default)]
    pub title: Option<String>,
    /// Canvas width (default 1920).
    #[serde(default)]
    pub width: Option<u32>,
    /// Canvas height (default 1080).
    #[serde(default)]
    pub height: Option<u32>,
    /// Frames per second (default 30).
    #[serde(default)]
    pub fps: Option<u32>,
    /// Background `#rrggbb` (default black).
    #[serde(default)]
    pub background: Option<String>,
}

#[derive(Debug, Serialize)]
pub(crate) struct ImportResult {
    pub project: PathBuf,
    pub duration_seconds: f64,
    pub slides: usize,
    pub subtitles: usize,
    pub markers: usize,
    pub problems: Vec<String>,
}

pub(crate) fn import(request: &ImportRequest) -> Result<ImportResult> {
    let project_dir = parent(&request.project);
    std::fs::create_dir_all(&project_dir)
        .with_context(|| format!("creating {}", project_dir.display()))?;
    let defaults = Canvas::default();
    let canvas = Canvas {
        width: request.width.unwrap_or(defaults.width),
        height: request.height.unwrap_or(defaults.height),
        fps: request.fps.unwrap_or(defaults.fps),
        background: request.background.clone().unwrap_or(defaults.background),
    };
    let project = import_textts(
        &TexttsImport {
            audio: request.audio.clone(),
            srt: request.srt.clone(),
            timeline: request.timeline.clone(),
            script: request.script.clone(),
            slides: request.slides.clone(),
            title: request.title.clone(),
            canvas: Some(canvas),
        },
        &project_dir,
    )?;
    let mut project = project;
    if let Some(intro) = &request.intro {
        let (path, seconds, audio) = clip(intro, &project_dir)?;
        project.prepend_clip(path, seconds, audio, "intro");
    }
    if let Some(outro) = &request.outro {
        let (path, seconds, audio) = clip(outro, &project_dir)?;
        project.append_clip(path, seconds, audio, "outro");
    }
    if let Some(lufs) = request.loudness_lufs {
        project.loudness_lufs = Some(lufs);
    }
    project.save(&request.project)?;
    Ok(ImportResult {
        project: request.project.clone(),
        duration_seconds: project.duration(),
        slides: project.visuals.iter().filter(|v| v.path.is_some()).count(),
        subtitles: project.subtitles.len(),
        markers: project.markers.len(),
        problems: project.problems(&project_dir),
    })
}

#[derive(Debug, Serialize)]
pub(crate) struct CheckResult {
    pub ok: bool,
    pub title: String,
    pub duration_seconds: f64,
    pub visuals: usize,
    pub audio: usize,
    pub subtitles: usize,
    pub markers: usize,
    pub problems: Vec<String>,
}

pub(crate) fn check(path: &Path) -> Result<CheckResult> {
    let project = Project::load(path)?;
    let problems = project.problems(&parent(path));
    Ok(CheckResult {
        ok: problems.is_empty(),
        title: project.title.clone(),
        duration_seconds: project.duration(),
        visuals: project.visuals.len(),
        audio: project.audio.len(),
        subtitles: project.subtitles.len(),
        markers: project.markers.len(),
        problems,
    })
}

pub(crate) fn parse_codec(name: Option<&str>) -> Result<VideoCodec> {
    Ok(match name.unwrap_or("auto") {
        "auto" => VideoCodec::Auto,
        "h264" => VideoCodec::H264,
        "mpeg4" => VideoCodec::Mpeg4,
        other => bail!("unknown codec {other:?}: expected auto, h264 or mpeg4"),
    })
}

/// Renders `project` to `output`, by default `<project name>.mp4` beside it.
/// How to render, as the command line and MCP take it.
pub(crate) struct RenderChoices {
    pub codec: VideoCodec,
    pub burn_subtitles: bool,
    pub fonts: Vec<PathBuf>,
}

pub(crate) fn render_project(
    project: &Path,
    output: Option<&Path>,
    choices: RenderChoices,
    progress: impl FnMut(f64),
) -> Result<RenderReport> {
    let loaded = Project::load(project)?;
    let output = output
        .map(Path::to_owned)
        .unwrap_or_else(|| default_output(project));
    if let Some(dir) = output.parent().filter(|dir| !dir.as_os_str().is_empty()) {
        std::fs::create_dir_all(dir).with_context(|| format!("creating {}", dir.display()))?;
    }
    let options = RenderOptions {
        codec: choices.codec,
        burn_subtitles: choices.burn_subtitles,
        fonts: choices.fonts,
        ..RenderOptions::default()
    };
    Ok(render(
        &loaded,
        &parent(project),
        &output,
        &options,
        progress,
    )?)
}

/// `bai10.project.json` → `bai10.mp4`; `lesson.json` → `lesson.mp4`.
fn default_output(project: &Path) -> PathBuf {
    let stem = project
        .file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_default();
    let name = stem.strip_suffix(".project").unwrap_or(&stem);
    project.with_file_name(format!("{name}.mp4"))
}

/// A clip's path as the project should hold it, its length, and whether it has sound.
fn clip(path: &Path, project_dir: &Path) -> Result<(PathBuf, f64, bool)> {
    let info = opencut_media::probe(path).with_context(|| format!("reading {}", path.display()))?;
    if info.video.is_empty() || info.duration_seconds <= 0.0 {
        bail!("{} has no video to put in the lesson", path.display());
    }
    let absolute = std::path::absolute(path).unwrap_or_else(|_| path.to_owned());
    let base = std::path::absolute(project_dir).unwrap_or_else(|_| project_dir.to_owned());
    let stored = absolute
        .strip_prefix(&base)
        .map(Path::to_owned)
        .unwrap_or(absolute);
    Ok((stored, info.duration_seconds, !info.audio.is_empty()))
}

fn parent(path: &Path) -> PathBuf {
    match path.parent() {
        Some(dir) if !dir.as_os_str().is_empty() => dir.to_owned(),
        _ => PathBuf::from("."),
    }
}

#[derive(Debug, Serialize)]
pub(crate) struct MascotResult {
    pub project: PathBuf,
    /// Poses set, one per subtitle cue; 0 when the mascot was removed.
    pub poses: usize,
}

/// Adds (or updates, or removes) the corner mascot and picks a pose per cue.
pub(crate) fn set_mascot(
    project_path: &Path,
    avatar: Option<PathBuf>,
    corner: Option<&str>,
    height: Option<f64>,
    remove: bool,
) -> Result<MascotResult> {
    let mut project = Project::load(project_path)?;
    let base = project_path.parent().unwrap_or(Path::new("."));
    if remove {
        project.mascot = None;
        project.save(project_path)?;
        return Ok(MascotResult {
            project: project_path.to_owned(),
            poses: 0,
        });
    }
    if let Some(avatar) = avatar {
        // Stored relative to the project when it lies beneath it, else as given.
        let avatar =
            plain(std::fs::canonicalize(&avatar).with_context(|| format!("{}", avatar.display()))?);
        let base_abs = plain(std::fs::canonicalize(base)?);
        let stored = avatar
            .strip_prefix(&base_abs)
            .map(Path::to_path_buf)
            .unwrap_or(avatar);
        let mut mascot = project
            .mascot
            .take()
            .unwrap_or_else(|| opencut_project::Mascot::new(stored.clone()));
        mascot.avatar = stored;
        project.mascot = Some(mascot);
    }
    let Some(mascot) = project.mascot.as_mut() else {
        bail!("no mascot in the project yet: pass --avatar <folder>");
    };
    match corner {
        Some("bottom-right") => mascot.corner = opencut_project::Corner::BottomRight,
        Some("bottom-left") => mascot.corner = opencut_project::Corner::BottomLeft,
        Some(other) => bail!("--corner: expected bottom-right or bottom-left, got {other:?}"),
        None => {}
    }
    if let Some(height) = height {
        mascot.height = height;
    }
    let poses = opencut_project::assign_poses(&mut project, base)?;
    project.save(project_path)?;
    Ok(MascotResult {
        project: project_path.to_owned(),
        poses,
    })
}

/// Windows' verbatim prefix (backslash backslash ? backslash) off a canonical
/// path, so stored paths read normally.
fn plain(path: PathBuf) -> PathBuf {
    match path.to_str().and_then(|p| p.strip_prefix("\\\\?\\")) {
        Some(rest) => PathBuf::from(rest),
        None => path,
    }
}
