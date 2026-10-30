#!/usr/bin/env python3
"""Run the validator on public Arabic NER datasets downloaded beforehand and keep only aggregate
counts (records, spans, findings per code). No record, text or per-sentence result is written.

  python scripts/smoke_test.py FILES_JSON OUT_JSON
FILES_JSON: {"<dataset id>": {"revision": "...", "license": "...", "files": ["...parquet", ...]}}
"""
import collections
import json
import sys

import pyarrow.parquet as pq

from arabic_ner_validator import validate

WIKIANN_TAGS = ["O", "B-PER", "I-PER", "B-ORG", "I-ORG", "B-LOC", "I-LOC"]


def jsonl(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")


def summarise(report):
    s = report["summary"]
    return {"records": s["records"], "records_with_errors": s["records_with_errors"], "spans": s["spans"],
            "valid_spans": s["valid_spans"], "by_severity": s["by_severity"], "by_code": s["by_code"]}


def merge(parts):
    out = {"records": 0, "records_with_errors": 0, "spans": 0, "valid_spans": 0,
           "by_severity": collections.Counter(), "by_code": collections.Counter()}
    for p in parts:
        for k in ("records", "records_with_errors", "spans", "valid_spans"):
            out[k] += p[k]
        out["by_severity"].update(p["by_severity"])
        out["by_code"].update(p["by_code"])
    out["by_severity"] = dict(sorted(out["by_severity"].items()))
    out["by_code"] = dict(sorted(out["by_code"].items()))
    return out


def run_wikiann(files):
    parts = []
    for f in files:
        rows = pq.read_table(f, columns=["tokens", "ner_tags"]).to_pylist()
        data = jsonl({"id": "r%d" % i, "tokens": r["tokens"], "ner_tags": r["ner_tags"]} for i, r in enumerate(rows))
        rep, _, _ = validate(data, {"format": "hf_tokens", "scheme": "IOB2", "tag_names": WIKIANN_TAGS})
        parts.append(summarise(rep))
    return merge(parts), "hf_tokens rows, IOB2, tag names " + ",".join(WIKIANN_TAGS)


def run_shamner(files):
    parts = []
    for f in files:
        rows = pq.read_table(f, columns=["text", "spans"]).to_pylist()
        recs = [{"id": "r%d" % i, "text": r["text"], "offset_unit": "codepoint",
                 "spans": [dict({"start": s["start"], "end": s["end"], "label": s["label"]},
                                **({"text": s["text"]} if isinstance(s.get("text"), str) else {})) for s in r["spans"]]}
                for i, r in enumerate(rows)]
        rep, _, _ = validate(jsonl(recs), {"format": "canonical"})
        parts.append(summarise(rep))
    return merge(parts), "canonical records, offsets read as code points (the dataset's character spans), span text checked where it is not null"


def run_token_rows(files):
    parts = []
    for f in files:
        rows = pq.read_table(f).to_pylist()
        sents, cur = [], []
        for r in rows:
            cur.append((r["Token"], r["Tag"]))
            if r["Token"] in (".", "؟", "!", "?") and r["Tag"] == "O":
                sents.append(cur)
                cur = []
        if cur:
            sents.append(cur)
        text = "".join("".join("%s\t%s\n" % (t, g) for t, g in s) + "\n" for s in sents)
        rep, _, _ = validate(text.encode("utf-8"), {"format": "conll", "scheme": "IOB2"})
        parts.append(summarise(rep))
    return merge(parts), "token rows grouped into sentences at sentence-final punctuation, CoNLL, IOB2"


RUNNERS = {"unimelb-nlp/wikiann": run_wikiann, "HebArabNlpProject/ShamNER": run_shamner, "asas-ai/DarNERcorp": run_token_rows}


def main(files_json, out):
    with open(files_json, encoding="utf-8") as fh:
        files = json.load(fh)
    res = {"note": "Aggregate counts only, computed locally; no record, sentence or span of these datasets is included.", "datasets": []}
    for rid, info in files.items():
        agg, how = RUNNERS[rid]([p for p in info["files"] if p.endswith(".parquet")])
        res["datasets"].append({"dataset": rid, "revision": info["revision"], "license_on_card": info.get("license"),
                                "read_as": how, **agg})
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
