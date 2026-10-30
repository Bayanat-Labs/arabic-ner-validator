"""Command line: arabic-ner-validator check | convert | codes | schema."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .convert import ALIASES, SCHEMES, convert_tags, tags_to_offsets
from .io import FORMATS, detect_format, parse
from .repair import apply
from .report import CODES, csv_report, decode, share_report, validate

UNITS = ("utf8_byte", "codepoint", "utf16", "grapheme")
HERE = os.path.dirname(os.path.abspath(__file__))


def _scheme(v):
    if v is None:
        return None
    v2 = ALIASES.get(v.upper(), v.upper())
    if v2 not in SCHEMES:
        raise argparse.ArgumentTypeError("unknown scheme %s" % v)
    return v2


def _settings(a):
    return {
        "format": a.format,
        "offset_unit": a.offset_unit,
        "scheme": a.scheme,
        "nested_policy": a.nested_policy,
        "clitic_policy": a.clitic_policy,
        "label_set": [x for x in a.labels.split(",") if x] if a.labels else None,
        "normalization_declared": a.normalization,
        "tag_names": [x for x in a.tag_names.split(",") if x] if a.tag_names else None,
    }


def _common(p):
    p.add_argument("input", help="input file ('-' reads standard input)")
    p.add_argument("--format", default="auto", choices=("auto",) + FORMATS,
                   help="input format (default: detected from the content; the offset unit is never detected)")
    p.add_argument("--offset-unit", choices=UNITS,
                   help="unit of the offsets in the file; required unless every record declares it")
    p.add_argument("--scheme", type=_scheme, help="tag scheme: IO, IOB1, IOB2 (BIO), IOE1, IOE2, BIOES (IOBES), BILUO (BILOU)")
    p.add_argument("--nested-policy", choices=("forbid", "allow"), help="nested spans (default forbid)")
    p.add_argument("--clitic-policy", choices=("include", "exclude", "unspecified"),
                   help="proclitics at the start of a name: inside the span, outside it, or not checked (default)")
    p.add_argument("--labels", help="comma-separated label set, e.g. PER,LOC,ORG")
    p.add_argument("--normalization", help="normalisation the text is declared to be in: none, NFC, NFKC, policy:<id>")
    p.add_argument("--tag-names", help="comma-separated tag names for integer tags (Hugging Face rows)")


def _read(path):
    if path == "-":
        return sys.stdin.buffer.read()
    with open(path, "rb") as fh:
        return fh.read()


def cmd_check(a):
    data = _read(a.input)
    if len(data) > a.max_bytes:
        print("input is larger than --max-bytes (%d)" % a.max_bytes, file=sys.stderr)
        return 2
    report, records, repairs = validate(data, _settings(a))
    if len(records) > a.max_records:
        print("input has more than --max-records (%d) records" % a.max_records, file=sys.stderr)
        return 2
    out = share_report(report) if a.share else report
    if a.json:
        txt = json.dumps(out, ensure_ascii=False, indent=1) + "\n"
        if a.json == "-":
            sys.stdout.write(txt)
        else:
            with open(a.json, "w", encoding="utf-8") as fh:
                fh.write(txt)
    if a.csv:
        with open(a.csv, "w", encoding="utf-8", newline="") as fh:
            fh.write(csv_report(report))
    if a.apply_suggestions:
        if os.path.abspath(a.apply_suggestions) == os.path.abspath(a.input):
            print("--apply-suggestions must name a new file, not the input", file=sys.stderr)
            return 2
        new, applied = apply(data, report["input"]["format"], records, repairs, a.min_confidence)
        with open(a.apply_suggestions, "wb") as fh:
            fh.write(new)
        if not a.quiet:
            print("wrote %s (%d changes applied)" % (a.apply_suggestions, len(applied)), file=sys.stderr)
    if not a.quiet and a.json != "-":
        s = report["summary"]
        print("arabic-ner-validator %s: %d records, %d spans, %d valid spans; %d errors, %d warnings, %d notes" % (
            __version__, s["records"], s["spans"], s["valid_spans"], s["by_severity"]["error"],
            s["by_severity"]["warning"], s["by_severity"]["info"]))
        for code, n in s["by_code"].items():
            print("  %s %-5d %s" % (code, n, CODES[code]["title_" + a.lang]))
        if a.verbose:
            for f in report["file_findings"]:
                print("  file: %s %s" % (f["code"], f["message_" + a.lang]))
            for r in report["records"]:
                for f in r["findings"]:
                    if f["severity"] == "info" and not a.verbose > 1:
                        continue
                    where = r["id"] + ("" if f["span_index"] is None else " span %d" % f["span_index"])
                    print("  %s: %s %s" % (where, f["code"], f["message_" + a.lang]))
    s = report["summary"]["by_severity"]
    if s["error"] or (a.strict and s["warning"]):
        return 1
    return 0


def cmd_convert(a):
    data = _read(a.input)
    text, ff, bom = decode(data)
    if text is None:
        print("input is not valid UTF-8", file=sys.stderr)
        return 2
    st = _settings(a)
    fmt = a.format if a.format != "auto" else detect_format(text)
    records = parse(text, fmt, st)
    to = a.to
    out = []
    from .checks import Ctx, check_record
    for rec in records:
        fs, _, _, _ = check_record(rec, bom)
        if any(f["code"] in ("E019", "E020") for f in fs):
            print("record %s cannot be converted: %s" % (rec.id, "; ".join(f["code"] for f in fs if f["code"] in ("E019", "E020"))), file=sys.stderr)
            return 2
        ctx = Ctx(rec, bom)
        toks = rec.tokens_cp if rec.tokens_cp is not None else rec.tokens
        if toks is None:
            from .tokenize import tokenize
            toks = tokenize(rec.text)
        elif rec.tokens_cp is None:
            toks = [(ctx.omap.to_cp(s, rec.offset_unit)[0], ctx.omap.to_cp(e, rec.offset_unit)[0]) for s, e in toks]
        if rec.from_tokens:
            spans = tags_to_offsets(toks, rec.tags, rec.scheme or "IOB2")
        else:
            spans = [(ctx.omap.to_cp(sp["start"], rec.offset_unit)[0], ctx.omap.to_cp(sp["end"], rec.offset_unit)[0], sp["label"]) for sp in rec.spans]
        if to == "spans":
            out.append({"id": rec.id, "text": rec.text, "offset_unit": "codepoint",
                        "spans": [{"start": s, "end": e, "label": lab, "text": rec.text[s:e]} for s, e, lab in spans]})
        else:
            from .convert import offsets_to_tags
            try:
                tags = offsets_to_tags(toks, spans, to)
            except ValueError as ex:
                print("record %s: %s (run check first)" % (rec.id, ex), file=sys.stderr)
                return 1
            out.append({"id": rec.id, "tokens": [rec.text[s:e] for s, e in toks], "tags": tags, "scheme": to})
    sys.stdout.write("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out))
    return 0


def cmd_codes(a):
    if a.json:
        sys.stdout.write(json.dumps(CODES, ensure_ascii=False, indent=1) + "\n")
        return 0
    for code, c in CODES.items():
        print("%s  %-7s  %s" % (code, c["severity"], c["title_" + a.lang]))
    return 0


def cmd_schema(a):
    with open(os.path.join(HERE, "data", "input.schema.json"), encoding="utf-8") as fh:
        sys.stdout.write(fh.read())
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="arabic-ner-validator",
                                 description="Check Arabic NER annotations for offset drift, normalisation shifts, clitic and grapheme boundaries, overlaps and BIO/BIOES/BILUO errors.")
    ap.add_argument("--version", action="version", version="arabic-ner-validator " + __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="validate a file and write reports")
    _common(p)
    p.add_argument("--json", help="write the JSON report to this file ('-' for standard output)")
    p.add_argument("--csv", help="write one CSV row per finding to this file")
    p.add_argument("--share", action="store_true", help="JSON report without any text: ids, codes, offsets and counts only")
    p.add_argument("--apply-suggestions", metavar="OUT", help="write a repaired copy to OUT (offsets only; labels and text unchanged)")
    p.add_argument("--min-confidence", choices=("high", "medium", "low"), default="medium",
                   help="lowest confidence of the suggestions that --apply-suggestions applies (default medium)")
    p.add_argument("--strict", action="store_true", help="exit with status 1 on warnings too")
    p.add_argument("--max-bytes", type=int, default=50 * 1024 * 1024)
    p.add_argument("--max-records", type=int, default=1_000_000)
    p.add_argument("--lang", choices=("en", "ar"), default="en", help="language of the summary")
    p.add_argument("-v", "--verbose", action="count", default=0, help="list findings (twice: with notes)")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("convert", help="convert spans to tags or tags to spans (well-formed input only)")
    _common(p)
    p.add_argument("--to", required=True, type=lambda v: "spans" if v.lower() == "spans" else _scheme(v),
                   help="spans, IOB2, BIOES or BILUO")
    p.set_defaults(func=cmd_convert)
    p = sub.add_parser("codes", help="list the finding codes")
    p.add_argument("--lang", choices=("en", "ar"), default="en")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_codes)
    p = sub.add_parser("schema", help="print the JSON Schema of the canonical input record")
    p.set_defaults(func=cmd_schema)
    a = ap.parse_args(argv)
    try:
        return a.func(a)
    except (OSError, ValueError) as ex:
        print("error: %s" % ex, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
