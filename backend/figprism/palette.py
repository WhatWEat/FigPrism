"""OKLab clustering and OKLCH hue/lightness pairing (no generated substitute colors)."""

import numpy as np
from PIL import Image


def oklab(rgb):
    rgb = np.asarray(rgb, dtype=float) / 255
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    lms = (
        lin
        @ np.array(
            [
                [0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005],
            ]
        ).T
    )
    return (
        np.cbrt(lms)
        @ np.array(
            [
                [0.2104542553, 0.793617785, -0.0040720468],
                [1.9779984951, -2.428592205, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.808675766],
            ]
        ).T
    )


def hexcode(rgb):
    return "#" + "".join(f"{int(v):02X}" for v in rgb)


def extract_palette(image: Image.Image):
    im = image.convert("RGB").copy()
    im.thumbnail((180, 180))
    pixels = np.asarray(im).reshape(-1, 3)
    labs = oklab(pixels)
    chroma = np.linalg.norm(labs[:, 1:], axis=1)
    # Preserve pale scientific fills; pure white and neutral axes remain excluded.
    colored = (chroma > 0.025) | (
        (labs[:, 0] > 0.85) & (chroma > 0.015) & (labs[:, 0] < 0.96)
    )
    gray = pixels[(~colored) & (labs[:, 0] < 0.90)]
    neutral = []
    if len(gray):
        for q in (0.25, 0.75):
            g = np.quantile(gray, q, axis=0).astype(int)
            h = hexcode(g)
            if h not in neutral:
                neutral.append(h)
    p = pixels[colored]
    lab = labs[colored]
    if not len(p):
        return {"colors": [], "pairs": [], "neutrals": neutral, "buckets": []}
    # Quantize only to seed deterministic perceptual k-means.
    quant = (p // 16).astype(int)
    _, ix, counts = np.unique(quant, axis=0, return_index=True, return_counts=True)
    seeds = list(ix[np.argsort(-counts)[:1]])
    for _ in range(min(7, len(ix)) - 1):
        distance = np.min(
            np.sum((lab[ix, None, :] - lab[seeds][None, :, :]) ** 2, axis=2), axis=1
        )
        seeds.append(int(ix[np.argmax(distance * np.sqrt(counts))]))
    centers = lab[seeds]
    for _ in range(16):
        labels = np.argmin(
            np.sum((lab[:, None, :] - centers[None, :, :]) ** 2, axis=2), axis=1
        )
        new = np.array(
            [
                lab[labels == i].mean(axis=0) if np.any(labels == i) else centers[i]
                for i in range(len(centers))
            ]
        )
        if np.max(abs(new - centers)) < 0.0005:
            break
        centers = new
    colors = []
    for i, c in enumerate(centers):
        mask = labels == i
        if mask.sum() < max(8, len(p) * 0.012):
            continue
        rgb = np.median(p[mask], axis=0).astype(int)
        L, a, b = oklab(rgb)
        C = float(np.hypot(a, b))
        hue = float(np.degrees(np.arctan2(b, a)) % 360)
        colors.append(
            {
                "hex": hexcode(rgb),
                "rgb": rgb.tolist(),
                "weight": round(float(mask.mean()), 4),
                "l": float(L),
                "c": C,
                "h": hue,
            }
        )
    colors.sort(key=lambda c: -c["weight"])
    pairs = []
    for fill in colors:
        candidates = [
            s
            for s in colors
            if s["l"] < 0.65
            and fill["l"] > 0.78
            and fill["l"] - s["l"] > 0.18
            and min(abs(s["h"] - fill["h"]), 360 - abs(s["h"] - fill["h"])) <= 25
        ]
        if candidates:
            stroke = max(candidates, key=lambda s: s["weight"])
            pairs.append({"fill": fill["hex"], "stroke": stroke["hex"]})
    buckets = sorted(set(str(int(c["h"] // 30)) for c in colors))
    if np.mean([c["c"] for c in colors]) < 0.08:
        buckets.append("muted")
    if any(
        min(abs(a["h"] - b["h"]), 360 - abs(a["h"] - b["h"])) > 120
        for a in colors
        for b in colors
    ):
        buckets.append("contrast")
    return {
        "colors": colors[:6],
        "pairs": pairs[:4],
        "neutrals": neutral,
        "buckets": buckets,
    }
