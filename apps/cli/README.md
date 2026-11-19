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

## Lesson videos from textts

```sh
# textts: python tts.py bai10.txt -o tt/bai10.mp3 --srt   (also writes tt/bai10.timeline.json)
opencut import-textts tt/bai10.mp3 --script bai10.txt \
  --slide slides/1.png --slide slides/2.png -o lesson/bai10.project.json
opencut check lesson/bai10.project.json
opencut render lesson/bai10.project.json        # lesson/bai10.mp4 (+ .vtt .srt .markers.json)
```

- **Subtitles** come from textts' `.srt`, matched to the timeline's line ids (`L001`…). With
  `--script` (the textts `.txt`, or a project `.json` saved with `--save-project`) they keep the
  script's furigana: `駅{えき}` becomes `<ruby>駅<rt>えき</rt></ruby>` in the `.vtt`, so HTML
  players show the reading above the kanji. The `.srt` has no ruby and shows `駅`.
- **Translations** after ` // ` in the script (or `translation` in a textts project) go under
  each line: Japanese on top, the translation on the next line (class `tr` in the `.vtt`,
  the second line in the `.srt`).
- **Slides** are spread one per scene (`[bgm=…]` in the script), one per line, or evenly.
- **Loudness**: the whole mix is brought to `loudness_lufs` in the project (-16 LUFS by
  default, `--loudness` to change it), never above -1 dBTP. The render report says what it measured.
- `project.json` is plain JSON (see `crates/project`): add Remotion intros/outros as
  `{"kind": "video", "path": "intro.mp4", "start": 0, "end": 5}` visuals, with the same file
  as an `audio` clip for its sound, and markers like `{"time": 42, "kind": "question", "ref": "qbank:123"}`.
- Without an H.264 encoder in the FFmpeg build, videos are MPEG-4 Part 2 (VLC plays them,
  browsers do not); the render report warns when that happens.

## MCP server

| Tool | What it does |
|---|---|
| `probe_media` | Container, duration, bit rate, video/audio streams (structured JSON). |
| `extract_frame` | The frame at a time, as a PNG image (and optionally saved to a file). |
| `generate_thumbnails` | Up to 48 frames spread over the video, as images or saved PNGs. |
| `import_textts` | Build a lesson `project.json` from textts output (audio, subtitles with furigana, scenes, slides). |
| `check_project` | Duration, counts and every problem that would stop a render. |
| `render_project` | Render to MP4 with `.vtt`/`.srt`/`.markers.json`; reports codec, loudness and warnings. |

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
