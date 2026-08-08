#!/usr/bin/env python3
"""Tests for desktop icon generator."""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from icon import generate_icon, generate_ico  # noqa: E402

PASS = FAIL = 0

def check(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  ✓ {name}")
    except Exception as e:
        FAIL += 1
        print(f"  ✗ {name}: {type(e).__name__}: {e}")

def test_sizes():
    for sz in (16, 32, 64, 128, 256):
        img = generate_icon(sz)
        assert img.size == (sz, sz), f"{sz}: {img.size}"
    print("    размеры 16/32/64/128/256 ✓")

def test_elements():
    img = np.array(generate_icon(256)).astype(int)
    r, g, b, a = img[..., 0], img[..., 1], img[..., 2], img[..., 3]
    opaque = a > 128
    total = opaque.sum()
    assert total > 30000, "мало непрозрачных пикселей"
    white = ((r > 200) & (g > 200) & (b > 200) & opaque).sum()
    yellow = ((r > 220) & (g > 170) & (b < 80) & opaque).sum()
    assert white / total > 0.10, f"глаз мал: {white/total*100:.1f}%"
    assert yellow / total > 0.005, f"молния мала: {yellow/total*100:.1f}%"
    print(f"    глаз {white/total*100:.1f}%, молния {yellow/total*100:.1f}% ✓")

def test_ico(tmp=r"C:\SuperGuard\desktop\assets"):
    ico = os.path.join(tmp, "icon_test.ico")
    generate_ico(ico)
    assert os.path.exists(ico) and os.path.getsize(ico) > 5000
    os.remove(ico)
    print(f"    ICO создан ✓")

def test_png_save(tmp=r"C:\SuperGuard\desktop\assets"):
    png = os.path.join(tmp, "icon_test.png")
    generate_icon(256).save(png)
    assert os.path.exists(png) and os.path.getsize(png) > 5000
    os.remove(png)
    print(f"    PNG создан ✓")

print("ICON TESTS")
check("размеры", test_sizes)
check("глаз + молния", test_elements)
check("ICO export", test_ico)
check("PNG export", test_png_save)
print(f"ИТОГ: {PASS} PASS, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)