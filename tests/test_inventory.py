"""Every length-changing sequence of the Arabic drift inventory is caught by E011."""
import csv
import json
import os
import unicodedata

from arabic_ner_validator import validate
from conftest import ROOT


def rows():
    v = unicodedata.unidata_version
    path = os.path.join(ROOT, "inventory", "drift_sequences_%s.csv" % v)
    if not os.path.exists(path):
        path = os.path.join(ROOT, "inventory", "drift_sequences_16.0.0.csv")
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def seq(s):
    return "".join(chr(int(x[2:], 16)) for x in s.split())


def _codes(rec):
    data = (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")
    report, _, _ = validate(data, {"format": "canonical"})
    return report["records"][0]["findings"]


def test_length_changing_rows_detected():
    checked = skipped = 0
    missed = []
    for r in rows():
        s = seq(r["sequence"])
        for form, col in (("NFC", "len_delta_nfc"), ("NFKC", "len_delta_nfkc")):
            if int(r[col]) == 0:
                continue
            if unicodedata.normalize(form, s) != seq(r[form.lower()]):
                skipped += 1  # the runtime knows another Unicode version for this sequence
                continue
            text = "قال " + s + " عن الرياض أمس"
            t = unicodedata.normalize(form, text)
            a = t.index("الرياض")
            fs = _codes({"id": "g", "text": text, "offset_unit": "codepoint",
                         "spans": [{"start": a, "end": a + 6, "label": "LOC", "text": "الرياض"}]})
            e011 = [f for f in fs if f["code"] == "E011"]
            checked += 1
            if not e011 or e011[0]["detail"]["policy"] not in ("NFC", "NFKC"):
                missed.append((r["sequence"], form))
    assert checked >= 500
    assert not missed, missed[:10]
    assert skipped == 0 or unicodedata.unidata_version != "16.0.0"


def test_reorder_rows_detected_in_span_text():
    n = 0
    for r in rows():
        if r["kind"] != "reorder":
            continue
        s = seq(r["sequence"])
        if unicodedata.normalize("NFC", s) != seq(r["nfc"]):
            continue
        ent = "الرياض" + s
        text = "زار الوفد " + ent + " أمس"
        a = text.index(ent)
        fs = _codes({"id": "g", "text": text, "offset_unit": "codepoint",
                     "spans": [{"start": a, "end": a + len(ent), "label": "LOC", "text": unicodedata.normalize("NFC", ent)}]})
        assert any(f["code"] == "E011" and f["kind"] == "span_text_form" for f in fs), r["sequence"]
        n += 1
    # Python's own unicodedata tables decide which rows can be checked here: 2,402 with the Unicode 13.0
    # tables of Python 3.10, more with newer versions.
    assert n > 2000
