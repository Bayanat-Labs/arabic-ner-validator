#!/usr/bin/env python3
"""Unicode normalisation (NFD, NFC, NFKD, NFKC) computed directly from one version of the UCD files,
so that the drift inventory can be built for a Unicode version the Python runtime does not ship.

  python scripts/ucd_normalize.py UCD_DIR      # runs NormalizationTest.txt from UCD_DIR and prints the result
"""
import os
import sys

SBASE, LBASE, VBASE, TBASE = 0xAC00, 0x1100, 0x1161, 0x11A7
LCOUNT, VCOUNT, TCOUNT = 19, 21, 28
NCOUNT = VCOUNT * TCOUNT
SCOUNT = LCOUNT * NCOUNT


class UCD:
    def __init__(self, ucd_dir):
        self.ccc = {}
        self.canon = {}
        self.compat = {}
        self.gc = {}
        self.name = {}
        self.assigned = set()
        first = None
        with open(os.path.join(ucd_dir, "UnicodeData.txt"), encoding="utf-8") as fh:
            for line in fh:
                f = line.rstrip("\n").split(";")
                cp = int(f[0], 16)
                nm = f[1]
                if nm.endswith(", First>"):
                    first = (cp, f)
                    continue
                if nm.endswith(", Last>"):
                    a, fa = first
                    for c in range(a, cp + 1):
                        self.assigned.add(c)
                        self.gc[c] = fa[2]
                        if int(fa[3]):
                            self.ccc[c] = int(fa[3])
                    continue
                self.assigned.add(cp)
                self.gc[cp] = f[2]
                self.name[cp] = nm
                if int(f[3]):
                    self.ccc[cp] = int(f[3])
                d = f[5]
                if d:
                    parts = d.split()
                    if parts[0].startswith("<"):
                        self.compat[cp] = [int(x, 16) for x in parts[1:]]
                    else:
                        self.canon[cp] = [int(x, 16) for x in parts]
        self.excl = set()
        with open(os.path.join(ucd_dir, "DerivedNormalizationProps.txt"), encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#")[0].strip()
                if not line:
                    continue
                f = [x.strip() for x in line.split(";")]
                if f[1] != "Full_Composition_Exclusion":
                    continue
                r = f[0].split("..")
                a = int(r[0], 16)
                b = int(r[-1], 16)
                self.excl.update(range(a, b + 1))
        self.comp = {}
        for cp, d in self.canon.items():
            if len(d) == 2 and cp not in self.excl:
                self.comp[(d[0], d[1])] = cp

    def _decomp(self, cp, compat, out):
        if SBASE <= cp < SBASE + SCOUNT:
            s = cp - SBASE
            out.append(LBASE + s // NCOUNT)
            out.append(VBASE + (s % NCOUNT) // TCOUNT)
            t = TBASE + s % TCOUNT
            if t != TBASE:
                out.append(t)
            return
        d = self.canon.get(cp)
        if d is None and compat:
            d = self.compat.get(cp)
        if d is None:
            out.append(cp)
            return
        for x in d:
            self._decomp(x, compat, out)

    def decompose(self, cps, compat):
        out = []
        for cp in cps:
            self._decomp(cp, compat, out)
        # canonical ordering
        i = 0
        n = len(out)
        while i < n:
            if self.ccc.get(out[i], 0) == 0:
                i += 1
                continue
            j = i
            while j < n and self.ccc.get(out[j], 0) != 0:
                j += 1
            out[i:j] = sorted(out[i:j], key=lambda c: self.ccc.get(c, 0))
            i = j
        return out

    def _primary(self, a, b):
        if LBASE <= a < LBASE + LCOUNT and VBASE <= b < VBASE + VCOUNT:
            return SBASE + ((a - LBASE) * VCOUNT + (b - VBASE)) * TCOUNT
        if SBASE <= a < SBASE + SCOUNT and (a - SBASE) % TCOUNT == 0 and TBASE < b < TBASE + TCOUNT:
            return a + (b - TBASE)
        return self.comp.get((a, b))

    def compose(self, d):
        if not d:
            return d
        res = [d[0]]
        starter = 0 if self.ccc.get(d[0], 0) == 0 else None
        for cp in d[1:]:
            c = self.ccc.get(cp, 0)
            if starter is not None:
                if len(res) - 1 == starter:
                    blocked = False
                else:
                    lc = self.ccc.get(res[-1], 0)
                    blocked = lc == 0 or lc >= c
                if not blocked:
                    comp = self._primary(res[starter], cp)
                    if comp is not None:
                        res[starter] = comp
                        continue
            if c == 0:
                starter = len(res)
            res.append(cp)
        return res

    def normalize(self, form, s):
        cps = [ord(c) for c in s]
        d = self.decompose(cps, form in ("NFKD", "NFKC"))
        if form in ("NFC", "NFKC"):
            d = self.compose(d)
        return "".join(map(chr, d))


def run_conformance(ucd_dir):
    u = UCD(ucd_dir)
    seen = set()
    fails = 0
    total = 0
    with open(os.path.join(ucd_dir, "NormalizationTest.txt"), encoding="utf-8") as fh:
        part = None
        for line in fh:
            if line.startswith("@Part"):
                part = line.split()[0]
                continue
            line = line.split("#")[0].strip()
            if not line:
                continue
            cols = ["".join(chr(int(x, 16)) for x in c.split()) for c in line.split(";")[:5]]
            c1, c2, c3, c4, c5 = cols
            if part == "@Part1" and len(c1) == 1:
                seen.add(ord(c1))
            checks = [(u.normalize("NFC", c1), c2), (u.normalize("NFC", c2), c2), (u.normalize("NFC", c3), c2),
                      (u.normalize("NFC", c4), c4), (u.normalize("NFC", c5), c4),
                      (u.normalize("NFD", c1), c3), (u.normalize("NFD", c2), c3), (u.normalize("NFD", c3), c3),
                      (u.normalize("NFD", c4), c5), (u.normalize("NFD", c5), c5),
                      (u.normalize("NFKC", c1), c4), (u.normalize("NFKC", c2), c4), (u.normalize("NFKC", c3), c4),
                      (u.normalize("NFKC", c4), c4), (u.normalize("NFKC", c5), c4),
                      (u.normalize("NFKD", c1), c5), (u.normalize("NFKD", c2), c5), (u.normalize("NFKD", c3), c5),
                      (u.normalize("NFKD", c4), c5), (u.normalize("NFKD", c5), c5)]
            total += len(checks)
            fails += sum(1 for a, b in checks if a != b)
    # Part 1 rule: every other code point normalises to itself
    other_fail = 0
    other_total = 0
    for cp in range(0x110000):
        if cp in seen or 0xD800 <= cp <= 0xDFFF:
            continue
        other_total += 1
        ch = chr(cp)
        for form in ("NFC", "NFD", "NFKC", "NFKD"):
            if u.normalize(form, ch) != ch:
                other_fail += 1
                break
    return {"checks": total, "failures": fails, "identity_code_points": other_total, "identity_failures": other_fail}


if __name__ == "__main__":
    print(run_conformance(sys.argv[1]))
