"""Run a fixture through the validator and compare with its expectations."""
import json

from arabic_ner_validator import validate

KEYS = ("record_id", "span_index", "old", "new", "reason_code", "confidence")


def run_fixture(fx):
    settings = dict(fx.get("options") or {})
    settings["format"] = fx["format"]
    report, _, repairs = validate(fx["input_payload"].encode("utf-8"), settings)
    return report, repairs


def flagged_codes(report):
    codes = {f["code"] for f in report["file_findings"] if f["severity"] in ("error", "warning")}
    for r in report["records"]:
        codes |= {f["code"] for f in r["findings"] if f["severity"] in ("error", "warning")}
    return sorted(codes)


def project(repairs):
    out = []
    for d in repairs:
        p = {k: d.get(k) for k in KEYS}
        if d.get("action"):
            p["action"] = d["action"]
        out.append(p)
    return out or None


def compare(fx):
    report, repairs = run_fixture(fx)
    got_codes = flagged_codes(report)
    got_sugg = project(repairs)
    exp_sugg = fx["expected_suggested_export"]
    return got_codes == fx["expected_error_codes"] and got_sugg == exp_sugg, got_codes, got_sugg, report
