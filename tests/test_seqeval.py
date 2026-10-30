"""Tag transition checks agree with seqeval's strict mode."""
from hypothesis import given, settings
from hypothesis import strategies as st
from seqeval.scheme import BILOU, IOB2, IOBES, Tokens

from arabic_ner_validator.convert import check_tags
from conftest import load_fixtures

SEQ = {"IOB2": IOB2, "BIOES": IOBES, "BILUO": BILOU}
ALPHA = {"IOB2": ["O", "B-PER", "I-PER", "B-LOC", "I-LOC"],
         "BIOES": ["O", "B-PER", "I-PER", "E-PER", "S-PER", "B-LOC", "I-LOC", "E-LOC", "S-LOC"],
         "BILUO": ["O", "B-PER", "I-PER", "L-PER", "U-PER", "B-LOC", "I-LOC", "L-LOC", "U-LOC"]}


def seqeval_valid(tags, scheme):
    covered = set()
    try:
        for ent in Tokens(list(tags), SEQ[scheme]).entities:
            covered.update(range(ent.start, ent.end))
    except ValueError:  # a prefix the scheme does not have
        return False
    return covered == {i for i, t in enumerate(tags) if t != "O"}


def ours_valid(tags, scheme):
    return not check_tags(tags, scheme)


@settings(max_examples=3000, deadline=None)
@given(st.sampled_from(sorted(SEQ)).flatmap(lambda s: st.tuples(st.just(s), st.lists(st.sampled_from(ALPHA[s]), min_size=1, max_size=8))))
def test_random_sequences(case):
    scheme, tags = case
    assert ours_valid(tags, scheme) == seqeval_valid(tags, scheme), (scheme, tags)


def test_fixture_sequences():
    n = 0
    for fx in load_fixtures("dev") + load_fixtures("acceptance"):
        sch = (fx.get("options") or {}).get("scheme")
        if fx["format"] != "conll" or sch not in SEQ:
            continue
        for block in fx["input_payload"].lstrip("﻿").split("\n\n"):
            tags = [ln.split("\t")[-1].strip() for ln in block.splitlines() if ln.strip()]
            if tags and all(t == "O" or t[:2] in {p + "-" for p in "BIESLU"} for t in tags):
                assert ours_valid(tags, sch) == seqeval_valid(tags, sch), (fx["fixture_id"], tags)
                n += 1
    assert n >= 5
