<table width="100%">
  <tr>
    <td align="left" width="120">
      <img src="https://assets.opencut.app/branding/symbol.svg" alt="OpenCut Logo" width="100" />
    </td>
    <td align="right">
      <h1>OpenCut IMEJI</h1>
      <h3 style="margin-top: -10px;">A headless video factory for Japanese lesson videos.</h3>
    </td>
  </tr>
</table>

[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat)](LICENSE)

## Scope

OpenCut IMEJI builds lesson videos from scripts and QBank questions, without a
window: textts voice, scenes, mascot, music, QC and a gated YouTube upload.
There is no GUI and no editor. The CLI (`opencut`) and the MCP server are the
interfaces.

The pipeline is described in [ROADMAP.md](ROADMAP.md). The current state and
the operating notes are in [lessons/HANDOFF_OpenCut_IMEJI.md](lessons/HANDOFF_OpenCut_IMEJI.md)
(local, git-ignored).

## Development

Install [proto](https://moonrepo.dev/proto) if you haven't already:

**Linux, macOS, WSL:**

```sh
bash <(curl -fsSL https://moonrepo.dev/install/proto.sh)
```

**Windows (PowerShell):**

```powershell
irm https://moonrepo.dev/install/proto.ps1 | iex
```

If shims fail to run, allow local scripts for your user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

From the repo root:

```sh
proto use                  # installs the tools pinned in .prototools
moon run cli:mcp           # MCP server for AI agents, see apps/cli/README.md
```

The Rust crates decode with the pinned FFmpeg in `crates/media`; their tasks run `moon run media:setup` first, which downloads it (or builds it from source) into `.cache/media/`.

For the whole pipeline in one container, see the `Dockerfile` and `compose.yaml`.

## Contributing

We're not set up to take outside contributions yet while the architecture is being designed. If you want to follow along, ask questions, or just hang out, [join the Discord](https://discord.gg/zmR9N35cjK) or [open an issue](https://github.com/opencut-app/opencut/issues).

## License

[MIT](LICENSE)
