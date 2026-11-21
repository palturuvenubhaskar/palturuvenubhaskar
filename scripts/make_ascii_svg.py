#!/usr/bin/env python3
"""
Turn the GitHub avatar into a monochrome ASCII portrait.

Two outputs:
  assets/ascii.json  -- the sampled grid, consumed by render_readme_cards.py
  assets/ascii.svg   -- standalone preview of the same portrait

Monochrome on purpose: one fill colour plus a density ramp reads as a clean
portrait; per-character colour turns it into noise.

The hero card re-emits these rows as a left-to-right clip wipe with a block
cursor riding the edge, staggered top to bottom, so the portrait prints once
and freezes.
"""

import html
import json
import os
import sys

import numpy as np
from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SRC = os.path.join(ROOT, "assets", "avatar.png")
JSON_OUT = os.path.join(ROOT, "assets", "ascii.json")
SVG_OUT = os.path.join(ROOT, "assets", "ascii.svg")

# more columns = more detail. the art stays ART_W px wide either way, cells
# shrink, keeping a ~1:1.875 character aspect.
COLS = int(os.environ.get("COLS", 110))
ART_W = 800.0
CELL_W = ART_W / COLS
CELL_H = CELL_W * 15 / 8
ROWS = round(COLS * 8 / 15)

RAMP = " .:-=+*#%@"
GAMMA = float(os.environ.get("GAMMA", 1.0))
FLOOR = float(os.environ.get("FLOOR", 0.13))   # luminance below this is background -> blank
CONTRAST = float(os.environ.get("CONTRAST", 1.15))

# tight crop around the head + subject-normalised inverted luminance
CROP = (0.20, 0.13, 0.88, 0.81)

# percentile normalisation on foreground pixels only (keeps face, drops background)
SUBJ_LO_P = 4     # lower percentile for foreground floor
SUBJ_HI_P = 96    # upper percentile for foreground ceiling
SUBJ_BLEND = 0.35 # 0 = fully normalised, 1 = raw luminance


def _subject_norm(arr, mask, lo_p=4, hi_p=96, blend=0.0):
    a = np.percentile(arr[mask], lo_p)
    b = np.percentile(arr[mask], hi_p)
    if b - a < 1e-3:
        return arr
    n = np.clip((arr - a) / (b - a), 0, 1)
    return n if blend <= 0 else (n * (1 - blend) + arr * blend)


def sample():
    im = Image.open(SRC).convert("L")
    w, h = im.size
    im = im.crop((int(w * CROP[0]), int(h * CROP[1]), int(w * CROP[2]), int(h * CROP[3])))
    im = im.resize((COLS, ROWS), Image.LANCZOS)
    arr = np.asarray(im).astype(np.float32) / 255.0

    # foreground mask from raw luminance (before normalisation)
    mask = arr > 0.10
    # keep largest blob to drop stray bright spots
    from collections import deque
    seen = np.zeros_like(mask, dtype=bool)
    best = np.zeros_like(mask)
    for sy in range(ROWS):
        for sx in range(COLS):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            q = deque([(sy, sx)])
            seen[sy, sx] = True
            cells = []
            while q:
                y, x = q.popleft()
                cells.append((y, x))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < ROWS and 0 <= nx < COLS and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            q.append((ny, nx))
            if len(cells) > best.sum():
                best = np.zeros_like(mask)
                for y, x in cells:
                    best[y, x] = True
    mask = best

    # percentile normalisation on subject only
    arr = _subject_norm(arr, mask, SUBJ_LO_P, SUBJ_HI_P, SUBJ_BLEND)

    # invert so dark face = dense chars on paper
    lines = []
    for y in range(ROWS):
        chars = []
        for x in range(COLS):
            if not mask[y, x]:
                chars.append(" ")
                continue
            v = 1.0 - arr[y, x]
            if v < FLOOR:
                chars.append(" ")
                continue
            idx = int(v * (len(RAMP) - 1) + 0.5)
            chars.append(RAMP[max(0, min(len(RAMP) - 1, idx))])
        lines.append("".join(chars))
    return lines


def write_json(lines):
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(
            {
                "cols": COLS,
                "rows": ROWS,
                "art_w": ART_W,
                "cell_w": CELL_W,
                "cell_h": CELL_H,
                "lines": lines,
            },
            f,
        )


def write_preview(lines):
    pad, title_h, status_h = 20, 30, 30
    art_h = ROWS * CELL_H
    cw, ch = ART_W + pad * 2, title_h + art_h + status_h + pad
    bg, bg2, frame, dim, ink = "#faf9f6", "#eeece6", "#d0cec6", "#6b7b8f", "#0b0f1a"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw:.0f}" height="{ch:.0f}" '
        f'viewBox="0 0 {cw:.0f} {ch:.0f}" role="img" aria-label="ASCII portrait">',
        f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{bg2}"/><stop offset="1" stop-color="{bg}"/></linearGradient></defs>',
        f'<rect width="{cw:.0f}" height="{ch:.0f}" rx="12" fill="url(#bg)"/>',
        f'<rect x=".5" y=".5" width="{cw - 1:.0f}" height="{ch - 1:.0f}" rx="12" fill="none" stroke="{frame}"/>',
        f'<line x1="0" y1="{title_h}" x2="{cw:.0f}" y2="{title_h}" stroke="{frame}"/>',
    ]
    for i, col in enumerate(["#1e3a8a", "#b45309", "#5b21b6"]):
        parts.append(f'<circle cx="{pad + i * 16}" cy="{title_h / 2}" r="5" fill="{col}"/>')
    parts.append(
        f'<text x="{cw / 2:.0f}" y="{title_h / 2 + 4}" fill="{dim}" font-size="12" '
        f'text-anchor="middle" font-family="monospace">venubhaskar@github: ~$ ./portrait.sh</text>'
    )

    top = title_h + pad * 0.35
    fs = CELL_H * 0.86
    for ry, line in enumerate(lines):
        y = top + ry * CELL_H + CELL_H * 0.74
        parts.append(
            f'<text xml:space="preserve" x="{pad}" y="{y:.1f}" fill="{ink}" font-size="{fs:.1f}" '
            f'textLength="{ART_W:.0f}" lengthAdjust="spacing">{html.escape(line)}</text>'
        )

    sy = title_h + art_h + pad * 0.35
    parts.append(f'<line x1="0" y1="{sy:.1f}" x2="{cw:.0f}" y2="{sy:.1f}" stroke="{frame}"/>')
    parts.append(
        f'<text x="{pad}" y="{sy + 19:.1f}" fill="{dim}" font-size="13" font-family="monospace">'
        f'venubhaskar@github:~$ whoami <tspan fill="{ink}">Palturu Venubhaskar</tspan></text>'
    )
    parts.append("</svg>")

    with open(SVG_OUT, "w", encoding="utf-8") as f:
        f.write("".join(parts))


if __name__ == "__main__":
    if not os.path.exists(SRC):
        print(f"missing {SRC}", file=sys.stderr)
        sys.exit(1)
    lines = sample()
    write_json(lines)
    write_preview(lines)
    print(f"wrote {JSON_OUT} and {SVG_OUT} ({COLS}x{ROWS})")
