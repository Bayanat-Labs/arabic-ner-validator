#!/usr/bin/env python3
"""Measure how Python, UTF-8, regex grapheme clusters, spaCy and Hugging Face fast tokenizers count
positions on the 20 probes. Writes matrix/evidence/probes.json and matrix/evidence/python_measurements.json.

  python matrix/measure.py TOKENIZERS_JSON
TOKENIZERS_JSON maps a model id to {"revision", "path"} of its tokenizer.json (downloaded beforehand).
"""
import json
import os
import platform
import sys
import unicodedata

import regex

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from probes import PROBES, target_cp  # noqa: E402

EV = os.path.join(HERE, "evidence")


def graphemes(text):
    return [m.group(0) for m in regex.finditer(r"\X", text)]


def g_index(text, cp):
    pos = 0
    for i, g in enumerate(graphemes(text)):
        if pos == cp:
            return i
        pos += len(g)
    return len(graphemes(text)) if pos == cp else None


def main(tok_json):
    os.makedirs(EV, exist_ok=True)
    probes = []
    for pid, feature, text, target, after in PROBES:
        s, e = target_cp(text, target, after)
        probes.append({"probe_id": pid, "feature": feature, "text": text, "target": target, "start_codepoint": s, "end_codepoint": e})
    with open(os.path.join(EV, "probes.json"), "w", encoding="utf-8") as fh:
        json.dump(probes, fh, ensure_ascii=False, indent=1)
    import spacy
    import tokenizers
    from tokenizers import Tokenizer
    nlp = spacy.blank("ar")
    with open(tok_json, encoding="utf-8") as fh:
        toks = json.load(fh)
    loaded = {mid: Tokenizer.from_file(v["path"]) for mid, v in toks.items()}
    out = {"python": platform.python_version(), "unicodedata": unicodedata.unidata_version, "regex": regex.__version__,
           "spacy": spacy.__version__, "tokenizers": tokenizers.__version__,
           "tokenizer_models": {mid: v["revision"] for mid, v in toks.items()}, "probes": []}
    for p in probes:
        text, s, e = p["text"], p["start_codepoint"], p["end_codepoint"]
        b = text.encode("utf-8")
        row = {"probe_id": p["probe_id"],
               "python_str": {"start": s, "end": e, "length": len(text)},
               "utf8_bytes": {"start": len(text[:s].encode()), "end": len(text[:e].encode()), "length": len(b),
                              "find": b.find(p["target"].encode())},
               "regex_grapheme": {"start": g_index(text, s), "end": g_index(text, e), "length": len(graphemes(text))},
               "normalised_length": {f: len(unicodedata.normalize(f, text)) for f in ("NFC", "NFKC")}}
        doc = nlp(text)
        row["spacy"] = {"doc_text_equals_input": doc.text == text, "tokens": [t.text for t in doc],
                        "char_span": {m: (lambda sp: None if sp is None else [sp.start_char, sp.end_char, sp.text])(doc.char_span(s, e, alignment_mode=m))
                                      for m in ("strict", "contract", "expand")}}
        row["hf"] = {}
        for mid, tk in loaded.items():
            enc = tk.encode(text, add_special_tokens=False)
            cover = [(a, z) for (a, z) in enc.offsets if a < e and z > s and z > a]
            norm = tk.normalizer.normalize_str(text) if tk.normalizer is not None else text
            ctrl = [i for i, ch in enumerate(text) if ch in "‌‎‏؜﻿"]
            covered_ctrl = [i for i in ctrl if any(a <= i < z for a, z in enc.offsets)]
            row["hf"][mid] = {"cover": [min(a for a, _ in cover), max(z for _, z in cover)] if cover else None,
                              "tokens_in_span": [enc.tokens[k] for k, (a, z) in enumerate(enc.offsets) if a < e and z > s and z > a],
                              "normalised_text_length": len(norm), "max_offset": max((z for _, z in enc.offsets), default=0),
                              "controls_in_text": len(ctrl), "controls_covered_by_a_token": len(covered_ctrl)}
        out["probes"].append(row)
    with open(os.path.join(EV, "python_measurements.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("ok", len(out["probes"]))


if __name__ == "__main__":
    main(sys.argv[1])
