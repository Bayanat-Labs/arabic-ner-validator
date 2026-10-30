"""Property tests on generated Arabic text: offsets -> tags -> offsets is the identity (10,000
cases), our tags equal spaCy's, and well-formed records produce no error or warning."""
import csv
import json
import os

from hypothesis import given, settings
from hypothesis import strategies as st

from arabic_ner_validator import validate
from arabic_ner_validator.convert import offsets_to_tags, tags_to_offsets
from conftest import ROOT
from oracle import doc_for
from spacy.training import offsets_to_biluo_tags


def _pool():
    words = ["الرياض", "جدة", "مَكَّةُ", "القاهرة", "بيروت", "الأمم", "المتحدة", "جامعة", "الملك", "سعود", "عَمّان",
             "الطائـــف", "ابنُ", "سينا", "Microsoft", "UNESCO", "٢٠٢٦", "2026", "\U0001F600", "زار", "الوفد", "مدينة"]
    path = os.path.join(ROOT, "inventory", "drift_sequences_16.0.0.csv")
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["kind"] in ("single", "composition"):
                s = "".join(chr(int(x[2:], 16)) for x in r["sequence"].split())
                words.append("ب" + s + "ر")
    return words


POOL = _pool()
LABELS = ["PER", "LOC", "ORG"]


@st.composite
def record(draw):
    n = draw(st.integers(min_value=1, max_value=8))
    words = [draw(st.sampled_from(POOL)) for _ in range(n)]
    toks, pos = [], 0
    for w in words:
        toks.append((pos, pos + len(w)))
        pos += len(w) + 1
    text = " ".join(words)
    ents, i = [], 0
    while i < n:
        if draw(st.booleans()):
            j = draw(st.integers(min_value=i, max_value=min(n - 1, i + 2)))
            if words[i] == "\U0001F600" or words[j] == "\U0001F600":
                i += 1
                continue  # an entity edge on an emoji has no letter there
            ents.append((toks[i][0], toks[j][1], draw(st.sampled_from(LABELS))))
            i = j + 1
        else:
            i += 1
    return text, toks, ents


@settings(max_examples=10000, deadline=None)
@given(record())
def test_round_trip(case):
    text, toks, ents = case
    for scheme in ("IOB2", "BIOES", "BILUO", "IOE2", "IO", "IOB1"):
        tags = offsets_to_tags(toks, ents, scheme)
        back = tags_to_offsets(toks, tags, scheme)
        if scheme == "IO":
            continue  # IO cannot separate two adjacent entities of one label
        assert sorted(back) == sorted(ents), (scheme, tags)
    doc, dtoks = doc_for(text, toks)
    assert offsets_to_biluo_tags(doc, ents) == offsets_to_tags(dtoks, ents, "BILUO")


@settings(max_examples=2000, deadline=None)
@given(record())
def test_no_false_positives(case):
    text, toks, ents = case
    rec = {"id": "h", "text": text, "offset_unit": "codepoint", "nested_policy": "forbid",
           "spans": [{"start": s, "end": e, "label": lab, "text": text[s:e]} for s, e, lab in ents]}
    report, _, _ = validate((json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8"), {"format": "canonical"})
    flagged = [f["code"] for f in report["records"][0]["findings"] if f["severity"] in ("error", "warning")]
    assert flagged == [], (text, ents, flagged)
