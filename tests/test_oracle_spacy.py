"""100% agreement with spaCy's converters on every valid fixture (dev, and acceptance when present)."""
import pytest

from arabic_ner_validator.checks import Ctx
from arabic_ner_validator.io import parse
from arabic_ner_validator.report import decode
from conftest import load_fixtures
from oracle import compare_record, compare_tags

VALID = [f for f in load_fixtures("dev") + load_fixtures("acceptance") if f["valid"]]


def records_of(fx):
    st = dict(fx.get("options") or {})
    st["format"] = fx["format"]
    text, _, bom = decode(fx["input_payload"].encode("utf-8"))
    return parse(text, fx["format"], st), bom


@pytest.mark.parametrize("fx", VALID, ids=[f["fixture_id"] for f in VALID])
def test_oracle(fx):
    recs, bom = records_of(fx)
    for rec in recs:
        ctx = Ctx(rec, bom)
        if rec.from_tokens:
            res = compare_tags(rec.text, rec.tokens, rec.tags, rec.scheme or "IOB2")
        else:
            spans = [(ctx.omap.to_cp(s["start"], rec.offset_unit)[0], ctx.omap.to_cp(s["end"], rec.offset_unit)[0], s["label"]) for s in rec.spans]
            if rec.nested_policy == "allow" and any(
                    a[0] < b[1] and b[0] < a[1] for i, a in enumerate(spans) for b in spans[i + 1:]):
                pytest.skip("nested spans cannot be written as BILUO tags")
            toks = None
            if rec.tokens_cp is not None:
                toks = list(rec.tokens_cp)
            elif rec.tokens is not None:
                toks = [(ctx.omap.to_cp(a, rec.offset_unit)[0], ctx.omap.to_cp(b, rec.offset_unit)[0]) for a, b in rec.tokens]
            res = compare_record(rec.text, spans, toks)
        assert all(res.values()), res
