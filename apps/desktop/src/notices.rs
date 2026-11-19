//! Third-party notices shown in the app (Inspector panel) and kept in sync
//! with `NOTICES.md` at the repository root.

pub(crate) const OPENH264_TITLE: &str = "OpenH264 Video Codec provided by Cisco Systems, Inc.";

pub(crate) const OPENH264_BODY: &str = "H.264 video is encoded with Cisco's OpenH264 module. \
OpenCut does not ship it: Cisco's own binary is downloaded from Cisco when the media libraries are \
set up, and Cisco pays the H.264 patent royalties for that binary only. Builds of OpenH264 from \
source, or other H.264 encoders, are not covered by Cisco's payment. \
OpenH264 source is BSD-2-Clause; the binary is under Cisco's OpenH264 binary licence \
(https://www.openh264.org/BINARY_LICENSE.txt).";

pub(crate) const FFMPEG_NOTICE: &str =
    "FFmpeg is used as shared libraries under the LGPL 2.1 or later. See COPYING.LGPLv2.1 and BUILD.md beside the libraries.";
