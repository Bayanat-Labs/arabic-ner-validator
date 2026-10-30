"""Validation entry point and reports (JSON, shareable JSON without text, CSV)."""
from __future__ import annotations

import csv
import hashlib
import io as _io
import json
import os
import unicodedata

import regex

from . import __version__
from .checks import check_record
from .io import FORMATS, detect_format, parse

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "data", "codes.json"), encoding="utf-8") as _fh:
    CODES = json.load(_fh)

SETTING_KEYS = ("format", "offset_unit", "scheme", "nested_policy", "clitic_policy", "label_set",
                "normalization_declared", "tag_names")


def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def settings_hash(settings: dict) -> str:
    return hashlib.sha256(canonical_json({k: settings.get(k) for k in SETTING_KEYS}).encode("utf-8")).hexdigest()


POLICY_NAMES = {
    "NFC": ("NFC normalisation", "تطبيع NFC"),
    "NFKC": ("NFKC normalisation", "تطبيع NFKC"),
    "NFD": ("NFD normalisation", "تطبيع NFD"),
    "NFKD": ("NFKD normalisation", "تطبيع NFKD"),
    "remove_tatweel": ("tatweel removal", "حذف التطويل"),
    "remove_diacritics": ("diacritic removal", "حذف التشكيل"),
    "crlf_to_lf": ("CRLF to LF conversion", "تحويل CRLF إلى LF"),
    "lf_to_crlf": ("LF to CRLF conversion", "تحويل LF إلى CRLF"),
    "strip_bom": ("removing U+FEFF", "حذف U+FEFF"),
    "add_bom": ("adding a byte order mark", "إضافة علامة ترتيب البايتات"),
}


def _policy_label(v, lang):
    k = 0 if lang == "en" else 1
    sep = ", " if lang == "en" else "، "
    return sep.join(POLICY_NAMES.get(p.strip(), (p.strip(), p.strip()))[k] for p in str(v).split(","))


def render(code, kind, values, lang):
    msgs = CODES[code]["messages"]
    tmpl = (msgs.get(kind) or msgs.get("default") or next(iter(msgs.values())))[lang]
    out = tmpl
    for k, v in values.items():
        if k == "policy":
            v = _policy_label(v, lang)
        out = out.replace("{" + k + "}", str(v))
    return out


def _values(f):
    vals = dict(f["detail"])
    vals["span"] = f["span_index"]
    vals["start"] = f["start"]
    vals["end"] = f["end"]
    if "token" in f["detail"]:
        vals["token"] = f["detail"]["token"] + 1
    return vals


def _sort_key(f):
    return (f["span_index"] is not None, f["span_index"] if f["span_index"] is not None else -1, f["code"], f["kind"] or "")


def decode(data: bytes):
    """(text or None, file_findings, file_bom)."""
    ff = []
    bom = data.startswith(b"\xef\xbb\xbf")
    body = data[3:] if bom else data
    if bom:
        ff.append({"code": "E018", "kind": "file", "span_index": None, "start": None, "end": None, "detail": {}})
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as ex:
        ff.append({"code": "E017", "kind": None, "span_index": None, "start": None, "end": None,
                   "detail": {"byte": ex.start + (3 if bom else 0)}})
        return None, ff, bom
    return text, ff, bom


def validate(data: bytes, settings: dict | None = None):
    """Validate the bytes of one input file. Returns (report, records, repairs)."""
    settings = dict(settings or {})
    fmt = settings.get("format") or "auto"
    text, file_findings, bom = decode(data)
    if text is not None and fmt == "auto":
        fmt = detect_format(text)
    settings["format"] = fmt
    if fmt not in FORMATS and fmt != "auto":
        raise ValueError("unknown format: %s" % fmt)
    records, out_records, repairs = [], [], []
    if bom:
        repairs.append({"record_id": None, "span_index": None, "old": None, "new": None, "reason_code": "E018",
                        "confidence": "high", "action": "remove_bom"})
    if text is not None:
        records = parse(text, fmt, settings)
    n_spans = n_valid = 0
    for rec in records:
        fs, reps, conv, valid = check_record(rec, bom)
        fs.sort(key=_sort_key)
        repairs += reps
        n_spans += len(rec.spans)
        n_valid += valid
        out_records.append({
            "id": rec.id, "line": rec.line, "text": rec.text,
            "offset_unit": rec.offset_unit, "normalization_declared": rec.normalization_declared,
            "findings": [_finish(f) for f in fs],
            "span_count": len(rec.spans), "valid_span_count": valid,
            "spans": [dict(sp) for sp in rec.spans],
            "conversion_map": conv,
        })
    all_f = [_finish(f) for f in file_findings] + [f for r in out_records for f in r["findings"]]
    by_code, by_sev = {}, {"error": 0, "warning": 0, "info": 0}
    for f in all_f:
        by_code[f["code"]] = by_code.get(f["code"], 0) + 1
        by_sev[f["severity"]] += 1
    report = {
        "tool": "arabic-ner-validator",
        "validator_version": __version__,
        "report_version": 1,
        "engine": {"language": "python", "unicode_normalization": unicodedata.unidata_version,
                   "grapheme_segmentation": "regex " + regex.__version__},
        "settings": {k: settings.get(k) for k in SETTING_KEYS},
        "settings_hash": settings_hash(settings),
        "input": {"format": fmt, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "records": len(records)},
        "summary": {"records": len(records),
                    "records_with_errors": sum(1 for r in out_records if any(f["severity"] == "error" for f in r["findings"])),
                    "spans": n_spans, "valid_spans": n_valid,
                    "by_severity": by_sev, "by_code": dict(sorted(by_code.items()))},
        "file_findings": [_finish(f) for f in file_findings],
        "records": out_records,
        "suggested_export": {"audit_diff": repairs} if repairs else None,
    }
    return report, records, repairs


def _finish(f):
    vals = _values(f)
    return {"code": f["code"], "severity": CODES[f["code"]]["severity"], "span_index": f["span_index"],
            "start": f["start"], "end": f["end"], "kind": f["kind"], "detail": f["detail"],
            "message_en": render(f["code"], f["kind"], vals, "en"), "message_ar": render(f["code"], f["kind"], vals, "ar")}


def share_report(report: dict) -> dict:
    """The report without any text: ids, codes, offsets, counts, version and settings hash only."""
    out = {k: report[k] for k in ("tool", "validator_version", "report_version", "engine", "settings_hash", "summary")}
    out["share"] = True
    s = dict(report["settings"])
    s["label_set"] = None if s.get("label_set") is None else len(s["label_set"])
    s["tag_names"] = None if s.get("tag_names") is None else len(s["tag_names"])
    out["settings"] = s
    out["input"] = {"format": report["input"]["format"], "bytes": report["input"]["bytes"], "records": report["input"]["records"]}

    def strip(f):
        return {"code": f["code"], "severity": f["severity"], "span_index": f["span_index"], "start": f["start"],
                "end": f["end"], "kind": f["kind"]}

    out["file_findings"] = [strip(f) for f in report["file_findings"]]
    out["records"] = [{"id": r["id"], "line": r["line"], "offset_unit": r["offset_unit"],
                       "span_count": r["span_count"], "valid_span_count": r["valid_span_count"],
                       "findings": [strip(f) for f in r["findings"]],
                       "conversion_map": r["conversion_map"]} for r in report["records"]]
    se = report["suggested_export"]
    out["suggested_export"] = None if se is None else {"audit_diff": [
        {k: v for k, v in d.items() if k != "label"} for d in se["audit_diff"]]}
    return out


def csv_report(report: dict) -> str:
    buf = _io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["record_id", "line", "span_index", "code", "severity", "kind", "start", "end", "message_en"])
    for f in report["file_findings"]:
        w.writerow(["", "", "", f["code"], f["severity"], f["kind"] or "", "", "", f.get("message_en", "")])
    for r in report["records"]:
        for f in r["findings"]:
            w.writerow([r["id"], r["line"] if r["line"] is not None else "", "" if f["span_index"] is None else f["span_index"],
                        f["code"], f["severity"], f["kind"] or "", "" if f["start"] is None else f["start"],
                        "" if f["end"] is None else f["end"], f.get("message_en", "")])
    return buf.getvalue()
