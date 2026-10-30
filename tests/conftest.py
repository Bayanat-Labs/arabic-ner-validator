import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:  # test the installed package when there is one, else the source tree
    import arabic_ner_validator  # noqa: F401
except ImportError:
    sys.path.insert(0, os.path.join(ROOT, "src"))


def load_fixtures(split):
    path = os.path.join(ROOT, "fixtures", split, "fixtures.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
