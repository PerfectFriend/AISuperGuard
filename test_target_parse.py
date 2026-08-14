#!/usr/bin/env python3
"""Test parse_target() with real-world examples."""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

src = open('panic_mode.py', encoding='utf-8').read()

# extract needed blocks: L dict, tr(), parse_target deps (COLOR_MAP/COLOR_SYN/CLASS_MAP/CLASS_SYN/VEHICLE_CLASSES)
blocks = {}
for name in ['L', 'COLOR_MAP', 'COLOR_SYN', 'CLASS_MAP', 'CLASS_SYN']:
    i = src.index(name + ' = {')
    j = src.index('\n}\n', i) + 3
    blocks[name] = src[i:j]

ns = {}
for name, code in blocks.items():
    exec(code, ns)

VEHICLE_CLASSES = {2: 'car', 5: 'bus', 7: 'truck'}
ns['VEHICLE_CLASSES'] = VEHICLE_CLASSES
ns['re'] = __import__('re')

# parse_target body
i = src.index('def parse_target(')
j = src.index('def _ranges_color_name', i)
exec(src[i:j], ns)

parse_target = ns['parse_target']

cases = [
    ("red car", {2}, "red"),
    ("жёлтая машина", {2}, "yellow"),
    ("человек в положении стоя", {0}, None),
    ("person standing", {0}, None),
    ("truck", {7}, None),
    ("белый грузовик", {7}, "white"),
    ("blue", {2,5,7}, "blue"),
    ("красный", {2,5,7}, "red"),
    ("автобус amarillo", {5}, "yellow"),
    ("carro rojo", {2}, "red"),
    ("любой объект", None, None),
]
ok = True
for text, exp_cls, exp_col in cases:
    classes, ranges = parse_target(text)
    got_cls = set(classes) if classes else None
    # determine color from ranges
    got_col = None
    if ranges:
        for cname, pairs in ns['COLOR_MAP'].items():
            if sorted(ranges) == sorted(pairs):
                got_col = cname
                break
    status = "OK " if got_cls == exp_cls and got_col == exp_col else "FAIL"
    if status == "FAIL":
        ok = False
    print(f"{status} '{text}' -> classes={got_cls} color={got_col} (exp {exp_cls}/{exp_col})")
print("ALL OK" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
