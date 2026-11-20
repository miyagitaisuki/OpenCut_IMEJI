#!/usr/bin/env python3
"""Measures H.264 encoders on one clip before any of them is made the default (standard library only).

For each encoder: wall time, output size, bitrate, and PSNR/SSIM against the source (the decoded
clip re-encoded as reference is the source itself, so the score says how much the encoder changed
it). Hardware encoders are listed only when ffmpeg has them; this script does not pick a winner.

  python scripts/bench_encoders.py lessons/demo-visuals/demo.mp4 --seconds 30
  python scripts/bench_encoders.py clip.mp4 --encoders libx264,h264_mf --bitrate 4M

Set OPENCUT_FFMPEG to the ffmpeg binary (default: the one on PATH).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def ffmpeg() -> str:
    exe = os.environ.get("OPENCUT_FFMPEG") or shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("ffmpeg not found: set OPENCUT_FFMPEG")
    return exe


def encoders(exe: str) -> set[str]:
    out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return {m.group(1) for m in re.finditer(r"^\s*V\S*\s+(\S+)", out, re.M)}


def run_encode(exe: str, src: Path, dst: Path, encoder: str, seconds: float, bitrate: str) -> float:
    args = [exe, "-y", "-hide_banner", "-loglevel", "error", "-t", str(seconds), "-i", str(src),
            "-map", "0:v:0", "-an", "-c:v", encoder, "-b:v", bitrate, "-pix_fmt", "yuv420p"]
    if encoder == "libx264":
        args += ["-preset", "medium"]
    args.append(str(dst))
    start = time.perf_counter()
    done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    elapsed = time.perf_counter() - start
    if done.returncode != 0:
        raise RuntimeError(f"{encoder}: {done.stderr.strip()[-400:]}")
    return elapsed


def quality(exe: str, reference: Path, encoded: Path, seconds: float) -> dict:
    """PSNR and SSIM of the encoded clip against the reference, both cut to `seconds`."""
    done = subprocess.run([exe, "-hide_banner", "-t", str(seconds), "-i", str(encoded), "-t", str(seconds),
                           "-i", str(reference), "-lavfi", "[0:v][1:v]psnr=stats_file=-;[0:v][1:v]ssim=stats_file=-",
                           "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = done.stderr
    psnr = re.findall(r"average:([\d.inf]+)", text)
    ssim = re.findall(r"All:([\d.]+)", text)
    return {"psnr_db": float(psnr[-1]) if psnr else None, "ssim": float(ssim[-1]) if ssim else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source")
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--bitrate", default="4M", help="target bitrate for every encoder")
    parser.add_argument("--encoders", default="libx264,libopenh264,h264_mf,h264_nvenc,h264_amf,h264_qsv",
                        help="comma-separated; only those ffmpeg has are run")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    exe = ffmpeg()
    have = encoders(exe)
    src = Path(args.source).resolve()
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in [e.strip() for e in args.encoders.split(",") if e.strip()]:
            if name not in have:
                results.append({"encoder": name, "skipped": "not in this ffmpeg build"})
                continue
            dst = Path(tmp) / f"{name}.mp4"
            try:
                seconds_taken = run_encode(exe, src, dst, name, args.seconds, args.bitrate)
            except RuntimeError as error:
                results.append({"encoder": name, "error": str(error)})
                continue
            size = dst.stat().st_size
            row = {"encoder": name, "seconds": round(seconds_taken, 2), "size_mb": round(size / 1e6, 2),
                   "kbps": round(size * 8 / 1000 / args.seconds), "realtime_x": round(args.seconds / seconds_taken, 2)}
            row.update(quality(exe, src, dst, args.seconds))
            results.append(row)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"{'encoder':14} {'time s':>7} {'x realtime':>10} {'kbps':>6} {'PSNR dB':>8} {'SSIM':>7}")
        for r in results:
            if "error" in r or "skipped" in r:
                print(f"{r['encoder']:14} {r.get('error', r.get('skipped'))}")
                continue
            print(f"{r['encoder']:14} {r['seconds']:7.2f} {r['realtime_x']:10.2f} {r['kbps']:6d} "
                  f"{str(r['psnr_db']):>8} {str(r['ssim']):>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
