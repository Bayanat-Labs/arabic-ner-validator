"""The canonical input contract, checked without a JSON Schema library.

schema/input.schema.json states the same rules as JSON Schema draft 2020-12; the tests check that
both reject the same examples. A missing offset_unit is reported as E019, every other breach as E020.
"""
from __future__ import annotations

import re

UNITS = ("utf8_byte", "codepoint", "utf16", "grapheme")
SCHEMES = ("IO", "IOB1", "IOB2", "IOE1", "IOE2", "BIOES", "BILUO")
KEYS = ("id", "text", "offset_unit", "normalization_declared", "scheme", "label_set", "nested_policy",
        "clitic_policy", "spans", "tokens", "tags")
NORM_RX = re.compile(r"^(none|NFC|NFKC|NFD|NFKD|policy:[A-Za-z0-9._-]+)$")


def is_int(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, float) and v == v and v not in (float("inf"), float("-inf")) and v.is_integer()


def check_canonical(obj, settings=None):
    """List of (path, problem). offset_unit may come from settings (a command-line declaration)."""
    out = []
    if not isinstance(obj, dict):
        return [("$", "must be an object")]
    for k in obj:
        if k not in KEYS:
            out.append((k, "is not an allowed property"))
    if "id" in obj and not (isinstance(obj["id"], str) or is_int(obj["id"])):
        out.append(("id", "must be a string or an integer"))
    if "text" not in obj:
        out.append(("text", "is required"))
    elif not isinstance(obj["text"], str):
        out.append(("text", "must be a string"))
    if "offset_unit" in obj and obj["offset_unit"] not in UNITS:
        out.append(("offset_unit", "must be one of utf8_byte, codepoint, utf16, grapheme"))
    if "normalization_declared" in obj and not (isinstance(obj["normalization_declared"], str) and NORM_RX.match(obj["normalization_declared"])):
        out.append(("normalization_declared", "must be none, NFC, NFKC, NFD, NFKD or policy:<id>"))
    if "scheme" in obj and obj["scheme"] not in SCHEMES:
        out.append(("scheme", "must be one of IO, IOB1, IOB2, IOE1, IOE2, BIOES, BILUO"))
    if "label_set" in obj:
        ls = obj["label_set"]
        if not isinstance(ls, list) or not all(isinstance(x, str) and x for x in ls):
            out.append(("label_set", "must be an array of non-empty strings"))
        elif len(set(ls)) != len(ls):
            out.append(("label_set", "must not repeat a label"))
    if "nested_policy" in obj and obj["nested_policy"] not in ("forbid", "allow"):
        out.append(("nested_policy", "must be forbid or allow"))
    if "clitic_policy" in obj and obj["clitic_policy"] not in ("include", "exclude", "unspecified"):
        out.append(("clitic_policy", "must be include, exclude or unspecified"))
    if "spans" not in obj:
        out.append(("spans", "is required"))
    elif not isinstance(obj["spans"], list):
        out.append(("spans", "must be an array"))
    else:
        for i, sp in enumerate(obj["spans"]):
            p = "spans[%d]" % i
            if not isinstance(sp, dict):
                out.append((p, "must be an object"))
                continue
            for k in sp:
                if k not in ("start", "end", "label", "text"):
                    out.append((p + "." + k, "is not an allowed property"))
            for k in ("start", "end"):
                if k not in sp:
                    out.append((p + "." + k, "is required"))
                elif not is_int(sp[k]):
                    out.append((p + "." + k, "must be an integer"))
            if "label" not in sp:
                out.append((p + ".label", "is required"))
            elif not isinstance(sp["label"], str) or not sp["label"]:
                out.append((p + ".label", "must be a non-empty string"))
            if "text" in sp and not isinstance(sp["text"], str):
                out.append((p + ".text", "must be a string"))
    if "tokens" in obj:
        toks = obj["tokens"]
        if not isinstance(toks, list):
            out.append(("tokens", "must be an array"))
        else:
            for i, t in enumerate(toks):
                p = "tokens[%d]" % i
                if isinstance(t, str):
                    continue
                if not isinstance(t, dict):
                    out.append((p, "must be a string or an object"))
                    continue
                for k in t:
                    if k not in ("start", "end", "text"):
                        out.append((p + "." + k, "is not an allowed property"))
                for k in ("start", "end"):
                    if k not in t:
                        out.append((p + "." + k, "is required"))
                    elif not is_int(t[k]):
                        out.append((p + "." + k, "must be an integer"))
                if "text" in t and not isinstance(t["text"], str):
                    out.append((p + ".text", "must be a string"))
    if "tags" in obj:
        tags = obj["tags"]
        if not isinstance(tags, list) or not all(isinstance(x, str) for x in tags):
            out.append(("tags", "must be an array of strings"))
        if "tokens" not in obj:
            out.append(("tags", "needs tokens"))
        elif isinstance(tags, list) and isinstance(obj.get("tokens"), list) and len(tags) != len(obj["tokens"]):
            out.append(("tags", "must have as many items as tokens"))
    return out
