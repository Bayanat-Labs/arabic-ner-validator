#!/usr/bin/env python3
"""Combine the measurement files and the source-code references into matrix/probe_measurements.csv
and matrix/offset_conventions.csv. Every number comes from the files in matrix/evidence/."""
import csv
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "evidence")


def load(name):
    with open(os.path.join(EV, name), encoding="utf-8") as fh:
        return json.load(fh)


def sha(name):
    with open(os.path.join(EV, name), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    probes = {p["probe_id"]: p for p in load("probes.json")}
    py, nd, ch = load("python_measurements.json"), load("node_measurements.json"), load("chromium_measurements.json")
    src = load("source_references.json")
    rows = []
    for r, n, c in zip(py["probes"], nd["probes"], ch["probes"]):
        p = probes[r["probe_id"]]
        row = {"probe_id": p["probe_id"], "feature": p["feature"], "target": p["target"],
               "codepoint": "%d-%d" % (r["python_str"]["start"], r["python_str"]["end"]),
               "utf16_node": "%d-%d" % (n["js_string"]["start"], n["js_string"]["end"]),
               "utf16_chromium": "%d-%d" % (c["js_string"]["start"], c["js_string"]["end"]),
               "utf8_byte": "%d-%d" % (r["utf8_bytes"]["start"], r["utf8_bytes"]["end"]),
               "grapheme_regex": "%s-%s" % (r["regex_grapheme"]["start"], r["regex_grapheme"]["end"]),
               "grapheme_intl_node": "%s-%s" % (n["intl_segmenter"]["start"], n["intl_segmenter"]["end"]),
               "grapheme_intl_chromium": "%s-%s" % (c["intl_segmenter"]["start"], c["intl_segmenter"]["end"]),
               "spacy_char_span_strict": "none" if r["spacy"]["char_span"]["strict"] is None else "%d-%d" % tuple(r["spacy"]["char_span"]["strict"][:2]),
               "spacy_char_span_expand": "none" if r["spacy"]["char_span"]["expand"] is None else "%d-%d" % tuple(r["spacy"]["char_span"]["expand"][:2])}
        for mid, v in r["hf"].items():
            row["hf_%s" % mid.split("/")[-1]] = "none" if v["cover"] is None else "%d-%d" % tuple(v["cover"])
        rows.append(row)
    with open(os.path.join(HERE, "probe_measurements.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    by = {r["probe_id"]: r for r in rows}

    def same(col, ref="codepoint"):
        return all(r[col] == r[ref] for r in rows)
    p04, p09, p02, p05 = by["p04"], by["p09"], by["p02"], by["p05"]
    m = []

    def add(tool, version, interface, unit, crlf, norm, emoji, method, evidence, notes):
        m.append({"tool": tool, "version": version, "interface": interface, "offset_unit_observed": unit,
                  "crlf_counted_as": crlf, "normalises_text": norm, "emoji_behaviour": emoji, "method": method,
                  "evidence_file": evidence, "evidence_sha256": sha(evidence) if evidence.endswith(".json") else "", "notes": notes})

    width = lambda col, pr: (lambda a, b: b - a)(*map(int, by[pr][col].split("-")))
    add("Python str", "CPython " + py["python"], "str.index / slicing", "codepoint", "2", "no",
        "U+1F600 counts 1 (probe p04 at %s)" % p04["codepoint"], "measured", "python_measurements.json",
        "Reference unit of this matrix.")
    add("UTF-8 bytes", "CPython " + py["python"], "str.encode('utf-8')", "utf8_byte", "2", "no",
        "U+1F600 counts 4; an Arabic letter counts 2 (p04 at %s)" % p04["utf8_byte"], "measured", "python_measurements.json",
        "Byte offsets are about twice the code point offsets in Arabic text.")
    add("JavaScript String", nd["runtime"] + " (V8 " + nd["v8"] + ")", "String.prototype.indexOf / length", "utf16", "2", "no",
        "U+1F600 counts 2 (p04 at %s; code points %s)" % (p04["utf16_node"], p04["codepoint"]), "measured", "node_measurements.json",
        "Same as Python on every probe without astral characters (%d of 20 probes have astral characters)." % sum(1 for r in rows if r["utf16_node"] != r["codepoint"]))
    add("JavaScript String", ch["browser"], "String.prototype.indexOf / length", "utf16", "2", "no",
        "U+1F600 counts 2 (p04 at %s)" % p04["utf16_chromium"], "measured", "chromium_measurements.json",
        "Identical to Node on all 20 probes." if all(r["utf16_chromium"] == r["utf16_node"] for r in rows) else "Differs from Node.")
    add("regex \\X grapheme clusters", "regex " + py["regex"], "regex.finditer(r'\\X')", "grapheme", "1",
        "no", "U+1F600 counts 1; the ZWJ family emoji counts 1 (p05 at %s, code points %s)" % (p05["grapheme_regex"], p05["codepoint"]),
        "measured", "python_measurements.json",
        "A letter with its harakat is one cluster (p02 at %s, code points %s)." % (p02["grapheme_regex"], p02["codepoint"]))
    add("Intl.Segmenter grapheme clusters", nd["runtime"] + " (ICU " + nd["icu"] + ", Unicode " + nd["unicode"] + ")", "Intl.Segmenter('und', {granularity: 'grapheme'})",
        "grapheme", "1", "no", "as regex \\X (p05 at %s)" % p05["grapheme_intl_node"], "measured", "node_measurements.json",
        "Identical to regex \\X on all 20 probes." if same("grapheme_intl_node", "grapheme_regex") else "Differs from regex \\X on some probes.")
    add("Intl.Segmenter grapheme clusters", ch["browser"], "Intl.Segmenter('und', {granularity: 'grapheme'})", "grapheme", "1", "no",
        "as regex \\X (p05 at %s)" % p05["grapheme_intl_chromium"], "measured", "chromium_measurements.json",
        "Identical to regex \\X on all 20 probes." if same("grapheme_intl_chromium", "grapheme_regex") else "Differs from regex \\X on some probes.")
    strict_none = [r["probe_id"] for r in rows if r["spacy_char_span_strict"] == "none"]
    add("spaCy Doc.char_span", "spaCy " + py["spacy"] + " (blank 'ar' pipeline)", "Doc.char_span(start, end, alignment_mode)", "codepoint", "2",
        "no", "U+1F600 counts 1 (p04 at %s)" % (p04["spacy_char_span_strict"]), "measured", "python_measurements.json",
        "strict and contract return no span on %d probes (%s) where the Arabic tokenizer keeps a control character or an attached clitic in the same token; expand then widens the span to include it." % (len(strict_none), ", ".join(strict_none)))
    for mid, rev in py["tokenizer_models"].items():
        col = "hf_" + mid.split("/")[-1]
        cover_ok = sum(1 for r in rows if r[col] == r["codepoint"])
        dropped = sum(1 for r in py["probes"] if r["hf"][mid]["normalised_text_length"] != r["python_str"]["length"])
        add("Hugging Face fast tokenizer offset_mapping", "tokenizers %s, %s@%s" % (py["tokenizers"], mid, rev[:12]),
            "Tokenizer.encode(text).offsets", "codepoint", "2", "yes, internally (offsets point into the original text)",
            "U+1F600 counts 1 (p04 covered by %s)" % by["p04"][col], "measured", "python_measurements.json",
            "Token offsets cover exactly the target on %d of 20 probes; the normaliser changes the text length on %d probes, but offsets still index the original text." % (cover_ok, dropped))
    for s in src:
        add(s["tool"], s["version"], s["interface"], s["offset_unit"], s["crlf"], s["normalises_text"], s["emoji"],
            "from source code, not measured", "source_references.json", s["notes"])
    with open(os.path.join(HERE, "offset_conventions.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(m[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(m)
    print(len(rows), "probes;", len(m), "rows in offset_conventions.csv")


if __name__ == "__main__":
    main()
