# OpenCut CLI

`opencut` runs OpenCut's media engine (`crates/media`) without a window:
for scripts and batch jobs, and as an [MCP](https://modelcontextprotocol.io)
server so AI agents can inspect and look at video.

```sh
moon run media:setup                 # once: the pinned FFmpeg build
cargo build -p opencut-cli --release # target/release/opencut
```

## Commands

```sh
opencut probe clip.mp4                          # container, duration, streams as JSON
opencut frame clip.mp4 -t 12.5 -o frame.png     # the frame on screen at 12.5 s
opencut frame clip.mp4 -t 3 -o small.png --max-size 640
opencut thumbnails clip.mp4 -n 8 -o thumbs/     # 8 frames spread over the clip
opencut mcp                                     # MCP server on stdio
```

## MCP server

| Tool | What it does |
|---|---|
| `probe_media` | Container, duration, bit rate, video/audio streams (structured JSON). |
| `extract_frame` | The frame at a time, as a PNG image (and optionally saved to a file). |
| `generate_thumbnails` | Up to 48 frames spread over the video, as images or saved PNGs. |

Paths are on the machine running the server. Media errors (missing file,
time past the end) come back as tool errors the agent can read.

Claude Code:

```sh
claude mcp add opencut -- /absolute/path/to/target/release/opencut mcp
```

Other clients (`mcpServers` JSON):

```json
{
  "mcpServers": {
    "opencut": { "command": "/absolute/path/to/target/release/opencut", "args": ["mcp"] }
  }
}
```

The binary finds FFmpeg through an rpath baked in at build time (Linux,
macOS), so it runs straight from `target/`. On Windows, put the DLLs from
`.cache/media/current/bin` next to it or on `PATH`.
