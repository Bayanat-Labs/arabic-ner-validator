#!/usr/bin/env python3
"""Derive tests/data/grapheme_break_<version>.json from GraphemeBreakTest.txt (UCD auxiliary file).
Each case: [code points], [boundary positions in code points]."""
import json
import os
import sys

src, version, out = sys.argv[1], sys.argv[2], sys.argv[3]
cases = []
with open(src, encoding="utf-8") as fh:
    for line in fh:
        line = line.split("#")[0].strip()
        if not line:
            continue
        cps, bounds, pos = [], [], 0
        for tok in line.split():
            if tok == "÷":
                bounds.append(pos)
            elif tok == "×":
                pass
            else:
                cps.append(int(tok, 16))
                pos += 1
        cases.append([cps, bounds])
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as fh:
    json.dump({"unicode_version": version, "source": "GraphemeBreakTest.txt", "cases": cases}, fh, separators=(",", ":"))
print(version, len(cases))
