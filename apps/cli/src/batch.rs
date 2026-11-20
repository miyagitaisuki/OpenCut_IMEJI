//! Batch rendering: many lesson projects in one run. Each project is rendered
//! as `render_project` does; the report says what happened to each one.

use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};

use crate::lesson::{self, RenderChoices};

#[derive(Deserialize)]
#[serde(untagged)]
enum Entry {
    Path(PathBuf),
    Detailed {
        project: PathBuf,
        #[serde(default)]
        output: Option<PathBuf>,
        #[serde(default)]
        burn_subtitles: Option<bool>,
    },
}

#[derive(Deserialize)]
#[serde(untagged)]
enum Manifest {
    List(Vec<Entry>),
    Wrapped { projects: Vec<Entry> },
}

/// One project to render, with its paths resolved.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct Item {
    pub project: PathBuf,
    pub output: Option<PathBuf>,
    pub burn_subtitles: Option<bool>,
}

/// What the batch does, as the command line and MCP take it.
pub(crate) struct Options {
    pub output_dir: Option<PathBuf>,
    pub codec: String,
    pub burn_subtitles: bool,
    pub fonts: Vec<PathBuf>,
    /// Projects rendered at once (at least 1).
    pub jobs: usize,
    /// Skip a project whose video is at least as new as its project.json.
    pub skip_existing: bool,
    /// Start no new renders after the first failure.
    pub fail_fast: bool,
}

#[derive(Debug, Serialize)]
pub(crate) struct ItemReport {
    pub project: PathBuf,
    pub output: PathBuf,
    /// rendered, skipped, failed or not_run
    pub status: &'static str,
    pub duration_seconds: Option<f64>,
    pub error: Option<String>,
}

#[derive(Debug, Serialize)]
pub(crate) struct BatchReport {
    pub rendered: usize,
    pub skipped: usize,
    pub failed: usize,
    pub not_run: usize,
    pub items: Vec<ItemReport>,
}

impl BatchReport {
    pub(crate) fn ok(&self) -> bool {
        self.failed == 0
    }
}

/// The projects `source` names: a folder (every `*.project.json` in it, sorted)
/// or a manifest. A manifest is an array of entries, or `{"projects": [...]}`;
/// an entry is a path, or `{"project", "output"?, "burn_subtitles"?}`. Relative
/// paths in a manifest are relative to the manifest's folder.
pub(crate) fn collect(source: &Path) -> Result<Vec<Item>> {
    if source.is_dir() {
        let mut found: Vec<PathBuf> = std::fs::read_dir(source)
            .with_context(|| format!("reading {}", source.display()))?
            .filter_map(|entry| entry.ok().map(|entry| entry.path()))
            .filter(|path| {
                path.file_name()
                    .is_some_and(|name| name.to_string_lossy().ends_with(".project.json"))
            })
            .collect();
        found.sort();
        if found.is_empty() {
            bail!("no *.project.json in {}", source.display());
        }
        return Ok(found
            .into_iter()
            .map(|project| Item {
                project,
                output: None,
                burn_subtitles: None,
            })
            .collect());
    }

    let text = std::fs::read_to_string(source)
        .with_context(|| format!("reading {}", source.display()))?;
    let manifest: Manifest =
        serde_json::from_str(&text).with_context(|| format!("parsing {}", source.display()))?;
    let entries = match manifest {
        Manifest::List(list) => list,
        Manifest::Wrapped { projects } => projects,
    };
    if entries.is_empty() {
        bail!("{} lists no projects", source.display());
    }
    let base = source.parent().unwrap_or(Path::new(""));
    Ok(entries
        .into_iter()
        .map(|entry| match entry {
            Entry::Path(project) => Item {
                project: base.join(project),
                output: None,
                burn_subtitles: None,
            },
            Entry::Detailed {
                project,
                output,
                burn_subtitles,
            } => Item {
                project: base.join(project),
                output: output.map(|output| base.join(output)),
                burn_subtitles,
            },
        })
        .collect())
}

/// The video a project renders to: its own output, else `output_dir`, else beside it.
fn output_for(item: &Item, options: &Options) -> PathBuf {
    if let Some(output) = &item.output {
        return output.clone();
    }
    let default = lesson::default_output(&item.project);
    match &options.output_dir {
        Some(dir) => dir.join(
            default
                .file_name()
                .unwrap_or(std::ffi::OsStr::new("output.mp4")),
        ),
        None => default,
    }
}

fn up_to_date(project: &Path, output: &Path) -> bool {
    let modified = |path: &Path| std::fs::metadata(path).and_then(|m| m.modified()).ok();
    match (modified(project), modified(output)) {
        (Some(project), Some(output)) => output >= project,
        _ => false,
    }
}

fn render_one(item: &Item, options: &Options) -> ItemReport {
    let output = output_for(item, options);
    let mut report = ItemReport {
        project: item.project.clone(),
        output: output.clone(),
        status: "failed",
        duration_seconds: None,
        error: None,
    };
    if options.skip_existing && up_to_date(&item.project, &output) {
        report.status = "skipped";
        return report;
    }
    let outcome = lesson::parse_codec(Some(&options.codec)).and_then(|codec| {
        let choices = RenderChoices {
            codec,
            burn_subtitles: item.burn_subtitles.unwrap_or(options.burn_subtitles),
            fonts: options.fonts.clone(),
        };
        lesson::render_project(&item.project, Some(&output), choices, |_| {})
    });
    match outcome {
        Ok(done) => {
            report.status = "rendered";
            report.duration_seconds = Some(done.duration_seconds);
        }
        Err(error) => report.error = Some(format!("{error:#}")),
    }
    report
}

/// Renders `items` with `options.jobs` workers. Progress goes to stderr, one line per project.
pub(crate) fn run(items: Vec<Item>, options: &Options) -> BatchReport {
    let total = items.len();
    let workers = options.jobs.clamp(1, total.max(1));
    let next = AtomicUsize::new(0);
    let finished = AtomicUsize::new(0);
    let stop = AtomicBool::new(false);
    let slots: Mutex<Vec<Option<ItemReport>>> = Mutex::new((0..total).map(|_| None).collect());

    std::thread::scope(|scope| {
        for _ in 0..workers {
            scope.spawn(|| {
                loop {
                    if stop.load(Ordering::SeqCst) {
                        break;
                    }
                    let index = next.fetch_add(1, Ordering::SeqCst);
                    if index >= total {
                        break;
                    }
                    let report = render_one(&items[index], options);
                    if options.fail_fast && report.status == "failed" {
                        stop.store(true, Ordering::SeqCst);
                    }
                    let n = finished.fetch_add(1, Ordering::SeqCst) + 1;
                    eprintln!("[{n}/{total}] {} {}", report.status, report.project.display());
                    slots.lock().expect("batch results lock")[index] = Some(report);
                }
            });
        }
    });

    let reports: Vec<ItemReport> = slots
        .into_inner()
        .expect("batch results lock")
        .into_iter()
        .enumerate()
        .map(|(index, slot)| {
            slot.unwrap_or_else(|| ItemReport {
                project: items[index].project.clone(),
                output: output_for(&items[index], options),
                status: "not_run",
                duration_seconds: None,
                error: None,
            })
        })
        .collect();
    let count = |status: &str| reports.iter().filter(|r| r.status == status).count();
    BatchReport {
        rendered: count("rendered"),
        skipped: count("skipped"),
        failed: count("failed"),
        not_run: count("not_run"),
        items: reports,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manifest_accepts_list_and_wrapped_forms() {
        let dir = std::env::temp_dir().join(format!("opencut-batch-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let list = dir.join("list.json");
        std::fs::write(&list, r#"["a.project.json", {"project": "b.project.json", "output": "out/b.mp4", "burn_subtitles": true}]"#).unwrap();
        let items = collect(&list).unwrap();
        assert_eq!(items[0].project, dir.join("a.project.json"));
        assert_eq!(items[1].output, Some(dir.join("out/b.mp4")));
        assert_eq!(items[1].burn_subtitles, Some(true));

        let wrapped = dir.join("wrapped.json");
        std::fs::write(&wrapped, r#"{"projects": ["c.project.json"]}"#).unwrap();
        assert_eq!(collect(&wrapped).unwrap()[0].project, dir.join("c.project.json"));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn folder_collects_only_project_files_sorted() {
        let dir = std::env::temp_dir().join(format!("opencut-batch-dir-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        for name in ["b.project.json", "a.project.json", "a.markers.json", "notes.txt"] {
            std::fs::write(dir.join(name), "{}").unwrap();
        }
        let items = collect(&dir).unwrap();
        let names: Vec<_> = items
            .iter()
            .map(|i| i.project.file_name().unwrap().to_string_lossy().into_owned())
            .collect();
        assert_eq!(names, ["a.project.json", "b.project.json"]);
        std::fs::remove_dir_all(&dir).ok();
    }
}
