#!/usr/bin/env python3
"""Arabic drift inventory from one pinned UCD version.

Rows:
  single       every assigned code point in the Arabic blocks whose NFC or NFKC form differs from it
  composition  every Arabic letter + combining mark pair (both from the Arabic blocks) that NFC or
               NFKC composes into fewer code points than the parts give separately
  reorder      every pair of Arabic combining marks that NFC puts in the other order (no length change)

  python scripts/build_inventory.py UCD_DIR VERSION OUT_CSV [--check-python]
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ucd_normalize import UCD  # noqa: E402

BLOCKS = [(0x0600, 0x06FF), (0x0750, 0x077F), (0x0870, 0x089F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF),
          (0xFE70, 0xFEFF), (0x10EC0, 0x10EFF), (0x1EE00, 0x1EEFF)]


def u(s):
    return " ".join("U+%04X" % ord(c) for c in s)


def main(ucd_dir, version, out, check_python=False):
    d = UCD(ucd_dir)
    cps = [c for a, b in BLOCKS for c in range(a, b + 1) if c in d.assigned]
    letters = [c for c in cps if d.gc[c].startswith("L") and d.ccc.get(c, 0) == 0]
    marks = [c for c in cps if d.gc[c] in ("Mn", "Mc", "Me")]
    rows = []
    for c in cps:
        s = chr(c)
        nfc, nfkc = d.normalize("NFC", s), d.normalize("NFKC", s)
        if nfc != s or nfkc != s:
            rows.append(("single", s, nfc, nfkc, str(d.ccc.get(c, 0)), d.name.get(c, "")))
    for b in letters:
        for m in marks:
            s = chr(b) + chr(m)
            nfc, nfkc = d.normalize("NFC", s), d.normalize("NFKC", s)
            sep_nfc = d.normalize("NFC", chr(b)) + d.normalize("NFC", chr(m))
            sep_nfkc = d.normalize("NFKC", chr(b)) + d.normalize("NFKC", chr(m))
            if len(nfc) < len(sep_nfc) or len(nfkc) < len(sep_nfkc):
                rows.append(("composition", s, nfc, nfkc, "%d,%d" % (d.ccc.get(b, 0), d.ccc.get(m, 0)),
                             d.name.get(b, "") + " + " + d.name.get(m, "")))
    for m1 in marks:
        for m2 in marks:
            c1, c2 = d.ccc.get(m1, 0), d.ccc.get(m2, 0)
            if c1 > c2 > 0:
                s = chr(m1) + chr(m2)
                nfc, nfkc = d.normalize("NFC", s), d.normalize("NFKC", s)
                if nfc != s and len(nfc) == 2:
                    rows.append(("reorder", s, nfc, nfkc, "%d,%d" % (c1, c2), d.name.get(m1, "") + " + " + d.name.get(m2, "")))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["unicode_version", "kind", "sequence", "nfc", "nfkc", "len_delta_nfc", "len_delta_nfkc", "ccc", "name"])
        for kind, s, nfc, nfkc, ccc, name in rows:
            w.writerow([version, kind, u(s), u(nfc), u(nfkc), len(nfc) - len(s), len(nfkc) - len(s), ccc, name])
    counts = {}
    for r in rows:
        counts[r[0]] = counts.get(r[0], 0) + 1
    changed = sum(1 for r in rows if len(r[2]) != len(r[1]) or len(r[3]) != len(r[1]))
    res = {"version": version, "rows": len(rows), "by_kind": counts, "length_changing": changed,
           "code_points_in_blocks": len(cps), "letters": len(letters), "marks": len(marks)}
    if check_python:
        import unicodedata
        agree = sum(1 for r in rows if unicodedata.normalize("NFC", r[1]) == r[2] and unicodedata.normalize("NFKC", r[1]) == r[3])
        res["python_unicodedata"] = unicodedata.unidata_version
        res["python_agrees"] = agree
    print(res)
    return res


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], "--check-python" in sys.argv)
