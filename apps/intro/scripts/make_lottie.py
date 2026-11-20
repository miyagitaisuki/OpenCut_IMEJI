"""Writes the small Lottie stickers in public/lottie/ (check, cross, star). Plain shapes, no assets."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "public" / "lottie"
FR, END = 30, 60


def rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)] + [1]


def static(v):
    return {"a": 0, "k": v}


def anim(keys):
    """keys: [(frame, value)], eased out and in."""
    ks = []
    for i, (t, v) in enumerate(keys):
        k = {"t": t, "s": v}
        if i + 1 < len(keys):
            n = len(v)
            k["i"] = {"x": [0.34] * n, "y": [1.0] * n}
            k["o"] = {"x": [0.2] * n, "y": [0.0] * n}
        ks.append(k)
    return {"a": 1, "k": ks}


def tr():
    return {"ty": "tr", "p": static([0, 0]), "a": static([0, 0]), "s": static([100, 100]), "r": static(0), "o": static(100), "sk": static(0), "sa": static(0)}


def group(items):
    return {"ty": "gr", "it": items + [tr()], "nm": "g"}


def stroke(path, color, w, start, end):
    return group([
        {"ty": "sh", "ks": static({"i": [[0, 0]] * len(path), "o": [[0, 0]] * len(path), "v": path, "c": False})},
        {"ty": "tm", "s": static(0), "e": anim([(start, [0]), (end, [100])]), "o": static(0), "m": 1},
        {"ty": "st", "c": static(rgb(color)), "o": static(100), "w": static(w), "lc": 2, "lj": 2},
    ])


def disc(color):
    return group([{"ty": "el", "p": static([0, 0]), "s": static([170, 170])}, {"ty": "fl", "c": static(rgb(color)), "o": static(100)}])


def layer(shapes, scale_keys, rot=None):
    ks = {"o": static(100), "r": anim(rot) if rot else static(0), "p": static([100, 100, 0]), "a": static([0, 0, 0]), "s": anim(scale_keys)}
    return {"ddd": 0, "ind": 1, "ty": 4, "nm": "l", "sr": 1, "ks": ks, "ao": 0, "shapes": shapes, "ip": 0, "op": END, "st": 0, "bm": 0}


def lottie(name, layers):
    return {"v": "5.7.0", "fr": FR, "ip": 0, "op": END, "w": 200, "h": 200, "nm": name, "ddd": 0, "assets": [], "layers": layers}


pop = [(0, [0, 0, 100]), (10, [112, 112, 100]), (18, [100, 100, 100])]

check = lottie("check", [layer([stroke([[-38, 2], [-10, 30], [42, -28]], "#ffffff", 20, 14, 30), disc("#6fcaa5")], pop)])
cross = lottie("cross", [layer([stroke([[-28, -28], [28, 28]], "#ffffff", 20, 14, 24), stroke([[28, -28], [-28, 28]], "#ffffff", 20, 22, 32), disc("#f2859f")], pop)])


def star_points(r_out, r_in):
    import math
    pts = []
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = -math.pi / 2 + i * math.pi / 5
        pts.append([round(r * math.cos(a), 2), round(r * math.sin(a), 2)])
    return pts


star_shape = group([
    {"ty": "sh", "ks": static({"i": [[0, 0]] * 10, "o": [[0, 0]] * 10, "v": star_points(82, 38), "c": True})},
    {"ty": "fl", "c": static(rgb("#f6c444")), "o": static(100)},
    {"ty": "st", "c": static(rgb("#f0b94a")), "o": static(100), "w": static(8), "lc": 2, "lj": 2},
])
star = lottie("star", [layer([star_shape], [(0, [0, 0, 100]), (12, [125, 125, 100]), (22, [100, 100, 100])], rot=[(0, [-90]), (22, [0])])])

OUT.mkdir(parents=True, exist_ok=True)
for name, doc in {"check": check, "cross": cross, "star": star}.items():
    (OUT / f"{name}.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(name)
