"""Write a repaired copy of the input from the audit diff (only with --apply-suggestions).

Only offsets change. Labels, record ids and the text stay as they are; a byte order mark at the start
of the file is dropped. Token formats (CoNLL, Hugging Face rows) carry no offsets, so only the byte
order mark is removed from them.
"""
from __future__ import annotations

import copy
import json

RANK = {"high": 3, "medium": 2, "low": 1}


def apply(data: bytes, fmt: str, records, repairs, min_confidence: str = "medium") -> tuple[bytes, list]:
    """(new file bytes, applied audit entries)."""
    body = data[3:] if data.startswith(b"\xef\xbb\xbf") else data
    applied = [r for r in repairs if r.get("action") == "remove_bom"]
    want = [r for r in repairs if r.get("span_index") is not None and RANK[r["confidence"]] >= RANK[min_confidence]]
    if fmt in ("conll", "hf_tokens") or not want:
        return body, applied
    text = body.decode("utf-8")
    by_rec = {}
    for r in want:
        by_rec.setdefault(r["record_id"], []).append(r)
    if fmt == "label_studio":
        tasks = json.loads(text)
        single = isinstance(tasks, dict)
        if single:
            tasks = [tasks]
        done = set()
        for rec in records:
            reps = by_rec.get(rec.id)
            if not reps or rec.source is None:
                continue
            ti = rec.task_index
            for rep in reps:
                key, (ai, ri), _ = rec.span_refs[rep["span_index"]]
                if (ti, key, ai, ri) in done:
                    continue
                same = [r2 for r2 in reps if rec.span_refs[r2["span_index"]][:2] == (key, (ai, ri))]
                if len({tuple(r2["new"]) for r2 in same}) != 1:
                    continue
                v = tasks[ti][key][ai]["result"][ri]["value"]
                v["start"], v["end"] = rep["new"]
                done.add((ti, key, ai, ri))
                applied += same
        out = json.dumps(tasks[0] if single else tasks, ensure_ascii=False, indent=2) + "\n"
        return out.encode("utf-8"), applied
    lines = text.split("\n")
    stripped = text.lstrip(" \t\r\n")
    if fmt == "canonical" and stripped.startswith("["):
        arr = json.loads(stripped)
        for k, rec in enumerate(records):
            for rep in by_rec.get(rec.id, []):
                path, j, kind = rec.span_refs[rep["span_index"]]
                arr[k][path][j]["start"], arr[k][path][j]["end"] = rep["new"]
                applied.append(rep)
        return (json.dumps(arr, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), applied
    for rec in records:
        reps = by_rec.get(rec.id)
        if not reps or rec.line is None or rec.source is None:
            continue
        obj = copy.deepcopy(rec.source)
        for rep in reps:
            path, j, kind = rec.span_refs[rep["span_index"]]
            s, e = rep["new"]
            if kind == "list":
                container = obj[1]["entities"] if path == "[1].entities" else obj[path]
                container[j][0], container[j][1] = s, e
            elif kind == "doccano":
                obj[path][j]["start_offset"], obj[path][j]["end_offset"] = s, e
            else:
                obj[path][j]["start"], obj[path][j]["end"] = s, e
            applied.append(rep)
        cr = lines[rec.line - 1].endswith("\r")
        lines[rec.line - 1] = json.dumps(obj, ensure_ascii=False) + ("\r" if cr else "")
    return "\n".join(lines).encode("utf-8"), applied
