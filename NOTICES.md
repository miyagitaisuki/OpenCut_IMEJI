# Third-party notices

## OpenH264 Video Codec provided by Cisco Systems, Inc.

H.264 video is encoded with Cisco's OpenH264 module. OpenCut does not ship
it: Cisco's own binary is downloaded from Cisco when the media libraries are
set up (`moon run media:setup`), and Cisco pays the H.264 patent royalties for
that binary only. Builds of OpenH264 from source, or other H.264 encoders, are
not covered by Cisco's payment.

- OpenH264 source: BSD-2-Clause, https://github.com/cisco/openh264
- Binary licence: https://www.openh264.org/BINARY_LICENSE.txt

## FFmpeg

Used as shared libraries under the LGPL 2.1 or later. The exact configure
flags (`BUILD.md`) and licence texts sit beside the libraries.

The same text is shown in the desktop app's Inspector panel
(`apps/desktop/src/notices.rs`).

## Turning H.264 off

H.264 export can be switched off: the **H.264 export** button in the desktop
app's Inspector, or `opencut h264 off` (`on` turns it back on, no argument
shows it). With it off, nothing asks FFmpeg for H.264: `opencut render` falls
back to MPEG-4 and `--codec h264` is refused. The setting is one file,
`settings.json` in the OpenCut config folder (`%APPDATA%\OpenCut` on Windows,
`$XDG_CONFIG_HOME/opencut` or `~/.config/opencut` on Linux), so the app, the
CLI and the MCP server agree.
