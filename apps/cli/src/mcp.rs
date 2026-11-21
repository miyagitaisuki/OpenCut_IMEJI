//! MCP server: lets an AI agent inspect and look at media, and build and
//! render lesson videos from what textts makes.
//!
//! Decoding is blocking work, so every tool runs it on Tokio's blocking
//! pool and the server keeps answering while a long seek runs.

use std::path::PathBuf;

use base64::Engine;
use opencut_media::{PixelFormat, VideoDecoder, probe, thumbnails};
use rmcp::{
    ErrorData, ServerHandler, ServiceExt,
    handler::server::{router::tool::ToolRouter, wrapper::Parameters},
    model::{CallToolResult, ContentBlock},
    schemars::JsonSchema,
    tool, tool_handler, tool_router,
    transport::stdio,
};
use serde::Deserialize;

/// Images sent back to the agent stay small: they cost context.
const DEFAULT_FRAME_SIZE: u32 = 768;
const DEFAULT_THUMBNAIL_SIZE: u32 = 320;
const MAX_THUMBNAILS: usize = 48;

#[derive(Deserialize, JsonSchema)]
#[schemars(crate = "rmcp::schemars")]
struct ProbeParams {
    /// Path of the media file.
    path: PathBuf,
}

#[derive(Deserialize, JsonSchema)]
#[schemars(crate = "rmcp::schemars")]
struct MascotParams {
    /// Path of the project.json.
    project: PathBuf,
    /// Avatar folder with avatar.json and a `poses` map (e.g. apps/intro/public/avatars/izumi). Needed the first time.
    avatar: Option<PathBuf>,
    /// bottom-right (default) or bottom-left.
    corner: Option<String>,
    /// Height as a fraction of the picture (default 0.55).
    height: Option<f64>,
    /// Take the mascot out of the project.
    remove: Option<bool>,
}

#[derive(Deserialize, JsonSchema)]
#[schemars(crate = "rmcp::schemars")]
struct FrameParams {
    /// Path of the video file.
    path: PathBuf,
    /// Time in seconds from the start.
    time_seconds: f64,
    /// Longest side of the image in pixels (default 768). Never scaled up.
    max_size: Option<u32>,
    /// Also save the frame as a PNG here.
    output_path: Option<PathBuf>,
}

#[derive(Deserialize, JsonSchema)]
#[schemars(crate = "rmcp::schemars")]
struct ThumbnailsParams {
    /// Path of the video file.
    path: PathBuf,
    /// How many frames, spread evenly over the video (default 6, at most 48).
    count: Option<usize>,
    /// Longest side of each image in pixels (default 320).
    max_size: Option<u32>,
    /// Save the frames as PNGs in this directory instead of returning them as images.
    output_dir: Option<PathBuf>,
}

#[derive(Deserialize, JsonSchema)]
#[schemars(crate = "rmcp::schemars")]
struct QcParams {
    /// Path of the project.json to check.
    project: PathBuf,
    /// Whisper's words file (`lesson.ts words` writes it). Without it the pronunciation check is skipped and reported as unchecked.
    words: Option<PathBuf>,
    /// Folder of scene stills (`lesson.ts preview`). Without it the layout check is skipped and reported as unchecked.
    stills: Option<PathBuf>,
    /// Teach textts the readings of the engine's suspect lines (they apply only after the voice is made again).
    fix_readings: Option<bool>,
}

#[derive(Deserialize, JsonSchema)]
#[schemars(crate = "rmcp::schemars")]
struct ProjectParams {
    /// Path of the project.json.
    project: PathBuf,
}

#[derive(Deserialize, JsonSchema)]
#[schemars(crate = "rmcp::schemars")]
struct RenderBatchParams {
    /// A folder of *.project.json files, or a manifest .json: an array of
    /// project paths or {"projects": [...]}; an entry is a path or
    /// {"project", "output"?, "burn_subtitles"?}.
    source: PathBuf,
    /// Folder for the videos; default beside each project.
    output_dir: Option<PathBuf>,
    /// Projects rendered at once; default 1.
    jobs: Option<usize>,
    /// auto, h264 or mpeg4. Default auto.
    codec: Option<String>,
    /// Draw the subtitles into the picture. Default false.
    burn_subtitles: Option<bool>,
    /// Font files for burned-in subtitles.
    fonts: Option<Vec<PathBuf>>,
    /// Skip projects whose video is at least as new as their project.json.
    skip_existing: Option<bool>,
    /// Start no new renders after the first failure.
    fail_fast: Option<bool>,
}

#[derive(Deserialize, JsonSchema)]
#[schemars(crate = "rmcp::schemars")]
struct RenderParams {
    /// Path of the project.json.
    project: PathBuf,
    /// Video to write; defaults to the project's name with .mp4.
    output: Option<PathBuf>,
    /// auto (H.264 when this FFmpeg has it, else MPEG-4), h264 or mpeg4.
    codec: Option<String>,
    /// Draw the subtitles (furigana and translation included) into the
    /// picture, for YouTube and other players without ruby. Default false.
    burn_subtitles: Option<bool>,
    /// Font files for burned-in subtitles; the system's Japanese fonts by default.
    fonts: Option<Vec<PathBuf>>,
}

#[derive(Clone)]
pub(crate) struct OpenCut {
    tool_router: ToolRouter<Self>,
}

#[tool_router]
impl OpenCut {
    fn new() -> Self {
        Self {
            tool_router: Self::tool_router(),
        }
    }

    #[tool(
        description = "Read a media file's container, duration, bit rate and streams (video size, frame rate, codecs; audio sample rate and channels) without decoding it.",
        annotations(read_only_hint = true)
    )]
    async fn probe_media(
        &self,
        Parameters(params): Parameters<ProbeParams>,
    ) -> Result<CallToolResult, ErrorData> {
        respond(
            async {
                let info = blocking(move || probe(&params.path).map_err(failure)).await?;
                Ok(CallToolResult::structured(
                    serde_json::to_value(&info).map_err(failure)?,
                ))
            }
            .await,
        )
    }

    #[tool(
        description = "Decode the video frame showing at a time and return it as a PNG image, to see what is on screen there. Optionally also save it to a file."
    )]
    async fn extract_frame(
        &self,
        Parameters(params): Parameters<FrameParams>,
    ) -> Result<CallToolResult, ErrorData> {
        respond(Self::frame(params).await)
    }

    #[tool(
        description = "Sample frames spread evenly over a video, to get an overview of its content. Returns them as PNG images, or saves them to output_dir and returns the file paths."
    )]
    async fn generate_thumbnails(
        &self,
        Parameters(params): Parameters<ThumbnailsParams>,
    ) -> Result<CallToolResult, ErrorData> {
        respond(Self::thumbnails(params).await)
    }

    #[tool(
        description = "Build a lesson project (project.json) from what textts made for a dialogue: its audio, .srt subtitles (speaker roles from .timeline.json) and scene markers, with slide images spread over scenes or lines. Returns the project's duration and any problems that would stop rendering."
    )]
    async fn import_textts(
        &self,
        Parameters(request): Parameters<crate::lesson::ImportRequest>,
    ) -> Result<CallToolResult, ErrorData> {
        respond(json(
            blocking(move || crate::lesson::import(&request).map_err(chain)).await,
        ))
    }

    #[tool(
        description = "Put a chibi mascot in a corner of a lesson project, changing pose with each subtitle sentence (poses picked from what is said: greeting, question, praise, thanks...). Run it after import_textts (and after any intro/outro, which shift the timeline), then render_project. Burned-in subtitles keep clear of her. Returns how many poses were set."
    )]
    async fn set_mascot(
        &self,
        Parameters(params): Parameters<MascotParams>,
    ) -> Result<CallToolResult, ErrorData> {
        respond(json(
            blocking(move || {
                crate::lesson::set_mascot(
                    &params.project,
                    params.avatar,
                    params.corner.as_deref(),
                    params.height,
                    params.remove.unwrap_or(false),
                )
                .map_err(chain)
            })
            .await,
        ))
    }

    #[tool(
        description = "Check a project.json: its duration, counts, and every problem (missing files, bad times, bad canvas) that would stop it rendering.",
        annotations(read_only_hint = true)
    )]
    async fn check_project(
        &self,
        Parameters(params): Parameters<ProjectParams>,
    ) -> Result<CallToolResult, ErrorData> {
        respond(json(
            blocking(move || crate::lesson::check(&params.project).map_err(chain)).await,
        ))
    }

    #[tool(
        description = "Quality check of a lesson project.json before rendering: the voice against the furigana (AivisSpeech), Whisper's transcript against the text (pronunciation, needs words), and text outside the safe area (layout, needs stills). Returns ok, each check's counts, and an issue list: line numbers, the text, what was heard or read, and the fix to make. Fix the furigana or wording in project.json, run it again, and render only when ok is true. unchecked lists checks that could not run; they are not passes.",
        annotations(read_only_hint = true)
    )]
    async fn qc_project(
        &self,
        Parameters(params): Parameters<QcParams>,
    ) -> Result<CallToolResult, ErrorData> {
        respond(json(blocking(move || run_qc(params)).await))
    }

    #[tool(
        description = "Render many lesson projects in one run: a folder of *.project.json or a manifest listing them. Renders one at a time unless jobs is set. skip_existing leaves out projects whose video is newer than their project.json; a failed project does not stop the others unless fail_fast. Returns counts (rendered, skipped, failed, not_run) and one entry per project with its status, output, duration or error. Takes about as long as the total video length on a laptop."
    )]
    async fn render_batch(
        &self,
        Parameters(params): Parameters<RenderBatchParams>,
    ) -> Result<CallToolResult, ErrorData> {
        respond(json(
            blocking(move || {
                let items = crate::batch::collect(&params.source).map_err(chain)?;
                let options = crate::batch::Options {
                    output_dir: params.output_dir,
                    codec: params.codec.unwrap_or_else(|| "auto".into()),
                    burn_subtitles: params.burn_subtitles.unwrap_or(false),
                    fonts: params.fonts.unwrap_or_default(),
                    jobs: params.jobs.unwrap_or(1),
                    skip_existing: params.skip_existing.unwrap_or(false),
                    fail_fast: params.fail_fast.unwrap_or(false),
                };
                Ok::<_, Failure>(crate::batch::run(items, &options))
            })
            .await,
        ))
    }

    #[tool(
        description = "Submit a lesson to the lesson job server (scripts/lesson_jobs.py serve): from QBank question ids, a QBank chapter, or a script_path under lessons/. The job builds the voice, the scenes and the video, then waits for a person to review it. It never uploads. Returns the job id and status."
    )]
    async fn submit_lesson_job(
        &self,
        Parameters(params): Parameters<SubmitLessonParams>,
    ) -> Result<CallToolResult, ErrorData> {
        respond(json(
            blocking(move || {
                let mut body = serde_json::Map::new();
                if let Some(name) = params.name {
                    body.insert("name".into(), name.into());
                }
                if let Some(questions) = params.questions {
                    body.insert("questions".into(), questions.into());
                }
                if let Some(chapter) = params.chapter {
                    body.insert("chapter".into(), chapter.into());
                }
                if let Some(script_path) = params.script_path {
                    body.insert("script_path".into(), script_path.into());
                }
                if let Some(title) = params.title {
                    body.insert("title".into(), title.into());
                }
                if let Some(level) = params.level {
                    body.insert("level".into(), level.into());
                }
                if params.dry_run.unwrap_or(false) {
                    body.insert("dry_run".into(), true.into());
                }
                crate::jobs_client::request("POST", "/jobs", Some(&serde_json::Value::Object(body)))
                    .map_err(failure)
            })
            .await,
        ))
    }

    #[tool(
        description = "Status of one lesson job: status (queued, running, quarantine, awaiting_approval, done, failed, cancelled...), the error if any, each stage's status, and the QC status and warnings. Read-only."
    )]
    async fn get_job_status(
        &self,
        Parameters(params): Parameters<JobIdParams>,
    ) -> Result<CallToolResult, ErrorData> {
        respond(json(
            blocking(move || {
                let job = crate::jobs_client::request("GET", &format!("/jobs/{}", params.job_id), None)
                    .map_err(failure)?;
                Ok::<_, Failure>(job_summary(&job))
            })
            .await,
        ))
    }

    #[tool(
        description = "Lesson jobs waiting for a person: status quarantine (the scenes or the engine check still fail after the automatic rebuilds). Each has its error. Read-only; to continue a job the person has reviewed, use the job server's accept route, not this tool."
    )]
    async fn list_quarantine(&self) -> Result<CallToolResult, ErrorData> {
        respond(json(
            blocking(move || {
                let jobs = crate::jobs_client::request("GET", "/jobs", None).map_err(failure)?;
                let items: Vec<serde_json::Value> = jobs
                    .as_array()
                    .map(|list| {
                        list.iter()
                            .filter(|job| job["status"] == "quarantine")
                            .map(job_summary)
                            .collect()
                    })
                    .unwrap_or_default();
                Ok::<_, Failure>(serde_json::json!({ "count": items.len(), "jobs": items }))
            })
            .await,
        ))
    }

    #[tool(
        description = "Render a project.json to a video (MP4 by default); burn_subtitles draws the subtitles with furigana and translation into the picture (for YouTube). Writes .vtt/.srt subtitles and .markers.json (scenes, chapters, question markers) beside it. Returns the output path, duration, codec and warnings. Takes about as long as the video on a laptop."
    )]
    async fn render_project(
        &self,
        Parameters(params): Parameters<RenderParams>,
    ) -> Result<CallToolResult, ErrorData> {
        respond(json(
            blocking(move || {
                let choices = crate::lesson::RenderChoices {
                    codec: crate::lesson::parse_codec(params.codec.as_deref()).map_err(chain)?,
                    burn_subtitles: params.burn_subtitles.unwrap_or(false),
                    fonts: params.fonts.unwrap_or_default(),
                };
                crate::lesson::render_project(
                    &params.project,
                    params.output.as_deref(),
                    choices,
                    |_| {},
                )
                .map_err(chain)
            })
            .await,
        ))
    }
}

/// A result as structured JSON content.
/// Runs `scripts/lesson_qc.py report`. Exit 1 means issues were found, which is an answer, not a failure:
/// the JSON on stdout is returned either way.
fn run_qc(params: QcParams) -> Result<serde_json::Value, Failure> {
    let repo = std::env::var_os("OPENCUT_REPO")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join(".."));
    let python = std::env::var("OPENCUT_PYTHON").unwrap_or_else(|_| "python".into());
    let mut command = std::process::Command::new(&python);
    command
        .arg(repo.join("scripts").join("lesson_qc.py"))
        .arg("report")
        .arg(&params.project);
    if let Some(words) = &params.words {
        command.arg("--words").arg(words);
    }
    if let Some(stills) = &params.stills {
        command.arg("--stills").arg(stills);
    }
    if params.fix_readings.unwrap_or(false) {
        command.arg("--fix");
    }
    let output = command
        .output()
        .map_err(|error| failure(format!("cannot run {python}: {error} (set OPENCUT_PYTHON)")))?;
    serde_json::from_slice(&output.stdout).map_err(|_| {
        failure(format!(
            "lesson_qc printed no report: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        ))
    })
}

fn json<T: serde::Serialize>(result: Result<T, Failure>) -> Result<CallToolResult, Failure> {
    Ok(CallToolResult::structured(
        serde_json::to_value(result?).map_err(failure)?,
    ))
}

/// An error with its causes, `outer: inner: â€¦`.
fn chain(error: anyhow::Error) -> Failure {
    Failure(format!("{error:#}"))
}

impl OpenCut {
    async fn frame(params: FrameParams) -> Result<CallToolResult, Failure> {
        let max_size = params.max_size.unwrap_or(DEFAULT_FRAME_SIZE);
        let (frame, png) = blocking(move || {
            let frame = VideoDecoder::open(&params.path, PixelFormat::Rgba, Some(max_size))
                .and_then(|mut decoder| decoder.frame_at(params.time_seconds))
                .map_err(failure)?;
            let png = frame.png_bytes().map_err(failure)?;
            if let Some(output) = &params.output_path {
                std::fs::write(output, &png)
                    .map_err(|error| failure(format!("writing {}: {error}", output.display())))?;
            }
            Ok((frame, png))
        })
        .await?;

        Ok(CallToolResult::success(vec![
            ContentBlock::text(format!(
                "{}x{} frame at {:.3}s",
                frame.width, frame.height, frame.seconds
            )),
            ContentBlock::image(
                base64::engine::general_purpose::STANDARD.encode(png),
                "image/png",
            ),
        ]))
    }

    async fn thumbnails(params: ThumbnailsParams) -> Result<CallToolResult, Failure> {
        let count = params.count.unwrap_or(6).clamp(1, MAX_THUMBNAILS);
        let max_size = params.max_size.unwrap_or(DEFAULT_THUMBNAIL_SIZE);

        if let Some(out_dir) = params.output_dir {
            let paths = blocking(move || {
                crate::save_thumbnails(&params.path, count, max_size, &out_dir)
                    .map_err(|error| failure(format!("{error:#}")))
            })
            .await?;
            let list = paths
                .iter()
                .map(|path| path.display().to_string())
                .collect::<Vec<_>>()
                .join("\n");
            return Ok(CallToolResult::success(vec![ContentBlock::text(list)]));
        }

        let frames = blocking(move || {
            thumbnails(&params.path, count, PixelFormat::Rgba, Some(max_size)).map_err(failure)
        })
        .await?;
        let mut content = Vec::with_capacity(frames.len() * 2);
        for frame in &frames {
            content.push(ContentBlock::text(format!("{:.3}s", frame.seconds)));
            let png = frame.png_bytes().map_err(failure)?;
            content.push(ContentBlock::image(
                base64::engine::general_purpose::STANDARD.encode(png),
                "image/png",
            ));
        }
        Ok(CallToolResult::success(content))
    }
}

#[tool_handler(
    router = self.tool_router,
    name = "opencut",
    instructions = "OpenCut: media tools and lesson video rendering. Paths are on the machine running the server; times are in seconds. To make a lesson video from textts output: import_textts, then optionally set_mascot (a chibi in the corner posing per sentence), then check_project, then render_project. probe_media, extract_frame and generate_thumbnails inspect any video, including a rendered one."
)]
impl ServerHandler for OpenCut {}

pub(crate) async fn serve() -> anyhow::Result<()> {
    let service = OpenCut::new().serve(stdio()).await?;
    service.waiting().await?;
    Ok(())
}

async fn blocking<T: Send + 'static>(
    work: impl FnOnce() -> Result<T, Failure> + Send + 'static,
) -> Result<T, Failure> {
    tokio::task::spawn_blocking(work).await.map_err(failure)?
}

/// Media problems (a wrong path, a time past the end) are tool errors, not
/// protocol errors: the agent sees FFmpeg's reason and can try again.
#[derive(Debug)]
struct Failure(String);

fn failure(error: impl ToString) -> Failure {
    Failure(error.to_string())
}

fn respond(result: Result<CallToolResult, Failure>) -> Result<CallToolResult, ErrorData> {
    Ok(result.unwrap_or_else(|Failure(message)| {
        CallToolResult::error(vec![ContentBlock::text(message)])
    }))
}

#[derive(Deserialize, JsonSchema)]
#[schemars(crate = "rmcp::schemars")]
struct SubmitLessonParams {
    /// Folder name under lessons/ (letters, digits, . _ -; max 64). Required with script_path only when no name can be derived.
    name: Option<String>,
    /// QBank question ids (one or more).
    questions: Option<Vec<i64>>,
    /// A QBank chapter id: every listening question in it.
    chapter: Option<i64>,
    /// A lesson script on disk under lessons/ or apps/ (the `[1] 日本語 // Tiếng Việt` format).
    script_path: Option<String>,
    /// Title shown on the video and the thumbnail.
    title: Option<String>,
    /// JLPT level: N5, N4, N3, N2 or N1 (sets the reading speed and the thumbnail badge).
    level: Option<String>,
    /// Stop after writing the textts script; no voice, no video.
    dry_run: Option<bool>,
}

#[derive(Deserialize, JsonSchema)]
#[schemars(crate = "rmcp::schemars")]
struct JobIdParams {
    /// The job id returned by submit_lesson_job.
    job_id: String,
}

/// The fields an agent needs from a job (the full record is large: QC histories, stage timings).
fn job_summary(job: &serde_json::Value) -> serde_json::Value {
    let stages: serde_json::Map<String, serde_json::Value> = job["stages"]
        .as_object()
        .map(|stages| {
            stages
                .iter()
                .map(|(name, info)| (name.clone(), info["status"].clone()))
                .collect()
        })
        .unwrap_or_default();
    serde_json::json!({
        "id": job["id"],
        "name": job["spec"]["name"],
        "status": job["status"],
        "error": job["error"],
        "stages": stages,
        "qc_status": job["outputs"]["qc_status"],
        "warnings": job["outputs"]["warnings"],
    })
}
