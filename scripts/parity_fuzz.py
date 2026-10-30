#!/usr/bin/env python3
"""Random inputs (valid and broken) through the Python package and the browser port; reports must match.

  python scripts/parity_fuzz.py N SEED OUT_DIR
"""
import json
import os
import random
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from arabic_ner_validator import validate  # noqa: E402

PIECES = ["الرياض", "والرياض", "بمكة", "للأمم", "المتحدة", "جـــدة", "مَكَّةُ", "دِمَشْقَ", "أبها", "ﻻهاي", "ﷲ",
          "Microsoft", "لـMozilla", "شركةNVIDIA", "٢٠٢٦", "\U0001F600", "\U0001F30D", "‏", "‎", "؜", "‌",
          "​", "﻿", "،", "؛", "؟", "«", "»", ".", "%", "U.S.", "\r\n", "\n", "\t", "  ", "ة", "ـ", "َ", "ّ"]


def text(rng):
    return " ".join(rng.choice(PIECES) for _ in range(rng.randint(1, 8)))


def make(rng, k):
    t = text(rng)
    n = len(t)
    unit = rng.choice(["codepoint", "utf16", "utf8_byte", "grapheme", None])
    spans = []
    for _ in range(rng.randint(0, 4)):
        a = rng.randint(-1, n + 2)
        b = rng.randint(-1, n + 3)
        sp = {"start": a, "end": b, "label": rng.choice(["LOC", "ORG", "PER"])}
        if rng.random() < 0.6:
            lo, hi = sorted((max(0, min(a, n)), max(0, min(b, n))))
            sp["text"] = t[lo:hi] if rng.random() < 0.7 else rng.choice(PIECES)
        spans.append(sp)
    rec = {"id": "f%d" % k, "text": t, "spans": spans}
    if unit:
        rec["offset_unit"] = unit
    for key, vals in (("clitic_policy", ["include", "exclude", "unspecified"]), ("nested_policy", ["forbid", "allow"]),
                      ("normalization_declared", ["none", "NFC", "NFKC"]), ("label_set", [["LOC", "ORG"]])):
        if rng.random() < 0.4:
            rec[key] = rng.choice(vals)
    fmt = rng.choice(["canonical", "canonical", "doccano", "spacy", "label_studio", "conll", "hf_tokens"])
    opts = {"offset_unit": rng.choice(["codepoint", "utf16", "utf8_byte", "grapheme"])}
    if fmt == "canonical":
        payload = json.dumps(rec, ensure_ascii=False) + "\n"
        opts = {}
    elif fmt == "doccano":
        payload = json.dumps({"id": k, "text": t, "label": [[s["start"], s["end"], s["label"]] for s in spans]}, ensure_ascii=False) + "\n"
    elif fmt == "spacy":
        payload = json.dumps({"text": t, "entities": [[s["start"], s["end"], s["label"]] for s in spans]}, ensure_ascii=False) + "\n"
    elif fmt == "label_studio":
        res = [{"value": {"start": s["start"], "end": s["end"], "labels": [s["label"]], **({"text": s["text"]} if "text" in s else {})}} for s in spans]
        payload = json.dumps([{"id": k, "data": {"text": t}, "annotations": [{"id": 1, "result": res}]}], ensure_ascii=False)
    else:
        toks = [p for p in text(rng).replace("\n", " ").replace("\r", " ").replace("\t", " ").split(" ") if p]
        tags = [rng.choice(["O", "B-LOC", "I-LOC", "E-LOC", "S-LOC", "L-ORG", "U-ORG", "B-ORG", "I-ORG", "X"]) for _ in toks]
        sch = rng.choice(["IOB2", "BIOES", "BILUO", "IOB1", "IOE2", "IO", None])
        opts = {"scheme": sch} if sch else {}
        if fmt == "conll":
            payload = "".join("%s\t%s\n" % (a, b) for a, b in zip(toks, tags)) + "\n"
        else:
            payload = json.dumps({"id": "h%d" % k, "tokens": toks, "ner_tags": tags}, ensure_ascii=False) + "\n"
    if rng.random() < 0.05:
        payload = "﻿" + payload
    return {"fixture_id": "fz-%05d" % k, "format": fmt, "options": opts, "input_payload": payload}


def main(n, seed, out_dir):
    rng = random.Random(seed)
    cases = [make(rng, k) for k in range(n)]
    path = os.path.join(out_dir, "fuzz_cases.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    out = subprocess.run(["node", os.path.join(ROOT, "tests", "js", "run_fixtures.mjs"), path],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    js = {json.loads(l)["fixture_id"]: json.loads(l) for l in out.splitlines()}
    diffs = []
    for c in cases:
        st = dict(c["options"])
        st["format"] = c["format"]
        rep, _, _ = validate(c["input_payload"].encode("utf-8"), st)
        a = json.loads(json.dumps(rep, ensure_ascii=False))
        b = js[c["fixture_id"]]["report"]
        a.pop("engine"), b.pop("engine")
        if a != b:
            diffs.append(c["fixture_id"])
    res = {"cases": n, "seed": seed, "mismatches": len(diffs), "first": diffs[:5]}
    print(json.dumps(res))
    log = os.path.join(ROOT, "docs", "qa", "parity_fuzz.json")
    runs = json.load(open(log, encoding="utf-8")) if os.path.exists(log) else []
    runs = [r for r in runs if r["seed"] != seed] + [res]
    with open(log, "w", encoding="utf-8") as fh:
        json.dump(sorted(runs, key=lambda r: r["seed"]), fh, indent=1)
        fh.write("\n")
    os.remove(path)
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]))
