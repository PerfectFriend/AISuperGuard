#!/usr/bin/env python3
"""
SuperGuard Desktop - icon generator (eye + lightning bolt).

Draws the brand icon: a dark round background, a white almond-shaped eye
with a dark pupil, and a yellow lightning bolt inside the pupil.
Exports PNG (any size) and multi-size ICO.
"""
import math
import os
from PIL import Image, ImageDraw, ImageFilter

# Brand palette
BG_DARK = (10, 20, 45, 255)        # deep navy
BG_DARKER = (5, 10, 25, 255)       # near black
EYE_WHITE = (235, 242, 255, 255)
EYE_LINE = (15, 25, 55, 255)       # eyelid outline
PUPIL = (12, 16, 38, 255)          # pupil
BOLT = (255, 213, 0, 255)          # yellow lightning
BOLT_GLOW = (255, 236, 120, 255)
HIGHLIGHT = (255, 255, 255, 255)


def _radial_bg(size: int) -> Image.Image:
    """Dark navy radial-gradient background (round)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    r = size / 2
    steps = 60
    for i in range(steps, 0, -1):
        t = i / steps
        rad = r * (1.0 - (1.0 - t) * 0.12)
        col = tuple(int(BG_DARK[k] * t + BG_DARKER[k] * (1 - t)) for k in range(3)) + (255,)
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=col)
    # soft edge
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([2, 2, size - 2, size - 2], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(size / 64))
    img.putalpha(mask)
    return img


def _bolt_points(cx: float, cy: float, r: float) -> list:
    """Lightning bolt polygon inside a circle of radius r centered at (cx, cy)."""
    s = r
    return [
        (cx + 0.28 * s, cy - 0.95 * s),
        (cx - 0.18 * s, cy + 0.10 * s),
        (cx - 0.05 * s, cy + 0.10 * s),
        (cx - 0.30 * s, cy + 0.95 * s),
        (cx + 0.26 * s, cy - 0.08 * s),
        (cx + 0.12 * s, cy - 0.08 * s),
        (cx + 0.42 * s, cy - 0.95 * s),
    ]


def generate_icon(size: int = 256) -> Image.Image:
    """Generate the eye+lightning icon at the requested pixel size."""
    img = _radial_bg(size)
    d = ImageDraw.Draw(img)
    s = size / 256.0  # scale factor

    cx = cy = size / 2

    # --- eye (almond): ellipse with pointed sides via overlay mask ---
    rx, ry = 95 * s, 50 * s
    # almond mask: union of two offset circles (lens shape)
    almond = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ad = ImageDraw.Draw(almond)
    ad.ellipse([cx - rx, cy - ry, cx + rx * 0.55, cy + ry], fill=EYE_WHITE)
    ad.ellipse([cx - rx * 0.55, cy - ry, cx + rx, cy + ry], fill=EYE_WHITE)
    # smooth the lens
    almond = almond.filter(ImageFilter.GaussianBlur(size / 96))
    img.alpha_composite(almond)

    # eyelid outline
    d.ellipse([cx - rx, cy - ry, cx + rx * 0.55, cy + ry], outline=EYE_LINE, width=max(2, int(6 * s)))
    d.ellipse([cx - rx * 0.55, cy - ry, cx + rx, cy + ry], outline=EYE_LINE, width=max(2, int(6 * s)))

    # --- pupil ---
    pr = 40 * s
    d.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=PUPIL, outline=EYE_LINE, width=max(1, int(3 * s)))

    # --- lightning bolt ---
    d.polygon(_bolt_points(cx, cy, pr * 0.95), fill=BOLT)
    # small glow highlight
    d.polygon(_bolt_points(cx, cy - pr * 0.06, pr * 0.55), fill=BOLT_GLOW)

    # --- light reflection on the eye ---
    d.ellipse([cx - rx * 0.55, cy - ry * 0.45, cx - rx * 0.15, cy - ry * 0.05],
              fill=HIGHLIGHT)

    return img


def generate_ico(path: str):
    """Save a multi-size ICO for Windows tray/taskbar."""
    img = generate_icon(256)
    img.save(path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    out_dir = os.path.dirname(os.path.abspath(__file__))
    assets = os.path.join(out_dir, "assets")
    os.makedirs(assets, exist_ok=True)

    png_path = os.path.join(assets, "icon.png")
    ico_path = os.path.join(assets, "icon.ico")

    generate_icon(256).save(png_path)
    generate_ico(ico_path)

    # preview sizes
    for sz in (16, 32, 64):
        generate_icon(sz).save(os.path.join(assets, f"icon_{sz}.png"))

    print(f"OK: {png_path}")
    print(f"OK: {ico_path}")
    print(f"Sizes: {os.path.getsize(png_path)}b (png), {os.path.getsize(ico_path)}b (ico)")
