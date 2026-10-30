"""The browser port (web/validator.js) gives the same report as the Python package on every fixture."""
import json
import os
import shutil
import subprocess

import pytest

from arabic_ner_validator import validate
from conftest import ROOT

NODE = shutil.which("node")
FILES = [p for p in (os.path.join(ROOT, "fixtures", s, "fixtures.jsonl") for s in ("dev", "acceptance")) if os.path.exists(p)]


def strip(rep):
    rep = json.loads(json.dumps(rep, ensure_ascii=False))
    rep.pop("engine", None)
    return rep


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
def test_js_python_parity():
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "js", "run_fixtures.mjs"), *FILES],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    js = {}
    for line in out.splitlines():
        d = json.loads(line)
        js[d["fixture_id"]] = d
    n = 0
    diffs = []
    for path in FILES:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                fx = json.loads(line)
                st = dict(fx.get("options") or {})
                st["format"] = fx["format"]
                rep, _, reps = validate(fx["input_payload"].encode("utf-8"), st)
                if strip(rep) != strip(js[fx["fixture_id"]]["report"]):
                    diffs.append(fx["fixture_id"])
                n += 1
    assert n >= 100
    assert not diffs, diffs
