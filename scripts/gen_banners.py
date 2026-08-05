"""
gen_banners.py — генерация рекламных баннеров SuperGuard.
Стиль: киберпанк × Ван Гог × Гауди (неоновые вихри + тренкадис-мозаика).

Баннер 1 (header):  SuperGuard — название + слоган
Баннер 2 (footer):  CTA — "Protege tu infraestructura"
"""

import math
import random
from PIL import Image, ImageDraw, ImageFont

# ── Палитра: киберпанк-неон на тёмном фоне ──────────────────────────────
BG = (10, 8, 24)                 # космический тёмно-синий
NEON = [
    (0, 255, 255),    # циан
    (255, 0, 200),    # маджента
    (255, 170, 0),    # янтарь
    (120, 80, 255),   # фиолетовый
    (0, 255, 120),    # неоновый зелёный
    (255, 60, 60),    # красный
]
GOLD = (255, 200, 60)

W, H = 1600, 480          # размер баннера (широкий, для README)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def neon_text(draw, xy, text, font, color, glow_runs=6, glow_power=10):
    """Текст с неоновым свечением."""
    x, y = xy
    for i in range(glow_runs, 0, -1):
        alpha_glow = int(90 / i)
        glow_color = tuple(min(255, int(c * 0.6)) for c in color)
        for dx in (-i, 0, i):
            for dy in (-i, 0, i):
                draw.text((x + dx * glow_power // 8, y + dy * glow_power // 8),
                          text, font=font, fill=glow_color + (alpha_glow,))
    draw.text((x, y), text, font=font, fill=color)


def van_gogh_swirls(draw, cx, cy, r_max, colors, seed=1):
    """Вихревые мазки в духе «Звёздной ночи» — спирали неоновых штрихов."""
    rnd = random.Random(seed)
    for r in range(10, r_max, 14):
        n = max(6, int(r * 0.9))
        for i in range(n):
            a = (i / n) * 2 * math.pi + r * 0.05
            rr = r + rnd.uniform(-5, 5)
            x = cx + math.cos(a) * rr
            y = cy + math.sin(a) * rr
            x2 = cx + math.cos(a + 0.4) * (rr + 12)
            y2 = cy + math.sin(a + 0.4) * (rr + 12)
            col = rnd.choice(colors)
            draw.line((x, y, x2, y2), fill=col + (140,), width=3)


def gaudi_mosaic(draw, x0, y0, w, h, colors, n=90, seed=2):
    """Тренкадис-мозаика Гауди: рваные цветные фрагменты."""
    rnd = random.Random(seed)
    for _ in range(n):
        x = rnd.uniform(x0, x0 + w)
        y = rnd.uniform(y0, y0 + h)
        s = rnd.uniform(6, 26)
        col = rnd.choice(colors) + (rnd.randint(90, 200),)
        pts = []
        for k in range(rnd.randint(3, 6)):
            a = k / 6 * 2 * math.pi
            pts.append((x + math.cos(a) * s * rnd.uniform(0.7, 1.3),
                        y + math.sin(a) * s * rnd.uniform(0.7, 1.3)))
        draw.polygon(pts, fill=col)


def circuit_lines(draw, colors, n=40, seed=3):
    """Киберпанк-дорожки: ломаные линии-цепи."""
    rnd = random.Random(seed)
    for _ in range(n):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        col = rnd.choice(colors) + (90,)
        pts = [(x, y)]
        for _ in range(rnd.randint(2, 4)):
            x += rnd.choice([-1, 1]) * rnd.uniform(40, 160)
            y += rnd.choice([-1, 1]) * rnd.uniform(20, 90)
            pts.append((x, y))
        draw.line(pts, fill=col, width=2)
        draw.ellipse((pts[-1][0] - 4, pts[-1][1] - 4, pts[-1][0] + 4, pts[-1][1] + 4),
                     fill=col)


def make_banner(title, subtitle, out_path, seed):
    img = Image.new("RGBA", (W, H), BG + (255,))
    draw = ImageDraw.Draw(img)

    # фоновые слои
    gaudi_mosaic(draw, 0, 0, W, H, NEON, n=130, seed=seed)
    van_gogh_swirls(draw, W * 0.85, H * 0.25, 260, NEON, seed=seed + 1)
    van_gogh_swirls(draw, W * 0.12, H * 0.8, 180, NEON, seed=seed + 2)
    circuit_lines(draw, NEON, n=50, seed=seed + 3)

    # виньетка (тёмные края → читаемый центр)
    for i in range(120):
        a = int(255 * (i / 120) ** 2)
        draw.rectangle((i, i, W - i, H - i), outline=(10, 8, 24, a), width=2)

    # ── Текст ───────────────────────────────────────────────────────────
    try:
        font_big = ImageFont.truetype("arialbd.ttf", 88)
        font_mid = ImageFont.truetype("arialbd.ttf", 40)
        font_small = ImageFont.truetype("arial.ttf", 26)
    except Exception:
        font_big = ImageFont.load_default()
        font_mid = font_small = font_big

    # тень-подложка под текст для читаемости
    draw.rectangle((30, H // 2 - 120, W - 30, H // 2 + 120), fill=(8, 6, 20, 170))

    neon_text(draw, (60, H // 2 - 95), title, font_big, (0, 255, 255))
    neon_text(draw, (62, H // 2 + 15), subtitle, font_mid, GOLD)
    neon_text(draw, (64, H // 2 + 75), "AI SURVEILLANCE · PERIMETER · ANTI-THEFT",
              font_small, (255, 60, 60))

    # неоновая рамка
    for i in range(1, 5):
        col = NEON[(seed + i) % len(NEON)]
        draw.rectangle((i * 3, i * 3, W - i * 3, H - i * 3), outline=col, width=2)

    img.save(out_path)
    print(f"✓ {out_path}  ({W}x{H})")


if __name__ == "__main__":
    make_banner(
        "SUPERGUARD",
        "Protection IA contra robos · Perímetro · Cable",
        r"C:\Users\tomas\video-surveillance\assets\banner-header.png",
        seed=7,
    )
    make_banner(
        "24/7 · AI · LOCAL",
        "Detección inteligente → Alerta → Foco + Sirena",
        r"C:\Users\tomas\video-surveillance\assets\banner-footer.png",
        seed=13,
    )
    print("Готово. Баннеры в assets/")
