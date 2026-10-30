import json
import os

import pytest
from jsonschema import Draft202012Validator

from arabic_ner_validator import validate
from conftest import ROOT

with open(os.path.join(ROOT, "schema", "input.schema.json"), encoding="utf-8") as fh:
    SCHEMA = json.load(fh)
with open(os.path.join(ROOT, "schema", "rejected_examples.jsonl"), encoding="utf-8") as fh:
    REJECTED = [json.loads(x) for x in fh if x.strip()]


def test_schema_is_valid_and_packaged():
    Draft202012Validator.check_schema(SCHEMA)
    with open(os.path.join(ROOT, "src", "arabic_ner_validator", "data", "input.schema.json"), encoding="utf-8") as fh:
        assert json.load(fh) == SCHEMA


def test_twenty_examples():
    assert len(REJECTED) == 20


@pytest.mark.parametrize("ex", REJECTED, ids=[e["name"] for e in REJECTED])
def test_rejected(ex):
    assert list(Draft202012Validator(SCHEMA).iter_errors(ex["record"])), "schema accepts it"
    data = (json.dumps(ex["record"], ensure_ascii=False) + "\n").encode("utf-8")
    report, _, _ = validate(data, {"format": "canonical"})
    codes = {f["code"] for r in report["records"] for f in r["findings"]}
    assert ex["expected_code"] in codes


def test_valid_dev_records_pass_schema():
    from conftest import load_fixtures
    v = Draft202012Validator(SCHEMA)
    n = 0
    for fx in load_fixtures("dev"):
        if fx["format"] != "canonical":
            continue
        for line in fx["input_payload"].lstrip("﻿").splitlines():
            if line.strip():
                assert not list(v.iter_errors(json.loads(line))), fx["fixture_id"]
                n += 1
    assert n > 50


def test_missing_unit_gives_hint():
    rec = {"id": "h", "text": "😀 الرياض", "spans": [{"start": 3, "end": 9, "label": "LOC", "text": "الرياض"}]}
    report, _, _ = validate((json.dumps(rec, ensure_ascii=False) + "\n").encode(), {"format": "canonical"})
    f = [f for f in report["records"][0]["findings"] if f["code"] == "E019"][0]
    assert "utf16 for 1 of 1" in f["message_en"]
    assert report["records"][0]["valid_span_count"] == 0


def test_invalid_utf8():
    report, _, _ = validate(b'{"text": "\xd8"}\n', {"format": "canonical"})
    assert report["file_findings"][0]["code"] == "E017"
    assert report["file_findings"][0]["detail"]["byte"] == 10
