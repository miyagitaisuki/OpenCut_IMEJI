"""Cut an expression sheet laid out as a 5x2 grid into per-feature PNGs.

usage: python3 cut_grid.py SHEET OUTDIR CELL_W CELL_H [--origin X Y]
Each cell holds: brow_L, brow_R (upper band), eye_L, eye_R (middle band), mouth (lower band).
Names are from the character's view: viewer-left feature = R, viewer-right = L.
Expression order: row-major, E01..E10 (row 1 = E01..E05, row 2 = E06..E10).
"""
import sys, os, json
import numpy as np
from PIL import Image
from scipy import ndimage

NAMES = ['neutral','smile','happy','angry','sad','shy','surprised','worried','thinking','wink']
BANDS = {'brow': (0.0, 0.38), 'eye': (0.38, 0.62), 'mouth': (0.62, 1.0)}

def main():
    sheet, outdir, cw, ch = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    ox, oy = 0, 0
    if '--origin' in sys.argv:
        i = sys.argv.index('--origin'); ox, oy = int(sys.argv[i+1]), int(sys.argv[i+2])
    os.makedirs(outdir, exist_ok=True)
    im = Image.open(sheet).convert('RGB'); a = np.asarray(im).astype(np.float32)
    white = a.min(2) >= 235
    lab, _ = ndimage.label(white)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    fg = ~np.isin(lab, list(border))
    fg = ndimage.binary_opening(fg, iterations=1)
    rgba = np.dstack([a.astype(np.uint8), (fg * 255).astype(np.uint8)])
    manifest = {}
    for idx, name in enumerate(NAMES):
        r, c = divmod(idx, 5)
        x0, y0 = ox + c * cw, oy + r * ch
        cell_fg = fg[y0:y0+ch, x0:x0+cw]
        cell_rgba = rgba[y0:y0+ch, x0:x0+cw]
        mid = cw / 2
        parts = {}
        for band, (t0, t1) in BANDS.items():
            ys = slice(int(t0*ch), int(t1*ch))
            if band == 'mouth':
                masks = {'mouth': None}
            elif band == 'brow':
                masks = {'brow_R': None, 'brow_L': None}
            else:
                masks = {'eye_R': None, 'eye_L': None}
            band_fg = np.zeros_like(cell_fg); band_fg[ys] = cell_fg[ys]
            labs, n = ndimage.label(ndimage.binary_dilation(band_fg, iterations=3))
            for key in masks:
                parts[key] = None
            for i, sl in enumerate(ndimage.find_objects(labs), 1):
                m = (labs[sl] == i) & band_fg[sl]
                if m.sum() < 200: continue
                cx = (sl[1].start + sl[1].stop) / 2
                if band == 'mouth': key = 'mouth'
                elif band == 'brow': key = 'brow_R' if cx < mid else 'brow_L'
                else: key = 'eye_R' if cx < mid else 'eye_L'
                if parts.get(key) is None:
                    keep = np.zeros_like(band_fg); keep[sl] = m
                    parts[key] = (keep, sl)
        for key, val in parts.items():
            if val is None: continue
            keep, _ = val
            ys_, xs_ = np.where(keep)
            if len(xs_) == 0: continue
            box = (xs_.min(), ys_.min(), xs_.max()+1, ys_.max()+1)
            crop = cell_rgba[box[1]:box[3], box[0]:box[2]].copy()
            crop[..., 3] = np.where(keep[box[1]:box[3], box[0]:box[2]], crop[..., 3], 0)
            fname = f'E{idx+1:02d}_{name}_{key}.png'
            Image.fromarray(crop, 'RGBA').save(os.path.join(outdir, fname))
            manifest.setdefault(f'E{idx+1:02d}_{name}', {})[key] = [int(x0+box[0]), int(y0+box[1]), int(x0+box[2]), int(y0+box[3])]
    json.dump(manifest, open(os.path.join(outdir, 'manifest.json'), 'w'), indent=1, ensure_ascii=False)
    print('cells:', len(manifest), 'parts:', sum(len(v) for v in manifest.values()))

if __name__ == '__main__':
    main()
