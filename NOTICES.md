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
