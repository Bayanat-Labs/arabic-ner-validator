"""Checks for one record: offsets, content at span edges, clitics, overlaps, tags, and the
diagnosis of drift (another unit or another reading of the text that makes the offsets fit).

Docs: docs/CHECKS.md. Every finding is a dict with code, kind, span_index, start, end and detail;
messages are added by the report.
"""
from __future__ import annotations

import re
import unicodedata

from . import chars as C
from .convert import check_tags, parse_tag, tags_to_entities
from .offsets import UNITS, OffsetMap, apply_policy, make_reading

SYMPTOMS = ("E002", "E004", "E007", "E008", "E012", "E016", "W101", "W102", "I204")
CONF_RANK = {"high": 3, "medium": 2, "low": 1}
EDIT_PRIORITY = ("E008", "E012", "E004", "W102", "W101", "E007")
EDIT_CONF = {"E008": "medium", "E012": "high", "E004": "medium", "W102": "medium", "W101": "high", "E007": "low"}
READ_ORDER = ("crlf_to_lf", "lf_to_crlf", "strip_bom", "add_bom", "NFC", "NFKC", "remove_tatweel", "remove_diacritics")
READ_CODE = {"crlf_to_lf": ("E013", "offsets_lf"), "lf_to_crlf": ("E013", "offsets_crlf"),
             "strip_bom": ("E018", "offsets_without_bom"), "add_bom": ("E018", "offsets_with_bom"),
             "NFC": ("E011", "offsets_on_normalized"), "NFKC": ("E011", "offsets_on_normalized"),
             "remove_tatweel": ("E011", "offsets_on_normalized"), "remove_diacritics": ("E011", "offsets_on_normalized")}
FORM_POLICIES = ("NFC", "NFKC", "remove_tatweel", "remove_diacritics")

_PROCLITIC = re.compile(r"^[وف]?[بكل]?$")
_ART1 = re.compile(r"^([وف]?[بك]?)ال$")
_ART2 = re.compile(r"^([وف]?ل)ل$")
_CL1 = re.compile(r"^([وف]?[بك]?)ال(.*)$")
_CL2 = re.compile(r"^([وف]?ل)ل(.*)$")


def F(code, kind=None, span=None, start=None, end=None, **detail):
    return {"code": code, "kind": kind, "span_index": span, "start": start, "end": end, "detail": detail}


def _edge_kind(start, end, suffix=""):
    if start and end:
        return "both" + suffix
    return ("start" if start else "end") + suffix


class Ctx:
    def __init__(self, rec, file_bom=False):
        self.rec = rec
        self.text = rec.text
        self.n = len(rec.text)
        self.unit = rec.offset_unit
        self.omap = OffsetMap(rec.text)
        self.word = [C.is_word(ch) for ch in rec.text]
        self.file_bom = file_bom
        self.policy = rec.clitic_policy or "unspecified"
        self._readings = {}
        self.tok = None
        if rec.tokens is not None:
            self.tok = (set(), set(), [])
        self.unit_errors = []

    def reading(self, name):
        if name not in self._readings:
            self._readings[name] = make_reading(self.text, name, self.file_bom)
        return self._readings[name]

    # ------------------------------------------------------------------ words and clitics
    def word_start(self, p):
        while p > 0 and self.word[p - 1]:
            p -= 1
        return p

    def word_end(self, p):
        while p < self.n and self.word[p]:
            p += 1
        return p

    def mid_word(self, p):
        return 0 < p < self.n and self.word[p - 1] and self.word[p]


def _letters(s, base=0):
    """[(char, position)] for the letters of s, skipping marks and tatweel."""
    return [(ch, base + i) for i, ch in enumerate(s) if C.is_letter(ch) and ch != C.TATWEEL]


_ART_SPLIT = re.compile(r"^([وف]?[بك]?)ا$")


def analyze_prefix(p, nxt=""):
    """('proclitic', None), ('article', offset_in_p), ('article_split', offset_in_p) or None for the
    in-word text p before a span; nxt is the text from the span start to the end of the word."""
    keep = [(ch, i) for i, ch in enumerate(p) if not C.is_mark(ch)]
    while keep and keep[-1][0] == C.TATWEEL:
        keep.pop()
    if not keep:
        return None
    base = "".join(ch for ch, _ in keep)
    if not all(C.is_arabic_letter(ch) for ch in base):
        return None
    if _PROCLITIC.match(base):
        return ("proclitic", None)
    m = _ART1.match(base) or _ART2.match(base)
    if m:
        return ("article", keep[len(m.group(1))][1])
    m = _ART_SPLIT.match(base)
    if m and nxt[:1] == "ل" and len(_letters(nxt)) >= 3:
        return ("article_split", keep[len(m.group(1))][1])
    return None


def _first_script(s):
    for ch in s:
        sc = C.script_of(ch)
        if sc:
            return sc
    return None


def _last_script(s):
    for ch in reversed(s):
        sc = C.script_of(ch)
        if sc:
            return sc
    return None


def start_cluster_exclude(ctx, s):
    """Under clitic_policy exclude: the position after a conjunction or preposition that the span
    includes at the start of its word, or None."""
    t = ctx.text
    we = ctx.word_end(s)
    w = t[s:we]
    lets = _letters(w, s)
    ar = []
    for ch, pos in lets:
        if C.is_arabic_letter(ch):
            ar.append((ch, pos))
        else:
            break
    base = "".join(ch for ch, _ in ar)
    rest_count = lambda k: len(lets) - k
    m = _CL1.match(base)
    if m and m.group(1) and rest_count(len(m.group(1)) + 2) >= 2:
        return lets[len(m.group(1))][1]
    m = _CL2.match(base)
    if m and rest_count(len(m.group(1)) + 1) >= 2:
        return lets[len(m.group(1))][1]
    if len(ar) < len(lets) and C.is_latin_letter(lets[len(ar)][0]) and base and _PROCLITIC.match(base):
        return lets[len(ar)][1]
    return None


def content(ctx, s, e, with_hints=False):
    """Symptom findings for the code point range [s, e) (0 <= s < e <= n). Each finding may carry
    private hints (keys starting with '_') used to build a repair."""
    t = ctx.text
    out = []
    if not any(C.is_alnum(ch) for ch in t[s:e]):
        return [F("E002", "no_content")]
    i = s
    lead_ctrl, lead_ws = [], False
    while i < e and (C.is_ws(t[i]) or C.is_control(t[i])):
        if C.is_control(t[i]):
            lead_ctrl.append(t[i])
        else:
            lead_ws = True
        i += 1
    j = e
    trail_ctrl, trail_ws = [], False
    while j > i and (C.is_ws(t[j - 1]) or C.is_control(t[j - 1])):
        if C.is_control(t[j - 1]):
            trail_ctrl.append(t[j - 1])
        else:
            trail_ws = True
        j -= 1
    if lead_ctrl or trail_ctrl:
        seen = []
        for ch in lead_ctrl + list(reversed(trail_ctrl)):
            if C.uplus(ch) not in seen:
                seen.append(C.uplus(ch))
        out.append(F("E012", _edge_kind(bool(lead_ctrl), bool(trail_ctrl)), char=", ".join(seen)))
    if lead_ws or trail_ws:
        out.append(F("W101", _edge_kind(lead_ws, trail_ws)))
    p_start = C.is_punct(t[i]) and t[i] not in C.PUNCT_EXEMPT
    last = t[j - 1]
    p_end = C.is_punct(last) and last not in C.PUNCT_EXEMPT and not (
        last == "." and j - 2 >= i and C.is_latin_letter(t[j - 2]))
    if p_start or p_end:
        seen = []
        if p_start:
            seen.append(C.uplus(t[i]))
        if p_end and C.uplus(last) not in seen:
            seen.append(C.uplus(last))
        out.append(F("W102", _edge_kind(p_start, p_end), char=", ".join(seen)))
    g_start = s not in ctx.omap.gb_set
    g_end = e not in ctx.omap.gb_set
    if g_start or g_end:
        out.append(F("E004", _edge_kind(g_start, g_end)))
    # ---- start edge: words, tokens and clitics
    w_start = w_end = False
    tok_start = tok_end = False
    mix_start = mix_end = False
    if not g_start and i == s:
        tok_cut = ctx.tok is not None and s not in ctx.tok[0]
        if tok_cut:
            tok_start = True
        elif ctx.mid_word(s):
            ws = ctx.word_start(s)
            we = ctx.word_end(s)
            kind = analyze_prefix(t[ws:s], t[s:we])
            if kind and kind[0] == "article_split" and ctx.policy in ("include", "exclude"):
                out.append(F("E008", "article_split", _start=ws if ctx.policy == "include" else ws + kind[1]))
            elif kind and kind[0] != "article_split" and len(_letters(t[s:we])) >= 2:
                if ctx.policy == "include":
                    out.append(F("E008", "clitic_excluded", _start=ws))
                elif ctx.policy == "exclude":
                    if kind[0] == "article":
                        out.append(F("E008", "article_excluded", _start=ws + kind[1]))
                else:
                    out.append(F("I204"))
            elif ctx.tok is None:
                a, b = _last_script(t[ws:s]), _first_script(t[s:we])
                if a and b and a != b:
                    mix_start = True
                else:
                    w_start = True
        elif ctx.policy == "exclude":
            q = start_cluster_exclude(ctx, s)
            if q is not None:
                out.append(F("E008", "clitic_included", _start=q))
    if not g_end and j == e:
        if ctx.tok is not None:
            if e not in ctx.tok[1]:
                tok_end = True
        elif ctx.mid_word(e):
            ws = ctx.word_start(e)
            we = ctx.word_end(e)
            a, b = _last_script(t[ws:e]), _first_script(t[e:we])
            if a and b and a != b:
                mix_end = True
            else:
                w_end = True
    if tok_start or tok_end:
        out.append(F("E007", _edge_kind(tok_start, tok_end, "_token")))
    elif w_start or w_end:
        out.append(F("E007", _edge_kind(w_start, w_end)))
    if mix_start or mix_end:
        out.append(F("E016", _edge_kind(mix_start, mix_end)))
    return out


def is_clean(ctx, s, e):
    return all(f["code"].startswith("I") for f in content(ctx, s, e))


def _to_cp(omap, value, unit):
    return omap.to_cp(value, unit)


def span_text_form(sl, st):
    for p in FORM_POLICIES:
        if apply_policy(sl, p) == apply_policy(st, p):
            return ("E011", p)
    if apply_policy(sl, "crlf_to_lf") == apply_policy(st, "crlf_to_lf"):
        return ("E013", "crlf_to_lf")
    return None


def _occurrences(hay, needle):
    out = []
    if not needle:
        return out
    i = hay.find(needle)
    while i >= 0:
        out.append(i)
        i = hay.find(needle, i + 1)
    return out


def diagnose(ctx, sp, sd, ed, declared, text_based, hard):
    """Other readings that make the span fit. Returns (status, findings, new_cp, confidence, reason)."""
    t = ctx.text
    succ = []  # (code, kind, detail_key, value, (s, e)) in priority order

    def try_unit(u):
        if u == ctx.unit:
            return
        if not text_based and u in ("utf8_byte", "grapheme") and not hard:
            return
        s2, err1 = ctx.omap.to_cp(sd, u)
        e2, err2 = ctx.omap.to_cp(ed, u)
        if err1 or err2 or s2 >= e2 or (s2, e2) == declared:
            return
        ok = (t[s2:e2] == sp["text"]) if text_based else is_clean(ctx, s2, e2)
        if ok:
            succ.append(("E014", None, "unit_found", u, (s2, e2)))

    for u in ("codepoint", "utf16", "utf8_byte"):
        try_unit(u)
    for name in READ_ORDER:
        r = ctx.reading(name)
        if r is None:
            continue
        sT, err1 = r.omap.to_cp(sd, ctx.unit)
        eT, err2 = r.omap.to_cp(ed, ctx.unit)
        if err1 or err2 or sT >= eT:
            continue
        s2, e2 = r.start_map[sT], r.end_map[eT]
        if s2 is None or e2 is None or s2 >= e2 or (s2, e2) == declared:
            continue
        if text_based:
            ok = r.text[sT:eT] == sp["text"] or t[s2:e2] == sp["text"]
        else:
            ok = is_clean(ctx, s2, e2)
        if ok:
            code, kind = READ_CODE[name]
            succ.append((code, kind, "policy", name, (s2, e2)))
    # grapheme counting last: CRLF, a letter with combining marks and alef + combining hamza are
    # single clusters, so this reading often coincides with a more specific one above
    try_unit("grapheme")
    if not succ and text_based:
        # the span text found somewhere else, as it is or after a reading
        for name in (None,) + FORM_POLICIES:
            if name is None:
                hits = [(p, p + len(sp["text"])) for p in _occurrences(t, sp["text"])]
            else:
                target = apply_policy(sp["text"], name)
                if target == sp["text"]:
                    continue
                r = ctx.reading(name)
                hits = []
                if r is None:
                    hits = [(p, p + len(target)) for p in _occurrences(t, target)]
                else:
                    for p in _occurrences(r.text, target):
                        a, b = r.start_map[p], r.end_map[p + len(target)]
                        if a is not None and b is not None and a < b:
                            hits.append((a, b))
            if not hits:
                continue
            if len(hits) > 1:
                return ("none", [], None, None, None)
            if name is None:
                return ("ok", [], hits[0], "low", "E003")
            return ("ok", [F("E011", "relocated", policy=name)], hits[0], "medium", "E011")
        return ("none", [], None, None, None)
    if not succ:
        return ("none", [], None, None, None)
    ranges = []
    for x in succ:
        if x[4] not in ranges:
            ranges.append(x[4])
    if len(ranges) == 1:
        code, kind, key, val, _ = succ[0]
        also = [x[3] for x in succ[1:]]
        if key == "unit_found":
            f = F(code, kind, unit_found=val, unit=ctx.unit, also_fits=also)
        else:
            f = F(code, kind, policy=val, also_fits=also)
        return ("ok", [f], ranges[0], "high" if text_based else "medium", code)
    findings = []
    by_code = {}
    for code, kind, key, val, rng in succ:
        by_code.setdefault(code, []).append(val)
    for code, vals in by_code.items():
        if code == "E014":
            findings.append(F(code, "ambiguous", unit_found=", ".join(vals), unit=ctx.unit))
        else:
            findings.append(F(code, "ambiguous", policy=", ".join(vals)))
    return ("ambiguous", findings, None, None, None)


def structural_repair(ctx, s, e, sym):
    """Edge-wise repair for symptom findings: (new_s, new_e, reason, reasons, confidence) or None."""
    t = ctx.text
    codes = {f["code"]: f for f in sym}
    if "E002" in codes:
        return None
    s2, e2 = s, e
    applied = []
    e004 = codes.get("E004")
    e008 = codes.get("E008")
    if e008 is not None:
        s2 = e008["detail"]["_start"]
        applied.append("E008")
    elif e004 is not None and e004["kind"] in ("start", "both"):
        cs, ce = ctx.omap.cluster_of(s)
        s2 = ce if (ce >= ctx.n or not ctx.word[ce]) else cs
        applied.append("E004")
    if e004 is not None and e004["kind"] in ("end", "both"):
        cs, ce = ctx.omap.cluster_of(e)
        e2 = ce
        applied.append("E004")

    def trim_code(ch):
        if C.is_control(ch):
            return "E012"
        if C.is_ws(ch):
            return "W101"
        return None

    while s2 < e2:
        ch = t[s2]
        c = trim_code(ch) or ("W102" if C.is_punct(ch) and ch not in C.PUNCT_EXEMPT else None)
        if c is None:
            break
        applied.append(c)
        s2 += 1
    while e2 > s2:
        ch = t[e2 - 1]
        c = trim_code(ch)
        if c is None and C.is_punct(ch) and ch not in C.PUNCT_EXEMPT and not (
                ch == "." and e2 - 2 >= s2 and C.is_latin_letter(t[e2 - 2])):
            c = "W102"
        if c is None:
            break
        applied.append(c)
        e2 -= 1
    if s2 >= e2:
        return None
    # word or token edges
    if ctx.tok is not None:
        starts, ends = ctx.tok[0], ctx.tok[1]
        if s2 not in starts:
            cands = [x for x in starts if x <= s2]
            if cands:
                s2 = max(cands)
                applied.append("E007")
        if e2 not in ends:
            cands = [x for x in ends if x >= e2]
            if cands:
                e2 = min(cands)
                applied.append("E007")
    else:
        if ctx.mid_word(s2):
            ws, we = ctx.word_start(s2), ctx.word_end(s2)
            kind = analyze_prefix(t[ws:s2], t[s2:we])
            mixed = (lambda a, b: a and b and a != b)(_last_script(t[ws:s2]), _first_script(t[s2:we]))
            acceptable = kind is not None and kind[0] != "article_split" and len(_letters(t[s2:we])) >= 2 and (
                ctx.policy == "unspecified" or (ctx.policy == "exclude" and kind[0] == "proclitic"))
            if not acceptable and not mixed:
                s2 = ws
                applied.append("E007")
        if ctx.mid_word(e2):
            ws, we = ctx.word_start(e2), ctx.word_end(e2)
            mixed = (lambda a, b: a and b and a != b)(_last_script(t[ws:e2]), _first_script(t[e2:we]))
            if not mixed:
                e2 = we
                applied.append("E007")
    if (s2, e2) == (s, e) or not applied:
        return None
    reasons = [c for c in EDIT_PRIORITY if c in applied]
    conf = min((EDIT_CONF[c] for c in reasons), key=lambda c: CONF_RANK[c])
    return (s2, e2, reasons[0], reasons, conf)


def check_record(rec, file_bom=False):
    """Findings and repair suggestions for one parsed record."""
    findings = []
    repairs = []
    conv = []
    if rec.problems:
        for path, problem in rec.problems:
            findings.append(F("E020", None, path=path, problem=problem))
    text = rec.text
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in text):
        findings.append(F("E020", None, path="text", problem="contains an unpaired surrogate"))
    if rec.offset_unit is None:
        hint = unit_hint(rec, file_bom, unit_free=True)
        findings.append(_public(F("E019", None, **hint)))
        return findings, repairs, conv, 0
    if any(f["code"] == "E020" for f in findings):
        return findings, repairs, conv, 0
    ctx = Ctx(rec, file_bom)
    if rec.tokens_cp is not None:
        ctx.tok = ({a for a, _ in rec.tokens_cp}, {b for _, b in rec.tokens_cp}, list(rec.tokens_cp))
    elif rec.tokens is not None:
        st, en, pairs = set(), set(), []
        for k, (a, b) in enumerate(rec.tokens):
            ca, e1 = ctx.omap.to_cp(a, ctx.unit)
            cb, e2 = ctx.omap.to_cp(b, ctx.unit)
            if e1 or e2 or ca > cb:
                findings.append(F("E020", None, path="tokens[%d]" % k, problem="offsets do not fit the text"))
                continue
            st.add(ca)
            en.add(cb)
            pairs.append((ca, cb))
        ctx.tok = (st, en, pairs)
    # ---------------------------------------------------------------- record-level notes
    if text.startswith(C.BOM):
        findings.append(F("E018", "text"))
    nd = rec.normalization_declared or "none"
    if nd in ("NFC", "NFKC", "NFD", "NFKD") and unicodedata.normalize(nd, text) != text:
        findings.append(F("E011", "declared_form", policy=nd))
    astral = sum(1 for ch in text if ord(ch) > 0xFFFF)
    if astral:
        findings.append(F("I201", None, n=astral))
    forms = [f for f in ("NFC", "NFKC") if len(unicodedata.normalize(f, text)) != len(text)]
    if forms:
        findings.append(F("I202", None, forms=" and ".join(forms)))
    # ---------------------------------------------------------------- tags
    if rec.tags is not None:
        scheme = rec.scheme
        if scheme is None:
            scheme = infer_scheme(rec.tags)
            findings.append(F("I205", None, scheme=scheme))
        for idx, kind, tag, prev in check_tags(rec.tags, scheme):
            findings.append(F("E009", kind, token=idx, tag=str(tag), prev=str(prev) if prev is not None else "", scheme=scheme))
        if rec.from_tokens:
            toks = rec.tokens
            for a, b, lab in tags_to_entities(rec.tags, scheme):
                rec.spans.append({"start": toks[a][0], "end": toks[b][1], "label": lab})
    # ---------------------------------------------------------------- spans
    ranges = {}
    span_ok = {}
    for i, sp in enumerate(rec.spans):
        fs, rep, cp = check_span(ctx, i, sp)
        findings += fs
        if rep is not None and not rec.from_tokens:
            repairs.append(rep)
        if cp is not None:
            ranges[i] = cp
            conv.append({"span_index": i, **ctx.omap.convert(*cp)})
    # ---------------------------------------------------------------- overlaps and nesting
    idx = sorted(ranges)
    for x in range(len(idx)):
        for y in range(x + 1, len(idx)):
            i, j = idx[x], idx[y]
            a, b = ranges[i], ranges[j]
            si, sj = rec.spans[i], rec.spans[j]
            if a == b:
                if si["label"] == sj["label"]:
                    findings.append(F("E005", "duplicate", j, sj["start"], sj["end"], other=i))
                elif rec.nested_policy != "allow":
                    findings.append(F("E006", "same_extent", j, sj["start"], sj["end"], other=i))
            elif a[0] < b[0] < a[1] < b[1] or b[0] < a[0] < b[1] < a[1]:
                findings.append(F("E005", "crossing", j, sj["start"], sj["end"], other=i))
            elif rec.nested_policy != "allow" and (a[0] <= b[0] and b[1] <= a[1] or b[0] <= a[0] and a[1] <= b[1]):
                inner, outer = (j, i) if (a[0] <= b[0] and b[1] <= a[1]) else (i, j)
                findings.append(F("E006", "nested", inner, rec.spans[inner]["start"], rec.spans[inner]["end"], other=outer))
    # ---------------------------------------------------------------- unit hint
    bad = [f for f in findings if f["code"] in ("E001", "E003", "E014", "E015")]
    if bad and not rec.from_tokens:
        hint = unit_hint(rec, file_bom, ctx)
        best = hint["_best"]
        if best and best != rec.offset_unit and hint["_counts"][best] > hint["_counts"].get(rec.offset_unit, 0):
            findings.append(F("I203", None, **hint))
    findings = [_public(f) for f in findings]
    valid = 0
    bad_spans = {f["span_index"] for f in findings if f["span_index"] is not None and f["code"][0] in "EW"}
    for i in range(len(rec.spans)):
        if i not in bad_spans:
            valid += 1
    return findings, repairs, conv, valid


def check_span(ctx, i, sp):
    """(findings, repair or None, cp range or None)."""
    out = []
    sd, ed = sp["start"], sp["end"]
    unit = ctx.unit
    if ctx.rec.label_set is not None and sp["label"] not in ctx.rec.label_set:
        out.append(F("E010", None, i, sd, ed, label=sp["label"]))
    s, serr = ctx.omap.to_cp(sd, unit)
    e, eerr = ctx.omap.to_cp(ed, unit)
    rng = (serr == "range", eerr == "range")
    mid = (serr == "mid", eerr == "mid")
    if any(rng):
        out.append(F("E001", _edge_kind(*rng), i, sd, ed, limit=ctx.omap.total(unit), unit=unit))
    if any(mid):
        out.append(F("E015", _edge_kind(*mid), i, sd, ed, unit=unit))
    if sd == ed:
        out.append(F("E002", "zero_length", i, sd, ed))
        return out, None, None
    if sd > ed:
        out.append(F("E002", "reversed", i, sd, ed))
        rep = None
        if not any(rng) and not any(mid):
            a, b = ctx.omap.to_cp(ed, unit)[0], ctx.omap.to_cp(sd, unit)[0]
            if any(C.is_alnum(ch) for ch in ctx.text[a:b]):
                rep = _rep(ctx, i, sp, (sd, ed), (ed, sd), "E002", ["E002"], "low")
        return out, rep, None
    text_given = "text" in sp
    if any(rng) or any(mid):
        st, fs, new, conf, reason = diagnose(ctx, sp, sd, ed, None, text_given, True)
        out += [_at(f, i, sd, ed) for f in fs]
        rep = _cp_rep(ctx, i, sp, (sd, ed), new, reason, [reason], conf) if st == "ok" else None
        return out, rep, None
    sl = ctx.text[s:e]
    sym = content(ctx, s, e)
    mismatch = text_given and sp["text"] != sl
    if mismatch:
        out.append(F("E003", None, i, sd, ed))
    status, dfs, new, conf, reason = ("none", [], None, None, None)
    if mismatch:
        form = span_text_form(sl, sp["text"])
        edge = None if form else edge_form(sl, sp["text"])
        if form:
            code, pol = form
            out.append(F(code, "span_text_form", i, sd, ed, policy=pol))
        elif edge is not None:
            out += [_at(f, i, sd, ed) for f in edge]
        else:
            status, dfs, new, conf, reason = diagnose(ctx, sp, sd, ed, (s, e), True, False)
    elif not text_given and any(f["code"][0] in "EW" for f in sym):
        status, dfs, new, conf, reason = diagnose(ctx, sp, sd, ed, (s, e), False, False)
    out += [_at(f, i, sd, ed) for f in dfs]
    if status == "ok" and reason != "E003":
        return out, _cp_rep(ctx, i, sp, (sd, ed), new, reason, [reason], conf), (s, e)
    out += [_at(_public(f), i, sd, ed) for f in sym]
    if status == "ambiguous":
        return out, None, (s, e)
    rep = None
    r = structural_repair(ctx, s, e, sym)
    if r is not None:
        rep = _cp_rep(ctx, i, sp, (sd, ed), (r[0], r[1]), r[2], r[3], r[4])
    elif status == "ok":
        rep = _cp_rep(ctx, i, sp, (sd, ed), new, reason, [reason], conf)
    return out, rep, (s, e)


def _edge_code(ch):
    if C.is_control(ch):
        return "E012"
    if C.is_ws(ch):
        return "W101"
    if C.is_punct(ch) and ch not in C.PUNCT_EXEMPT:
        return "W102"
    return None


def _trim_edges(s):
    a, b = 0, len(s)
    while a < b and _edge_code(s[a]):
        a += 1
    while b > a and _edge_code(s[b - 1]) and not (s[b - 1] == "." and b - 2 >= a and C.is_latin_letter(s[b - 2])):
        b -= 1
    return s[a:b], s[:a], s[b:]


def edge_form(sl, st):
    """Findings when the span text and the slice differ only by whitespace, controls or punctuation at
    the edges; the characters that only the span text carries are reported (the slice's own edges are
    reported by the content checks). None when they differ otherwise."""
    c1, _, _ = _trim_edges(sl)
    c2, lead, trail = _trim_edges(st)
    if not c1 or c1 != c2:
        return None
    out = []
    for code in ("E012", "W101", "W102"):
        chars = [ch for ch in lead + trail if _edge_code(ch) == code]
        if chars:
            seen = []
            for ch in chars:
                if C.uplus(ch) not in seen:
                    seen.append(C.uplus(ch))
            out.append(F(code, "span_text", char=", ".join(seen)))
    return out


def _public(f):
    f = dict(f)
    f["detail"] = {k: v for k, v in f["detail"].items() if not k.startswith("_")}
    return f


def _at(f, i, sd, ed):
    f = dict(f)
    f["span_index"], f["start"], f["end"] = i, sd, ed
    return f


def _rep(ctx, i, sp, old, new, reason, reasons, conf):
    return {"record_id": ctx.rec.id, "span_index": i, "label": sp["label"], "old": list(old), "new": list(new),
            "unit": ctx.unit, "reason_code": reason, "reason_codes": reasons, "confidence": conf}


def _cp_rep(ctx, i, sp, old, new_cp, reason, reasons, conf):
    if new_cp is None:
        return None
    a = ctx.omap.from_cp(new_cp[0], ctx.unit)
    b = ctx.omap.from_cp(new_cp[1], ctx.unit)
    if a is None or b is None:
        return None
    return _rep(ctx, i, sp, old, (a, b), reason, reasons, conf)


def infer_scheme(tags):
    pre = {t[0] for t in tags if isinstance(t, str) and parse_tag(t) and t != "O"}
    if pre & {"L", "U"}:
        return "BILUO"
    if pre & {"E", "S"}:
        return "BIOES"
    return "IOB2"


def unit_hint(rec, file_bom=False, ctx=None, unit_free=False):
    """How many spans fit under each unit (by span text when given, else by clean edges)."""
    if ctx is None:
        ctx = Ctx(rec, file_bom)
    counts = {}
    n = 0
    for sp in rec.spans:
        if sp["start"] >= sp["end"]:
            continue
        n += 1
        for u in UNITS:
            a, e1 = ctx.omap.to_cp(sp["start"], u)
            b, e2 = ctx.omap.to_cp(sp["end"], u)
            if e1 or e2 or a >= b:
                continue
            ok = ctx.text[a:b] == sp["text"] if "text" in sp else is_clean(ctx, a, b)
            if ok:
                counts[u] = counts.get(u, 0) + 1
    order = sorted((u for u in UNITS if counts.get(u)), key=lambda u: (-counts[u], UNITS.index(u)))
    if order:
        en = "Offsets fit " + "; ".join("%s for %d of %d spans" % (u, counts[u], n) for u in order) + "."
        ar = "تتطابق المواضع مع " + "؛ ".join("%s في %d من %d" % (u, counts[u], n) for u in order) + "."
    else:
        en = "No unit makes the offsets fit."
        ar = "لا توجد وحدة تجعل المواضع متطابقة."
    return {"hint": en, "hint_ar": ar, "counts": {u: counts.get(u, 0) for u in UNITS}, "spans": n,
            "_best": order[0] if order else None, "_counts": counts}
