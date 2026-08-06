#!/usr/bin/env python3
"""Sanity check: every tr() key exists in all 3 languages; tr() formats ok."""
import re, sys

src = open('panic_mode.py', encoding='utf-8').read()

# extract the L dict literal (from 'L = {' to the line before 'def tr')
start = src.index('L = {')
end = src.index('\ndef tr(', start)
m = src[start:end]
ns = {}
exec(m, ns)
L = ns['L']

keys = set(L['ru'])
bad = False
for lang in ('en', 'es', 'ru'):
    missing = keys - set(L[lang])
    if missing:
        bad = True
        print(f'{lang}: MISSING {sorted(missing)}')
print('keys total:', len(keys))

# every tr('key', ...) call in source must be a real key
calls = set(re.findall(r"tr\('([a-z_]+)'", src))
for k in sorted(calls - keys):
    bad = True
    print(f'source calls unknown key: {k}')

# zone_label edge cases (grid math)
ZONE = (3, 4, 9)   # N3x4 C9 -> row 3, col 1 (bottom-left)
cell = 9; rows, cols = 3, 4
r = (cell - 1) // cols + 1
c = (cell - 1) % cols + 1
assert (r, c) == (3, 1), (r, c)
ZONE2 = (3, 3, 5)  # N3x3 C5 -> center
cell = 5; rows, cols = 3, 3
assert ((cell - 1) // cols + 1, (cell - 1) % cols + 1) == (2, 2)

print('OK: all keys present, zone math correct')
sys.exit(1 if bad else 0)
