"""Input adapters. Each turns a decoded file into canonical records.

Formats: canonical (this package's JSON Lines contract), doccano (JSONL with "label" lists or
"entities" objects), label_studio (JSON export: tasks with annotations or predictions), spacy
(JSONL: {"text", "entities"} or {"text", "spans", "tokens"} or ["text", {"entities": ...}]),
conll (one token per line, tag in the last column, blank line between sentences) and hf_tokens
(JSONL rows with "tokens" and "ner_tags").
"""
from __future__ import annotations

import json

from ..chars import is_ws
from ..contract import check_canonical, is_int
from ..convert import ALIASES

FORMATS = ("canonical", "doccano", "label_studio", "spacy", "conll", "hf_tokens")
SPAN_FORMATS = ("canonical", "doccano", "label_studio", "spacy")


class Record:
    __slots__ = ("id", "line", "text", "offset_unit", "normalization_declared", "scheme", "label_set",
                 "nested_policy", "clitic_policy", "spans", "tokens", "tags", "from_tokens", "problems",
                 "scheme_inferred", "source", "span_refs", "task_index", "tokens_cp")

    def __init__(self, rid, line):
        self.id = rid
        self.line = line
        self.text = ""
        self.offset_unit = None
        self.normalization_declared = "none"
        self.scheme = None
        self.label_set = None
        self.nested_policy = "forbid"
        self.clitic_policy = "unspecified"
        self.spans = []          # dicts: start, end, label, text (optional)
        self.tokens = None       # list of (start, end) in the declared unit
        self.tags = None
        self.from_tokens = False  # text and spans were built from tokens (CoNLL, HF rows)
        self.problems = []       # (path, problem) contract problems
        self.scheme_inferred = False
        self.source = None       # the parsed object, for --apply-suggestions
        self.span_refs = []      # where each span lives in source, for --apply-suggestions
        self.task_index = None   # Label Studio: index of the task in the export
        self.tokens_cp = None    # tokens given as strings, aligned on the text (code points)


def _scheme(value):
    if value is None:
        return None
    v = ALIASES.get(value, value)
    return v


def _lines(text):
    """(line_number, line) for each line, without the line break."""
    out = []
    for i, ln in enumerate(text.split("\n"), 1):
        if ln.endswith("\r"):
            ln = ln[:-1]
        out.append((i, ln))
    return out


def _json_lines(text):
    """(line_number, value or None, error or None) for each non-blank line."""
    out = []
    for i, ln in _lines(text):
        if not ln.strip(" \t"):
            continue
        try:
            out.append((i, json.loads(ln), None))
        except ValueError:
            out.append((i, None, "is not valid JSON"))
    return out


def _rid(obj, line):
    if isinstance(obj, dict) and "id" in obj and (isinstance(obj["id"], str) or is_int(obj["id"])):
        v = obj["id"]
        return v if isinstance(v, str) else str(int(v))
    return "L%d" % line


def detect_format(text):
    s = text.lstrip("﻿ \t\r\n")
    if not s:
        return "canonical"
    if s[0] not in "[{":
        return "conll"
    if s[0] == "[":
        try:
            v = json.loads(s)
        except ValueError:
            v = None
        if isinstance(v, list) and v and isinstance(v[0], dict):
            if "data" in v[0] or "annotations" in v[0] or "predictions" in v[0]:
                return "label_studio"
            return "canonical"
        return "spacy"
    first = None
    for _, obj, err in _json_lines(text):
        first = obj
        break
    if isinstance(first, dict):
        if "data" in first and ("annotations" in first or "predictions" in first):
            return "label_studio"
        if "tokens" in first and "ner_tags" in first:
            return "hf_tokens"
        if "offset_unit" in first:
            return "canonical"
        ents = first.get("entities")
        if "label" in first or (isinstance(ents, list) and ents and isinstance(ents[0], dict) and "start_offset" in ents[0]):
            return "doccano"
        return "spacy"
    if isinstance(first, list):
        return "spacy"
    return "canonical"


def _bad(rec, path, problem):
    rec.problems.append((path, problem))


def _span_list_offsets(rec, items, path):
    """[[start, end, label], ...] as used by doccano 'label' and spaCy 'entities'."""
    if not isinstance(items, list):
        _bad(rec, path, "must be an array")
        return
    for k, it in enumerate(items):
        p = "%s[%d]" % (path, k)
        if not (isinstance(it, list) and len(it) >= 3):
            _bad(rec, p, "must be [start, end, label]")
            continue
        s, e, lab = it[0], it[1], it[2]
        if not is_int(s) or not is_int(e):
            _bad(rec, p, "start and end must be integers")
            continue
        if not isinstance(lab, str) or not lab:
            _bad(rec, p, "label must be a non-empty string")
            continue
        rec.spans.append({"start": int(s), "end": int(e), "label": lab})
        rec.span_refs.append((path, k, "list"))


def align_tokens(rec, text, toks):
    """Code point offsets of token strings that occur in the text in order, separated by whitespace."""
    out = []
    pos = 0
    for k, t in enumerate(toks):
        i = text.find(t, pos) if t else -1
        if i < 0 or any(not is_ws(ch) for ch in text[pos:i]):
            _bad(rec, "tokens[%d]" % k, "is not the next token of the text")
            return None
        out.append((i, i + len(t)))
        pos = i + len(t)
    return out


def parse_canonical(text, settings):
    recs = []
    s = text.lstrip(" \t\r\n")
    items = []
    if s.startswith("["):
        try:
            arr = json.loads(s)
        except ValueError:
            arr = None
        if isinstance(arr, list):
            items = [(None, k + 1, v, None) for k, v in enumerate(arr)]
        else:
            items = [(1, None, None, "is not valid JSON")]
    else:
        items = [(ln, None, v, err) for ln, v, err in _json_lines(text)]
    for line, idx, obj, err in items:
        if line is not None:
            rid = _rid(obj, line)
        else:
            rid = _rid(obj, 0) if isinstance(obj, dict) and (isinstance(obj.get("id"), str) or is_int(obj.get("id"))) else "#%d" % idx
        rec = Record(rid, line)
        rec.source = obj
        if err:
            _bad(rec, "$", err)
            recs.append(rec)
            continue
        for path, problem in check_canonical(obj, settings):
            _bad(rec, path, problem)
        if isinstance(obj, dict):
            if isinstance(obj.get("text"), str):
                rec.text = obj["text"]
            ou = obj.get("offset_unit")
            rec.offset_unit = ou if isinstance(ou, str) else None
            for k in ("normalization_declared", "nested_policy", "clitic_policy"):
                if isinstance(obj.get(k), str):
                    setattr(rec, k, obj[k])
            if isinstance(obj.get("scheme"), str):
                rec.scheme = obj["scheme"]
            if isinstance(obj.get("label_set"), list):
                rec.label_set = [x for x in obj["label_set"] if isinstance(x, str)]
            if isinstance(obj.get("spans"), list):
                for k, sp in enumerate(obj["spans"]):
                    if isinstance(sp, dict) and is_int(sp.get("start")) and is_int(sp.get("end")) and isinstance(sp.get("label"), str):
                        d = {"start": int(sp["start"]), "end": int(sp["end"]), "label": sp["label"]}
                        if isinstance(sp.get("text"), str):
                            d["text"] = sp["text"]
                        rec.spans.append(d)
                        rec.span_refs.append(("spans", k, "dict"))
            if isinstance(obj.get("tokens"), list):
                toks = obj["tokens"]
                if toks and all(isinstance(t, str) for t in toks):
                    rec.tokens_cp = align_tokens(rec, rec.text, toks)
                    rec.tokens = []
                else:
                    rec.tokens = [(int(t["start"]), int(t["end"])) for t in toks
                                  if isinstance(t, dict) and is_int(t.get("start")) and is_int(t.get("end"))]
            if isinstance(obj.get("tags"), list):
                rec.tags = [t for t in obj["tags"] if isinstance(t, str)]
        _fill(rec, settings, own=obj if isinstance(obj, dict) else {})
        recs.append(rec)
    return recs


def _fill(rec, settings, own):
    """Settings apply where the record itself does not declare a value."""
    if not own.get("offset_unit") and rec.offset_unit is None:
        rec.offset_unit = settings.get("offset_unit")
    for k, default in (("normalization_declared", "none"), ("nested_policy", "forbid"), ("clitic_policy", "unspecified")):
        if k not in own and settings.get(k) is not None:
            setattr(rec, k, settings[k])
    if "scheme" not in own and settings.get("scheme") is not None:
        rec.scheme = settings["scheme"]
    if "label_set" not in own and settings.get("label_set") is not None:
        rec.label_set = list(settings["label_set"])


def parse_doccano(text, settings):
    recs = []
    for line, obj, err in _json_lines(text):
        rec = Record(_rid(obj, line), line)
        rec.source = obj
        if err:
            _bad(rec, "$", err)
        elif not isinstance(obj, dict):
            _bad(rec, "$", "must be an object")
        else:
            if not isinstance(obj.get("text"), str):
                _bad(rec, "text", "is required and must be a string")
            else:
                rec.text = obj["text"]
            if "label" in obj:
                _span_list_offsets(rec, obj["label"], "label")
            if "entities" in obj:
                ents = obj["entities"]
                if not isinstance(ents, list):
                    _bad(rec, "entities", "must be an array")
                else:
                    for k, it in enumerate(ents):
                        p = "entities[%d]" % k
                        if not isinstance(it, dict) or not is_int(it.get("start_offset")) or not is_int(it.get("end_offset")):
                            _bad(rec, p, "must have integer start_offset and end_offset")
                            continue
                        if not isinstance(it.get("label"), str) or not it["label"]:
                            _bad(rec, p, "label must be a non-empty string")
                            continue
                        rec.spans.append({"start": int(it["start_offset"]), "end": int(it["end_offset"]), "label": it["label"]})
                        rec.span_refs.append(("entities", k, "doccano"))
        _fill(rec, settings, {})
        recs.append(rec)
    return recs


def parse_label_studio(text, settings):
    recs = []
    try:
        data = json.loads(text)
    except ValueError:
        rec = Record("#1", 1)
        _bad(rec, "$", "is not valid JSON")
        return [rec]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        rec = Record("#1", 1)
        _bad(rec, "$", "must be an array of tasks")
        return [rec]
    for ti, task in enumerate(data, 1):
        if not isinstance(task, dict):
            rec = Record("#%d" % ti, None)
            _bad(rec, "[%d]" % (ti - 1), "task must be an object")
            recs.append(rec)
            continue
        tid = task.get("id")
        tid = (tid if isinstance(tid, str) else str(int(tid))) if (isinstance(tid, str) or is_int(tid)) else "#%d" % ti
        d = task.get("data")
        ttext = None
        if isinstance(d, dict):
            if isinstance(d.get("text"), str):
                ttext = d["text"]
            else:
                for v in d.values():
                    if isinstance(v, str):
                        ttext = v
                        break
        groups = []
        for key, mark in (("annotations", ""), ("predictions", "p")):
            arr = task.get(key)
            if isinstance(arr, list):
                for k, ann in enumerate(arr, 1):
                    aid = ann.get("id") if isinstance(ann, dict) else None
                    aid = (aid if isinstance(aid, str) else str(int(aid))) if (isinstance(aid, str) or is_int(aid)) else str(k)
                    groups.append(("%s:%s%s" % (tid, mark, aid), key, k - 1, ann))
        if not groups:
            groups = [(tid, None, None, None)]
        for rid, key, k, ann in groups:
            rec = Record(rid, None)
            rec.source = task
            rec.task_index = ti - 1
            if ttext is None:
                _bad(rec, "data.text", "is required and must be a string")
            else:
                rec.text = ttext
            if ann is not None:
                res = ann.get("result") if isinstance(ann, dict) else None
                if not isinstance(res, list):
                    _bad(rec, "%s[%d].result" % (key, k), "must be an array")
                else:
                    for ri, r in enumerate(res):
                        if not isinstance(r, dict):
                            continue
                        v = r.get("value")
                        if not isinstance(v, dict) or "start" not in v or "end" not in v:
                            continue
                        labels = None
                        for lk in ("labels", "hypertextlabels"):
                            if isinstance(v.get(lk), list):
                                labels = v[lk]
                        p = "%s[%d].result[%d].value" % (key, k, ri)
                        if not is_int(v.get("start")) or not is_int(v.get("end")):
                            _bad(rec, p, "start and end must be integers")
                            continue
                        if not labels or not all(isinstance(x, str) and x for x in labels):
                            _bad(rec, p, "labels must be a non-empty array of strings")
                            continue
                        for lab in labels:
                            sp = {"start": int(v["start"]), "end": int(v["end"]), "label": lab}
                            if isinstance(v.get("text"), str):
                                sp["text"] = v["text"]
                            rec.spans.append(sp)
                            rec.span_refs.append((key, (k, ri), "ls"))
            _fill(rec, settings, {})
            recs.append(rec)
    return recs


def parse_spacy(text, settings):
    recs = []
    for line, obj, err in _json_lines(text):
        rec = Record(_rid(obj, line), line)
        rec.source = obj
        if err:
            _bad(rec, "$", err)
        elif isinstance(obj, list):
            if len(obj) >= 2 and isinstance(obj[0], str) and isinstance(obj[1], dict):
                rec.text = obj[0]
                _span_list_offsets(rec, obj[1].get("entities", []), "[1].entities")
            else:
                _bad(rec, "$", "must be [text, {\"entities\": [...]}]")
        elif isinstance(obj, dict):
            if not isinstance(obj.get("text"), str):
                _bad(rec, "text", "is required and must be a string")
            else:
                rec.text = obj["text"]
            if "entities" in obj:
                _span_list_offsets(rec, obj["entities"], "entities")
            if "spans" in obj:
                sps = obj["spans"]
                if not isinstance(sps, list):
                    _bad(rec, "spans", "must be an array")
                else:
                    for k, it in enumerate(sps):
                        p = "spans[%d]" % k
                        if not isinstance(it, dict) or not is_int(it.get("start")) or not is_int(it.get("end")):
                            _bad(rec, p, "must have integer start and end")
                            continue
                        if not isinstance(it.get("label"), str) or not it["label"]:
                            _bad(rec, p, "label must be a non-empty string")
                            continue
                        sp = {"start": int(it["start"]), "end": int(it["end"]), "label": it["label"]}
                        if isinstance(it.get("text"), str):
                            sp["text"] = it["text"]
                        rec.spans.append(sp)
                        rec.span_refs.append(("spans", k, "dict"))
            if isinstance(obj.get("tokens"), list):
                toks = []
                for k, t in enumerate(obj["tokens"]):
                    if isinstance(t, dict) and is_int(t.get("start")) and is_int(t.get("end")):
                        toks.append((int(t["start"]), int(t["end"])))
                    else:
                        _bad(rec, "tokens[%d]" % k, "must have integer start and end")
                rec.tokens = toks
        else:
            _bad(rec, "$", "must be an object or a list")
        _fill(rec, settings, {})
        recs.append(rec)
    return recs


def _from_tokens(rec, tokens, tags):
    pos = 0
    toks = []
    parts = []
    for t in tokens:
        toks.append((pos, pos + len(t)))
        parts.append(t)
        pos += len(t) + 1
    rec.text = " ".join(parts)
    rec.tokens = toks
    rec.tags = list(tags)
    rec.from_tokens = True
    rec.offset_unit = "codepoint"


def parse_conll(text, settings):
    recs = []
    sent = []
    start_line = None
    n = 0

    def flush():
        nonlocal sent, start_line, n
        if sent:
            n += 1
            rec = Record("S%d" % n, start_line)
            bad = [(ln, k) for k, (ln, cols) in enumerate(sent) if len(cols) < 2]
            for ln, k in bad:
                _bad(rec, "line %d" % ln, "needs a token and a tag")
            toks = [cols[0] for _, cols in sent]
            tags = [cols[-1] if len(cols) >= 2 else "O" for _, cols in sent]
            _from_tokens(rec, toks, tags)
            _fill(rec, settings, {})
            rec.offset_unit = "codepoint"
            recs.append(rec)
        sent = []
        start_line = None

    for ln, line in _lines(text):
        if not line.strip(" \t"):
            flush()
            continue
        cols = [c for c in line.replace("\t", " ").split(" ") if c != ""]
        if cols and cols[0] == "-DOCSTART-":
            flush()
            continue
        if start_line is None:
            start_line = ln
        sent.append((ln, cols))
    flush()
    return recs


def parse_hf_tokens(text, settings):
    recs = []
    names = settings.get("tag_names")
    for line, obj, err in _json_lines(text):
        rec = Record(_rid(obj, line), line)
        rec.source = obj
        if err:
            _bad(rec, "$", err)
        elif not isinstance(obj, dict) or not isinstance(obj.get("tokens"), list) or not isinstance(obj.get("ner_tags"), list):
            _bad(rec, "$", "must have arrays tokens and ner_tags")
        else:
            toks, tags = obj["tokens"], obj["ner_tags"]
            ok = True
            if len(toks) != len(tags):
                _bad(rec, "ner_tags", "must have as many items as tokens")
                ok = False
            if not all(isinstance(t, str) for t in toks):
                _bad(rec, "tokens", "must be strings")
                ok = False
            out = []
            for k, t in enumerate(tags):
                if isinstance(t, str):
                    out.append(t)
                elif is_int(t):
                    if not names:
                        _bad(rec, "ner_tags[%d]" % k, "is an integer but no tag_names were given")
                        ok = False
                        out.append("O")
                    elif not 0 <= int(t) < len(names):
                        _bad(rec, "ner_tags[%d]" % k, "is outside tag_names")
                        ok = False
                        out.append("O")
                    else:
                        out.append(names[int(t)])
                else:
                    _bad(rec, "ner_tags[%d]" % k, "must be a string or an integer")
                    ok = False
                    out.append("O")
            if ok:
                _from_tokens(rec, toks, out)
        _fill(rec, settings, {})
        rec.offset_unit = "codepoint"
        recs.append(rec)
    return recs


PARSERS = {"canonical": parse_canonical, "doccano": parse_doccano, "label_studio": parse_label_studio,
           "spacy": parse_spacy, "conll": parse_conll, "hf_tokens": parse_hf_tokens}


def parse(text, fmt, settings):
    if fmt not in PARSERS:
        raise ValueError("unknown format: %s" % fmt)
    recs = PARSERS[fmt](text, settings)
    for r in recs:
        if r.scheme is not None:
            r.scheme = _scheme(r.scheme)
    return recs
