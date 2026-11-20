#!/usr/bin/env python3
"""How much the music drops under the voice (auto-ducking), measured on a real clip (standard library only).

It runs the same music chain as `lesson_audio.py mix` twice, once with the voice as the sidechain key
(ducked) and once without (plain), then compares the music level in the frames where the voice speaks.

  python scripts/measure_ducking.py lessons/demo-visuals/demo.mp4 --seconds 60

Needs ffmpeg (OPENCUT_FFMPEG, else on PATH). Voice activity: 50 ms frames above -40 dBFS of the voice track.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lesson_audio  # noqa: E402

RATE = 16000
FRAME = int(RATE * 0.05)  # 50 ms
ACTIVE_DB = -40.0


def ffmpeg() -> str:
    exe = os.environ.get("OPENCUT_FFMPEG") or shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("ffmpeg not found: set OPENCUT_FFMPEG")
    return exe


def run(cmd: list[str]) -> None:
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise SystemExit(f"ffmpeg failed: {done.stderr.strip()[-400:]}")


def read_mono(path: Path) -> list[int]:
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return list(struct.unpack(f"<{len(raw) // 2}h", raw))


def frame_db(samples: list[int]) -> list[float]:
    """RMS in dBFS for each FRAME-sized chunk."""
    out = []
    for i in range(0, len(samples) - FRAME + 1, FRAME):
        chunk = samples[i:i + FRAME]
        rms = math.sqrt(sum(x * x for x in chunk) / FRAME) / 32768.0
        out.append(20 * math.log10(rms) if rms > 1e-9 else -120.0)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="a video or audio file with the voice")
    parser.add_argument("--bgm", help="music file (default: the generated pad, as lesson_audio uses)")
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    exe = ffmpeg()
    bgm = Path(args.bgm) if args.bgm else lesson_audio.BGM
    if not bgm.exists():
        lesson_audio.make()
    src = Path(args.source).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        voice = tmp / "voice.wav"
        ducked = tmp / "ducked.wav"
        plain = tmp / "plain.wav"
        run([exe, "-y", "-loglevel", "error", "-t", str(args.seconds), "-i", str(src), "-vn", "-ac", "1",
             "-ar", str(RATE), "-c:a", "pcm_s16le", str(voice)])
        music = lesson_audio.MUSIC_FILTER.format(music_db=0.0)
        base = ["-stream_loop", "-1", "-i", str(bgm), "-t", str(args.seconds), "-ac", "1", "-ar", str(RATE),
                "-c:a", "pcm_s16le"]
        run([exe, "-y", "-loglevel", "error", "-i", str(voice), *base[:2], "-i", str(bgm), "-t", str(args.seconds),
             "-filter_complex", f"[1:a]{music}[m];[m][0:a]{lesson_audio.DUCK_FILTER}[d]", "-map", "[d]",
             "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", str(ducked)])
        run([exe, "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(bgm), "-t", str(args.seconds),
             "-filter_complex", f"[0:a]{music}[m]", "-map", "[m]", "-ac", "1", "-ar", str(RATE),
             "-c:a", "pcm_s16le", str(plain)])

        v_db = frame_db(read_mono(voice))
        d_db = frame_db(read_mono(ducked))
        p_db = frame_db(read_mono(plain))

    n = min(len(v_db), len(d_db), len(p_db))
    active = [i for i in range(n) if v_db[i] > ACTIVE_DB]
    quiet = [i for i in range(n) if v_db[i] <= ACTIVE_DB]

    def mean_db(values: list[float], idx: list[int]) -> float:
        return sum(values[i] for i in idx) / len(idx) if idx else float("nan")

    result = {
        "source": str(src),
        "seconds": args.seconds,
        "voice_active_share": round(len(active) / n, 3) if n else None,
        "music_db_plain_while_voice": round(mean_db(p_db, active), 2),
        "music_db_ducked_while_voice": round(mean_db(d_db, active), 2),
        "reduction_db_while_voice": round(mean_db(p_db, active) - mean_db(d_db, active), 2),
        "reduction_db_in_pauses": round(mean_db(p_db, quiet) - mean_db(d_db, quiet), 2) if quiet else None,
        "note": "The target in lesson_audio is 18-24 dB; a smaller number means the music barely ducks.",
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for key, value in result.items():
            print(f"{key:30} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
