import hashlib
import json
import os

import pytest

from conftest import ROOT, load_fixtures
from fixture_runner import compare

DEV = load_fixtures("dev")


def test_manifest():
    with open(os.path.join(ROOT, "fixtures", "dev", "fixtures.jsonl"), "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    with open(os.path.join(ROOT, "fixtures", "FIXTURES.sha256"), encoding="utf-8") as fh:
        line = [x for x in fh.read().splitlines() if x.endswith("fixtures/dev/fixtures.jsonl")][0]
    assert line.split()[0] == digest
    assert len(DEV) == 100


@pytest.mark.parametrize("fx", DEV, ids=[f["fixture_id"] for f in DEV])
def test_dev_fixture(fx):
    ok, codes, sugg, report = compare(fx)
    assert codes == fx["expected_error_codes"]
    assert sugg == fx["expected_suggested_export"]


def test_categories_mapping_covers_dev():
    with open(os.path.join(ROOT, "src", "arabic_ner_validator", "data", "categories.json"), encoding="utf-8") as fh:
        cats = json.load(fh)["categories"]
    for fx in DEV:
        ok, codes, _, _ = compare(fx)
        if fx["valid"]:
            assert codes == []
        else:
            assert set(codes) & set(cats[fx["category"]]["codes"]), fx["fixture_id"]
