#!/usr/bin/env python3
"""Run the independently written acceptance set through the validator (Python and the browser port).

  python scripts/run_acceptance.py ACCEPTANCE_JSONL OUT_JSON [--write-fixtures fixtures/acceptance/fixtures.jsonl]

A fixture of category X passes when the validator reports an error or warning whose code is mapped to
X (src/arabic_ner_validator/data/categories.json); a valid fixture passes when it reports no error and
no warning ("strict"). The acceptance README also allows warnings on some valid cases; that reading
is reported as "readme_rule".
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from arabic_ner_validator import validate  # noqa: E402

FMT = {"canonical": "canonical", "conll_iob2": "conll", "conll_biluo": "conll", "doccano_jsonl": "doccano",
       "labelstudio_json": "label_studio", "spacy_jsonl": "spacy"}
with open(os.path.join(ROOT, "src", "arabic_ner_validator", "data", "categories.json"), encoding="utf-8") as fh:
    CATS = json.load(fh)["categories"]


def to_fixture(a):
    fmt = FMT[a["format"]]
    opts = {k: v for k, v in (a.get("options") or {}).items() if v is not None}
    if a["format"] == "conll_iob2":
        opts.setdefault("scheme", "IOB2")
    if a["format"] == "conll_biluo":
        opts.setdefault("scheme", "BILUO")
    if fmt == "conll":
        opts.pop("offset_unit", None)
    inp = a["input"]
    if isinstance(inp, str):
        payload = inp
    elif fmt == "label_studio":
        payload = json.dumps(inp, ensure_ascii=False)
    else:
        payload = json.dumps(inp, ensure_ascii=False) + "\n"
    return {"fixture_id": a["fixture_id"], "split": "acceptance", "category": a["category"].split(":")[0].strip(),
            "category_name": a["category"].split(":", 1)[1].strip(), "valid": a["valid"], "format": fmt,
            "source_format": a["format"], "options": opts, "input_payload": payload,
            "expected_problem": a["expected_problem"], "author_note": a["author_note"],
            "author": "Bayanat Labs (acceptance set, written separately from the validator)", "reviewed_by": None,
            "synthetic": True, "license": "CC-BY-4.0"}


def evaluate(fx, report):
    flagged = sorted({f["code"] for f in report["file_findings"] + [g for r in report["records"] for g in r["findings"]]
                      if f["severity"] in ("error", "warning")})
    errors = sorted({f["code"] for f in report["file_findings"] + [g for r in report["records"] for g in r["findings"]]
                     if f["severity"] == "error"})
    cat = CATS[fx["category"]]
    if fx["valid"]:
        strict = not flagged
        warn_ok = "warning" in fx["expected_problem"].lower()
        readme = not errors and (not flagged or warn_ok)
        primary = strict
    else:
        strict = bool(set(flagged) & set(cat["codes"]))
        readme = bool(set(errors) & set(cat["codes"]))
        primary = cat["primary"] in flagged
    return {"fixture_id": fx["fixture_id"], "category": fx["category"], "valid": fx["valid"], "format": fx["format"],
            "flagged": flagged, "pass": strict, "pass_readme_rule": readme, "primary_code": primary}


def main(src, out, write=None):
    with open(src, encoding="utf-8") as fh:
        acc = [json.loads(x) for x in fh if x.strip()]
    fixtures = [to_fixture(a) for a in acc]
    if write:
        os.makedirs(os.path.dirname(write), exist_ok=True)
        with open(write, "w", encoding="utf-8", newline="\n") as fh:
            for f in fixtures:
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    tmp = out + ".fixtures.jsonl"
    with open(tmp, "w", encoding="utf-8") as fh:
        for f in fixtures:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    js_out = subprocess.run(["node", os.path.join(ROOT, "tests", "js", "run_fixtures.mjs"), tmp],
                            capture_output=True, text=True, encoding="utf-8", check=True).stdout
    js = {json.loads(l)["fixture_id"]: json.loads(l)["report"] for l in js_out.splitlines()}
    os.remove(tmp)
    rows, parity_diff = [], []
    for fx in fixtures:
        st = dict(fx["options"])
        st["format"] = fx["format"]
        rep, _, _ = validate(fx["input_payload"].encode("utf-8"), st)
        a = json.loads(json.dumps(rep, ensure_ascii=False))
        b = dict(js[fx["fixture_id"]])
        a.pop("engine"), b.pop("engine")
        if a != b:
            parity_diff.append(fx["fixture_id"])
        row = evaluate(fx, rep)
        row["messages"] = [f["message_en"] for r in rep["records"] for f in r["findings"] if f["severity"] != "info"] + \
                          [f["message_en"] for f in rep["file_findings"]]
        rows.append(row)
    summ = {"fixtures": len(rows), "valid": sum(r["valid"] for r in rows), "invalid": sum(not r["valid"] for r in rows),
            "pass": sum(r["pass"] for r in rows), "pass_readme_rule": sum(r["pass_readme_rule"] for r in rows),
            "primary_code": sum(r["primary_code"] for r in rows), "js_python_mismatches": len(parity_diff),
            "by_category": {}}
    for r in rows:
        c = summ["by_category"].setdefault(r["category"], {"fixtures": 0, "pass": 0})
        c["fixtures"] += 1
        c["pass"] += r["pass"]
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"summary": summ, "parity_mismatches": parity_diff, "results": rows}, fh, ensure_ascii=False, indent=1)
    print(json.dumps(summ, ensure_ascii=False))
    for r in rows:
        if not r["pass"]:
            print("FAIL", r["fixture_id"], "valid" if r["valid"] else "invalid", r["flagged"])


if __name__ == "__main__":
    w = sys.argv[sys.argv.index("--write-fixtures") + 1] if "--write-fixtures" in sys.argv else None
    main(sys.argv[1], sys.argv[2], w)
