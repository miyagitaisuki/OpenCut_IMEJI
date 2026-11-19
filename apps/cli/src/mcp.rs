//! MCP server: lets an AI agent inspect and look at media.
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
    instructions = "OpenCut's media tools. Paths are on the machine running the server. Times are in seconds from the start of the file. Call probe_media first to learn a file's duration."
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
