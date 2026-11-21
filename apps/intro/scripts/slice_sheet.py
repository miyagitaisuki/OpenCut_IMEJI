#!/usr/bin/env python3
"""Cut chibi pose sheets into one transparent PNG per pose, all on the same
canvas with the feet in the same place, and write the avatar's `poses` map.

  python scripts/slice_sheet.py public/avatars/izumi \
      --sheet a=sheetA.png --sheet b=sheetB.png --cols 4 --rows 3 \
      --names scripts/chibi_names.json

Each sheet is a plain grid on a white background (cols x rows, left to right,
top to bottom). Poses are written to `<folder>/pose_<sheet><NN>.png` and the
manifest `<folder>/avatar.json` gets `poses` (name -> file) and `size`.
`--names` is an optional JSON {"a01": "think_chin", ...}; unnamed poses keep
their id. Sheets should be as large as you can get (>= 2000 px wide): the
video draws the character about 1000 px tall.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def cut_background(sheet: Image.Image) -> Image.Image:
    """White background -> transparent, flood-filled from the borders so white
    inside the character (shirt, eye highlights) survives."""
    rgb = sheet.convert("RGB")
    w, h = rgb.size
    marker = (255, 0, 255)
    work = rgb.copy()
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    # Also seed along the top/bottom edges: poses never touch them.
    seeds += [(x, 0) for x in range(0, w, max(1, w // 40))]
    seeds += [(x, h - 1) for x in range(0, w, max(1, w // 40))]
    for s in seeds:
        if work.getpixel(s) != marker:
            ImageDraw.floodfill(work, s, marker, thresh=48)
    arr = np.asarray(work)
    bg = (arr[..., 0] == 255) & (arr[..., 1] == 0) & (arr[..., 2] == 255)
    alpha = Image.fromarray(np.where(bg, 0, 255).astype("uint8"))
    # Soften the cut a little so the edge is not jagged.
    alpha = alpha.filter(ImageFilter.GaussianBlur(max(0.5, w / 3000)))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def find_poses(sheet: Image.Image, count: int, rows: int):
    """The poses on a cut-out sheet, in reading order, as (box, cropped image).
    Found as connected blobs (not a fixed grid), so a pose may touch its cell edge."""
    from scipy import ndimage

    alpha = np.asarray(sheet.getchannel("A")) > 20
    grow = 1
    blobs, n = ndimage.label(ndimage.binary_dilation(alpha, iterations=grow))
    found = []
    for i, sl in enumerate(ndimage.find_objects(blobs), 1):
        area = int(((blobs[sl] == i) & alpha[sl]).sum())
        found.append((area, sl))
    found.sort(key=lambda t: -t[0])
    found = found[:count]
    if len(found) != count:
        print(f"warning: expected {count} poses, found {len(found)}", file=sys.stderr)
    boxes = [(sl[1].start, sl[0].start, sl[1].stop, sl[0].stop) for _, sl in found]
    # Reading order: split into `rows` bands by vertical centre, then by x.
    boxes.sort(key=lambda b: b[1] + b[3])
    per = max(1, round(len(boxes) / rows))
    ordered = []
    for r in range(0, len(boxes), per):
        ordered += sorted(boxes[r:r + per], key=lambda b: b[0])
    out = []
    for box in ordered:
        crop = sheet.crop(box)
        # Drop neighbours' pixels that fall inside this box.
        out.append((box, crop))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--sheet", action="append", required=True, help="id=path, e.g. a=sheetA.png")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--names", type=Path)
    ap.add_argument("--height", type=int, default=2000, help="canvas height")
    args = ap.parse_args()

    names = json.loads(args.names.read_text("utf-8")) if args.names else {}
    cells = []  # (id, image cropped to its content, foot-centre x within crop)
    for spec in args.sheet:
        sid, _, path = spec.partition("=")
        sheet = cut_background(Image.open(path))
        for n, (box, crop) in enumerate(find_poses(sheet, args.cols * args.rows, args.rows), 1):
            a = np.asarray(crop.getchannel("A")) > 20
            # Anchor on the legs/skirt (lowest quarter): arms swing, feet do not.
            low = a[int(a.shape[0] * 0.75):]
            cols = np.where(low.any(axis=0))[0]
            foot_x = float(cols.mean()) if len(cols) else crop.width / 2
            cells.append((f"{sid}{n:02d}", crop, foot_x))

    if not cells:
        print("no poses found", file=sys.stderr)
        return 1

    # One scale for all poses (median height -> ~92% of the canvas), so size
    # does not jump when the pose changes.
    target = args.height * 0.92
    scale = target / statistics.median(c.height for _, c, _ in cells)
    scaled = []
    for pid, crop, fx in cells:
        nw, nh = max(1, round(crop.width * scale)), max(1, round(crop.height * scale))
        scaled.append((pid, crop.resize((nw, nh), Image.LANCZOS), fx * scale))
    half = max(max(fx, img.width - fx) for _, img, fx in scaled)
    cw = int(half * 2 + args.height * 0.04) // 2 * 2
    ch = args.height
    margin = round(ch * 0.02)

    args.folder.mkdir(parents=True, exist_ok=True)
    poses = {}
    for pid, img, fx in scaled:
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        canvas.alpha_composite(img, (round(cw / 2 - fx), ch - margin - img.height))
        fname = f"pose_{pid}.png"
        canvas.save(args.folder / fname)
        poses[names.get(pid, pid)] = fname

    manifest_path = args.folder / "avatar.json"
    manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else {"name": args.folder.name}
    manifest["size"] = [cw, ch]
    manifest["poses"] = poses
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"{len(poses)} poses, canvas {cw}x{ch}, scale x{scale:.2f} -> {args.folder}")
    if scale > 4:
        print("note: heavy upscaling; get higher-resolution sheets for a sharp video", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
