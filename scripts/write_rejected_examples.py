#!/usr/bin/env python3
"""Write schema/rejected_examples.jsonl: 20 canonical records that the input contract rejects."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = "زار الوفد مدينة الرياض"
OK = {"start": 16, "end": 22, "label": "LOC"}
EX = [
    ("missing-offset-unit", "offset_unit is missing; the unit is never guessed", {"id": "x1", "text": T, "spans": [OK]}, "E019"),
    ("unknown-offset-unit", "offset_unit 'char' is not one of the four units", {"id": "x2", "text": T, "offset_unit": "char", "spans": [OK]}, "E020"),
    ("null-offset-unit", "offset_unit is null", {"id": "x3", "text": T, "offset_unit": None, "spans": [OK]}, "E020"),
    ("missing-text", "text is missing", {"id": "x4", "offset_unit": "codepoint", "spans": [OK]}, "E020"),
    ("text-not-string", "text is a number", {"id": "x5", "text": 42, "offset_unit": "codepoint", "spans": []}, "E020"),
    ("missing-spans", "spans is missing", {"id": "x6", "text": T, "offset_unit": "codepoint"}, "E020"),
    ("spans-not-array", "spans is an object", {"id": "x7", "text": T, "offset_unit": "codepoint", "spans": {"start": 16, "end": 22, "label": "LOC"}}, "E020"),
    ("span-missing-end", "a span has no end", {"id": "x8", "text": T, "offset_unit": "codepoint", "spans": [{"start": 16, "label": "LOC"}]}, "E020"),
    ("span-start-string", "a span start is a string", {"id": "x9", "text": T, "offset_unit": "codepoint", "spans": [{"start": "16", "end": 22, "label": "LOC"}]}, "E020"),
    ("span-start-fraction", "a span start is not an integer", {"id": "x10", "text": T, "offset_unit": "codepoint", "spans": [{"start": 16.5, "end": 22, "label": "LOC"}]}, "E020"),
    ("span-label-empty", "a span label is empty", {"id": "x11", "text": T, "offset_unit": "codepoint", "spans": [{"start": 16, "end": 22, "label": ""}]}, "E020"),
    ("span-label-missing", "a span has no label", {"id": "x12", "text": T, "offset_unit": "codepoint", "spans": [{"start": 16, "end": 22}]}, "E020"),
    ("span-extra-key", "a span has an unknown key", {"id": "x13", "text": T, "offset_unit": "codepoint", "spans": [{"start": 16, "end": 22, "label": "LOC", "type": "place"}]}, "E020"),
    ("scheme-alias", "scheme 'BIO' is an alias accepted on the command line, not in a record", {"id": "x14", "text": T, "offset_unit": "codepoint", "scheme": "BIO", "spans": [OK]}, "E020"),
    ("nested-policy-unknown", "nested_policy 'maybe'", {"id": "x15", "text": T, "offset_unit": "codepoint", "nested_policy": "maybe", "spans": [OK]}, "E020"),
    ("clitic-policy-boolean", "clitic_policy is a boolean", {"id": "x16", "text": T, "offset_unit": "codepoint", "clitic_policy": True, "spans": [OK]}, "E020"),
    ("label-set-repeats", "label_set repeats a label", {"id": "x17", "text": T, "offset_unit": "codepoint", "label_set": ["LOC", "LOC"], "spans": [OK]}, "E020"),
    ("normalization-lowercase", "normalization_declared 'nfc' is not a recognised value", {"id": "x18", "text": T, "offset_unit": "codepoint", "normalization_declared": "nfc", "spans": [OK]}, "E020"),
    ("doccano-key-in-canonical", "a doccano key in a canonical record", {"id": "x19", "text": T, "offset_unit": "codepoint", "spans": [], "label": [[16, 22, "LOC"]]}, "E020"),
    ("tags-without-tokens", "tags without tokens", {"id": "x20", "text": T, "offset_unit": "codepoint", "spans": [], "tags": ["O", "O", "O", "B-LOC"]}, "E020"),
]
assert len(EX) == 20
with open(os.path.join(ROOT, "schema", "rejected_examples.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
    for name, desc, rec, code in EX:
        fh.write(json.dumps({"name": name, "description": desc, "expected_code": code, "record": rec}, ensure_ascii=False) + "\n")
print("wrote 20")
