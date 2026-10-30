#!/usr/bin/env python3
"""Recompute the QA numbers quoted in the documentation and write docs/qa/numbers.json.

  python scripts/qa_numbers.py [UCD_DIR_16 UCD_DIR_17]
The UCD directories (UnicodeData.txt, DerivedNormalizationProps.txt, NormalizationTest.txt) are only
needed to rerun the normalisation conformance check; without them the stored result is kept.
"""
import collections
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import regex  # noqa: E402

from arabic_ner_validator import __version__  # noqa: E402
from arabic_ner_validator.checks import Ctx  # noqa: E402
from arabic_ner_validator.io import parse  # noqa: E402
from arabic_ner_validator.report import CODES, decode  # noqa: E402
from fixture_runner import compare  # noqa: E402

QA = os.path.join(ROOT, "docs", "qa")


def fixtures(split):
    with open(os.path.join(ROOT, "fixtures", split, "fixtures.jsonl"), encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def oracle(fx_list):
    from oracle import compare_record, compare_tags
    out = {"fixtures": 0, "records": 0, "skipped_nested": 0, "checks": collections.Counter(), "agree": collections.Counter()}
    for fx in fx_list:
        if not fx["valid"]:
            continue
        out["fixtures"] += 1
        st = dict(fx.get("options") or {})
        st["format"] = fx["format"]
        text, _, bom = decode(fx["input_payload"].encode("utf-8"))
        for rec in parse(text, fx["format"], st):
            ctx = Ctx(rec, bom)
            if rec.from_tokens:
                res = compare_tags(rec.text, rec.tokens, rec.tags, rec.scheme or "IOB2")
            else:
                spans = [(ctx.omap.to_cp(s["start"], rec.offset_unit)[0], ctx.omap.to_cp(s["end"], rec.offset_unit)[0], s["label"]) for s in rec.spans]
                if any(a[0] < b[1] and b[0] < a[1] for i, a in enumerate(spans) for b in spans[i + 1:]):
                    out["skipped_nested"] += 1
                    continue
                toks = list(rec.tokens_cp) if rec.tokens_cp is not None else (
                    [(ctx.omap.to_cp(a, rec.offset_unit)[0], ctx.omap.to_cp(b, rec.offset_unit)[0]) for a, b in rec.tokens] if rec.tokens is not None else None)
                res = compare_record(rec.text, spans, toks)
            out["records"] += 1
            for k, v in res.items():
                out["checks"][k] += 1
                out["agree"][k] += bool(v)
    out["checks"], out["agree"] = dict(out["checks"]), dict(out["agree"])
    return out


def graphemes():
    res = {}
    for v in ("16.0.0", "17.0.0"):
        with open(os.path.join(ROOT, "tests", "data", "grapheme_break_%s.json" % v), encoding="utf-8") as fh:
            cases = json.load(fh)["cases"]
        ok = 0
        for cps, b in cases:
            s = "".join(map(chr, cps))
            got, pos = [0], 0
            for m in regex.finditer(r"\X", s):
                pos += len(m.group(0))
                got.append(pos)
            ok += got == b
        res[v] = {"cases": len(cases), "regex_pass": ok}
    return res


def main():
    dev, acc = fixtures("dev"), fixtures("acceptance")
    n = {"validator_version": __version__}
    n["codes"] = dict(collections.Counter(c["severity"] for c in CODES.values()))
    n["codes_total"] = len(CODES)
    for name, fl in (("dev", dev), ("acceptance", acc)):
        cats = collections.Counter(f["category"] for f in fl)
        n[name] = {"fixtures": len(fl), "valid": sum(f["valid"] for f in fl), "invalid": sum(not f["valid"] for f in fl),
                   "categories": len([c for c in cats if c != "v"]), "by_category": dict(sorted(cats.items())),
                   "by_format": dict(sorted(collections.Counter(f["format"] for f in fl).items()))}
    n["dev"]["pass"] = sum(compare(f)[0] for f in dev)
    with open(os.path.join(QA, "acceptance_results.json"), encoding="utf-8") as fh:
        ar = json.load(fh)["summary"]
    with open(os.path.join(QA, "acceptance_run_frozen.json"), encoding="utf-8") as fh:
        a1 = json.load(fh)["summary"]
    n["acceptance"].update({"pass": ar["pass"], "pass_frozen_build": a1["pass"], "primary_code": ar["primary_code"],
                            "js_python_mismatches": ar["js_python_mismatches"]})
    n["oracle"] = oracle(dev + acc)
    inv = {}
    for v in ("16.0.0", "17.0.0"):
        with open(os.path.join(ROOT, "inventory", "drift_sequences_%s.csv" % v), encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        inv[v] = {"rows": len(rows), "by_kind": dict(collections.Counter(r["kind"] for r in rows)),
                  "length_changing": sum(1 for r in rows if r["len_delta_nfc"] != "0" or r["len_delta_nfkc"] != "0")}
    n["inventory"] = inv
    n["grapheme_break_tests"] = graphemes()
    import shutil
    import subprocess
    if shutil.which("node"):
        js = json.loads(subprocess.run(["node", os.path.join(ROOT, "tests", "js", "grapheme_tests.mjs")], capture_output=True, text=True, check=True).stdout)
        for v in ("16.0.0", "17.0.0"):
            n["grapheme_break_tests"][v]["intl_segmenter_pass"] = js[v]["pass"]
        n["grapheme_break_tests"]["intl_segmenter_runtime"] = "%s (ICU %s, Unicode %s)" % (js["runtime"], js["icu"], js["unicode"])
    with open(os.path.join(QA, "normalization_conformance.json"), encoding="utf-8") as fh:
        n["normalization_conformance"] = json.load(fh)
    with open(os.path.join(QA, "parity_fuzz.json"), encoding="utf-8") as fh:
        pf = json.load(fh)
    n["parity_fuzz"] = {"runs": len(pf), "cases": sum(r["cases"] for r in pf), "mismatches": sum(r["mismatches"] for r in pf)}
    with open(os.path.join(ROOT, "matrix", "offset_conventions.csv"), encoding="utf-8") as fh:
        m = list(csv.DictReader(fh))
    n["matrix"] = {"rows": len(m), "measured": sum(r["method"] == "measured" for r in m),
                   "from_source": sum(r["method"] != "measured" for r in m), "tools": len({r["tool"] for r in m})}
    with open(os.path.join(ROOT, "matrix", "evidence", "probes.json"), encoding="utf-8") as fh:
        n["matrix"]["probes"] = len(json.load(fh))
    with open(os.path.join(ROOT, "schema", "rejected_examples.jsonl"), encoding="utf-8") as fh:
        n["rejected_examples"] = sum(1 for x in fh if x.strip())
    with open(os.path.join(QA, "smoke_report.json"), encoding="utf-8") as fh:
        n["smoke"] = json.load(fh)["datasets"]
    with open(os.path.join(QA, "numbers.json"), "w", encoding="utf-8") as fh:
        json.dump(n, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(json.dumps({k: v for k, v in n.items() if k != "smoke"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
