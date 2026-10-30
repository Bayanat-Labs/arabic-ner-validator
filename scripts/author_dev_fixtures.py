#!/usr/bin/env python3
"""Write the 100 dev fixtures (fixtures/dev/fixtures.jsonl) and their SHA-256 manifest.

Every sentence is original and written for this set. Names are places, organisations, public or
historical figures, or invented. Offsets are computed here with plain string operations (code
point index, UTF-16 and UTF-8 lengths, regex grapheme clusters); the expected error codes and the
expected suggestions are stated by hand for each fixture from the check definitions in
docs/CHECKS.md. This script does not import the validator.

  python scripts/author_dev_fixtures.py            # writes fixtures/dev/fixtures.jsonl
"""
import hashlib
import json
import os
import unicodedata

import regex

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "fixtures", "dev", "fixtures.jsonl")

EMOJI = "\U0001F600"
EARTH = "\U0001F30D"
RLM, LRM, ALM = "‏", "‎", "؜"
ZWNJ, ZWSP = "‌", "​"
BOM = "﻿"
HAMZA_ABOVE = "ٔ"
LAM_ALEF = "ﻻ"
ALLAH = "ﷲ"
TATWEEL = "ـ"

CATEGORIES = {
    "a": "Astral character (emoji) before the span: UTF-16 vs code point offsets",
    "b": "UTF-8 byte offsets",
    "c": "NFC composition drift",
    "d": "NFKC ligature expansion",
    "e": "Span edge between a letter and its haraka or shadda",
    "f": "Tatweel removed after annotation",
    "g": "Bidi or zero-width control at a span edge",
    "h": "Clitic boundary under the include or exclude policy",
    "i": "Span edge inside a word or token",
    "j": "Overlapping spans",
    "k": "Nested spans under the forbid or allow policy",
    "l": "Empty, zero-length or reversed span",
    "m": "Invalid tag or tag transition",
    "n": "CRLF vs LF line-break shift",
    "o": "UTF-8 byte order mark",
    "p": "Span text differs from text[start:end]",
    "q": "Arabic punctuation at a span edge",
    "r": "Latin-script entity inside right-to-left text",
    "v": "Valid records that must produce no error or warning",
}


# ----------------------------------------------------------------------------- string helpers
def find(text, sub, nth=1):
    """Code point (start, end) of the nth occurrence of sub."""
    i = -1
    for _ in range(nth):
        i = text.index(sub, i + 1)
    return i, i + len(sub)


def u16(text, cp):
    return len(text[:cp].encode("utf-16-le")) // 2


def u8(text, cp):
    return len(text[:cp].encode("utf-8"))


def gr(text, cp):
    clusters = regex.findall(r"\X", text[:cp])
    assert "".join(clusters) == text[:cp]
    # cp must sit on a cluster boundary of the whole text
    pos, idx = 0, 0
    for c in regex.findall(r"\X", text):
        if pos == cp:
            return idx
        pos += len(c)
        idx += 1
    assert pos == cp, "not on a grapheme boundary"
    return idx


def conv(text, se, unit):
    s, e = se
    f = {"codepoint": lambda t, x: x, "utf16": u16, "utf8_byte": u8, "grapheme": gr}[unit]
    return [f(text, s), f(text, e)]


def jl(records):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def canon(rid, text, unit, spans, **opts):
    rec = {"id": rid, "text": text, "offset_unit": unit}
    rec.update(opts)
    rec["spans"] = spans
    return rec


def sp(start, end, label, text=None):
    d = {"start": start, "end": end, "label": label}
    if text is not None:
        d["text"] = text
    return d


def sug(rid, idx, old, new, code, conf):
    return {"record_id": rid, "span_index": idx, "old": list(old), "new": list(new), "reason_code": code,
            "confidence": conf}


def ls_task(tid, text, regions, ann_id=1):
    res = []
    for k, (s, e, lab, t) in enumerate(regions, 1):
        v = {"start": s, "end": e, "labels": [lab]}
        if t is not None:
            v["text"] = t
        res.append({"id": f"reg{k}", "from_name": "label", "to_name": "text", "type": "labels", "value": v})
    return {"id": tid, "data": {"text": text}, "annotations": [{"id": ann_id, "result": res}]}


def conll(sentences):
    out = []
    for sent in sentences:
        for tok, tag in sent:
            out.append(f"{tok}\t{tag}\n")
        out.append("\n")
    return "".join(out)


FIX = []


def add(cat, n, valid, fmt, payload, codes, suggestions=None, options=None, desc="", template=None):
    fid = f"dev-{cat}-{n:02d}"
    FIX.append({
        "fixture_id": fid,
        "split": "dev",
        "category": cat,
        "category_name": CATEGORIES[cat],
        "valid": valid,
        "format": fmt,
        "options": options or {},
        "input_payload": payload,
        "expected_error_codes": sorted(set(codes)),
        "expected_suggested_export": suggestions if suggestions else None,
        "template_id": template or f"dev-t-{cat}{n:02d}",
        "description": desc,
        "author": "Bayanat Labs",
        "reviewed_by": None,
        "synthetic": True,
        "license": "CC-BY-4.0",
    })
    assert valid == (not codes), fid


# ============================================================================= (a) astral before span
t = "وصلت الرسالة " + EMOJI + " من مدينة الرياض صباح اليوم"
s, e = find(t, "الرياض")
off = conv(t, (s, e), "utf16")
assert off == [s + 1, e + 1] and t[off[0]:off[1]] != "الرياض"
add("a", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(*off, "LOC", "الرياض")])]),
    ["E003", "E014"], [sug("r1", 0, off, (s, e), "E014", "high")],
    desc="Offsets counted in UTF-16 code units (the emoji counts 2) but declared as code points; the span text confirms the UTF-16 reading.")

t = EMOJI + " افتتحت مكتبة الإسكندرية قاعة جديدة"
s, e = find(t, "مكتبة الإسكندرية")
add("a", 2, False, "canonical", jl([canon("r1", t, "utf16", [sp(s, e, "ORG", "مكتبة الإسكندرية")])]),
    ["E003", "E014"], [sug("r1", 0, (s, e), conv(t, (s, e), "utf16"), "E014", "high")],
    desc="Offsets counted in code points but declared as UTF-16; the emoji at the start shifts the UTF-16 reading by one.")

t = "شاركت فرق من الدوحة " + EMOJI + EMOJI + " ومن المنامة في المسابقة"
s1, e1 = find(t, "الدوحة")
s2, e2 = find(t, "المنامة")
o2 = conv(t, (s2, e2), "utf16")
assert o2 == [s2 + 2, e2 + 2]
add("a", 3, False, "doccano", jl([{"id": 301, "text": t, "label": [[s1, e1, "LOC"], [o2[0], o2[1], "LOC"]]}]),
    ["E014"], [sug("301", 1, o2, (s2, e2), "E014", "medium")], options={"offset_unit": "codepoint"},
    desc="doccano export without span text: the second span lies after two emoji and only fits word boundaries when read as UTF-16.")

t = "مرحبًا من " + EMOJI + "الدمام"
s, e = find(t, "الدمام")
assert u16(t, s) == s + 1
add("a", 4, False, "canonical", jl([canon("r1", t, "utf16", [sp(s, e, "LOC", "الدمام")])]),
    ["E014", "E015"], [sug("r1", 0, (s, e), conv(t, (s, e), "utf16"), "E014", "high")],
    desc="Declared UTF-16; the start offset lands between the two surrogates of the emoji glued to the entity. Read as code points the span fits.")

t = "قال الفريق " + EMOJI + " إن معرض الكتاب يقام في الشارقة"
s, e = find(t, "الشارقة")
o = conv(t, (s, e), "utf16")
add("a", 5, True, "label_studio", json.dumps([ls_task(5, t, [(o[0], o[1], "LOC", "الشارقة")])], ensure_ascii=False),
    [], options={"offset_unit": "utf16"},
    desc="Label Studio task with an emoji before the entity and correct UTF-16 offsets.")

def mid8(text, off):
    bb = text.encode("utf-8")
    return 0 < off < len(bb) and (bb[off] & 0xC0) == 0x80


# ============================================================================= (b) UTF-8 bytes
t = "عقد المؤتمر السنوي في مدينة جدة"
s, e = find(t, "جدة")
o = conv(t, (s, e), "utf8_byte")
assert o[0] > len(t)
add("b", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(*o, "LOC", "جدة")])]),
    ["E001", "E014"], [sug("r1", 0, o, (s, e), "E014", "high")],
    desc="UTF-8 byte offsets declared as code points: Arabic letters take two bytes, so the offsets run past the end of the text.")

t = "تقع جامعة القاهرة في الجيزة"
s, e = find(t, "جامعة القاهرة")
assert not mid8(t, s) and not mid8(t, e)
add("b", 2, False, "canonical", jl([canon("r1", t, "utf8_byte", [sp(s, e, "ORG", "جامعة القاهرة")])]),
    ["E003", "E014"], [sug("r1", 0, (s, e), conv(t, (s, e), "utf8_byte"), "E014", "high")],
    desc="Code point offsets declared as UTF-8 bytes; both offsets fall on byte boundaries but select the wrong text.")

t = "سافر وفد بغداد إلى فاس"
s1, e1 = find(t, "بغداد")
s2, e2 = find(t, "فاس")
assert (mid8(t, s1) or mid8(t, e1)) and (mid8(t, s2) or mid8(t, e2))
add("b", 3, False, "doccano",
    jl([{"id": 303, "text": t, "entities": [{"id": 1, "label": "LOC", "start_offset": s1, "end_offset": e1},
                                            {"id": 2, "label": "LOC", "start_offset": s2, "end_offset": e2}]}]),
    ["E014", "E015"],
    [sug("303", 0, (s1, e1), conv(t, (s1, e1), "utf8_byte"), "E014", "medium"),
     sug("303", 1, (s2, e2), conv(t, (s2, e2), "utf8_byte"), "E014", "medium")],
    options={"offset_unit": "utf8_byte"},
    desc="doccano entities with code point offsets declared as UTF-8 bytes; offsets land inside two-byte Arabic letters.")

t = "تستضيف مسقط معرضًا للمخطوطات العربية"
s, e = find(t, "مسقط")
o = conv(t, (s, e), "utf8_byte")
add("b", 4, True, "canonical", jl([canon("r1", t, "utf8_byte", [sp(*o, "LOC", "مسقط")])]), [],
    desc="Correct UTF-8 byte offsets, declared as such.")

t = "استضافت الرباط ملتقى الشباب العربي"
s, e = find(t, "الرباط")
o = conv(t, (s, e), "utf8_byte")
assert o[1] <= len(t)
add("b", 5, False, "label_studio", json.dumps([ls_task(9, t, [(o[0], o[1], "LOC", "الرباط")])], ensure_ascii=False),
    ["E003", "E014"], [sug("9:1", 0, o, (s, e), "E014", "high")], options={"offset_unit": "utf16"},
    desc="Label Studio task whose offsets are UTF-8 bytes while the declared unit is UTF-16.")

# ============================================================================= (c) NFC drift
sa_l = "س" + "ا" + HAMZA_ABOVE + "ل"          # decomposed form of سأل
t = sa_l + " الباحث عن تاريخ القاهرة"
s, e = find(t, "القاهرة")
nt = unicodedata.normalize("NFC", t)
ns, ne = find(nt, "القاهرة")
assert (ns, ne) == (s - 1, e - 1)
add("c", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(ns, ne, "LOC", "القاهرة")])]),
    ["E003", "E011"], [sug("r1", 0, (ns, ne), (s, e), "E011", "high")],
    desc="The text keeps alef + combining hamza (U+0627 U+0654); the offsets were taken from the NFC form, where the pair is one letter.")

aswan_d = "ا" + HAMZA_ABOVE + "سوان"
t = "زرنا مدينة " + aswan_d + " في الشتاء"
s, e = find(t, aswan_d)
add("c", 2, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", "أسوان")])]),
    ["E003", "E011"], None,
    desc="Offsets are right for the decomposed text, but the span text is the NFC form (أسوان); the two differ only by normalisation.")

qara = "قر" + "ا" + HAMZA_ABOVE
t = qara + " الطالب ثم " + sa_l + " عن مدينة الأقصر"
s, e = find(t, "الأقصر")
nt = unicodedata.normalize("NFC", t)
ns, ne = find(nt, "الأقصر")
assert (ns, ne) == (s - 2, e - 2)
add("c", 3, False, "doccano", jl([{"id": 503, "text": t, "label": [[ns, ne, "LOC"]]}]),
    ["E011"], [sug("503", 0, (ns, ne), (s, e), "E011", "medium")], options={"offset_unit": "codepoint"},
    desc="doccano export without span text; two decomposed hamzas before the entity, offsets taken from the NFC form.")

abha_d = "ا" + HAMZA_ABOVE + "بها"
t = "تقع مدينة " + abha_d + " في جنوب المملكة"
k, ke = find(t, abha_d)
add("c", 4, False, "canonical", jl([canon("r1", t, "codepoint", [sp(k + 1, ke, "LOC", t[k + 1:ke])])]),
    ["E004"], [sug("r1", 0, (k + 1, ke), (k, ke), "E004", "medium")],
    desc="The span starts between the alef and its combining hamza, inside one grapheme cluster.")

t = "تقع مدينة " + abha_d + " في جنوب المملكة"
s, e = find(t, abha_d)
add("c", 5, True, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", abha_d)])]), [],
    desc="Decomposed text with offsets and span text that match it exactly.")

# ============================================================================= (d) NFKC ligatures
t = LAM_ALEF + " يزال المتحف الوطني في الشارقة مفتوحًا"
s, e = find(t, "الشارقة")
nk = unicodedata.normalize("NFKC", t)
ks, ke = find(nk, "الشارقة")
assert (ks, ke) == (s + 1, e + 1)
add("d", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(ks, ke, "LOC", "الشارقة")])]),
    ["E003", "E011"], [sug("r1", 0, (ks, ke), (s, e), "E011", "high")],
    desc="The text starts with the lam-alef ligature U+FEFB; the offsets were taken from the NFKC form, where it is two letters.")

t = "كتب الخطاط اسم " + ALLAH + " بخط الثلث على لوحة عرضت في الدوحة العام الماضي"
s, e = find(t, "الدوحة")
nk = unicodedata.normalize("NFKC", t)
ks, ke = find(nk, "الدوحة")
assert (ks, ke) == (s + 3, e + 3)
add("d", 2, False, "canonical", jl([canon("r1", t, "codepoint", [sp(ks, ke, "LOC", "الدوحة")])]),
    ["E003", "E011"], [sug("r1", 0, (ks, ke), (s, e), "E011", "high")],
    desc="U+FDF2 (one code point) expands to four letters under NFKC; offsets from the NFKC form are three too far.")

hague = LAM_ALEF + "هاي"
t = "عقدت محكمة العدل الدولية جلستها في " + hague
s, e = find(t, hague)
add("d", 3, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", "لاهاي")])]),
    ["E003", "E011"], None,
    desc="The text writes the place name with the ligature U+FEFB; the span text spells it with two letters. Offsets are right.")

t = "قال الدليل إن " + LAM_ALEF + " شيء يضاهي أسواق مراكش القديمة"
s, e = find(t, "مراكش")
add("d", 4, False, "doccano", jl([{"id": 704, "text": t, "label": [[s + 1, e + 1, "LOC"]]}]),
    ["E011"], [sug("704", 0, (s + 1, e + 1), (s, e), "E011", "medium")], options={"offset_unit": "codepoint"},
    desc="doccano export without span text; offsets taken from the NFKC form of a text with one lam-alef ligature.")

t = "رفع الزوار لافتة " + LAM_ALEF + " للحرب أمام مبنى الأمم المتحدة"
s, e = find(t, "الأمم المتحدة")
add("d", 5, True, "label_studio", json.dumps([ls_task(12, t, [(s, e, "ORG", "الأمم المتحدة")])], ensure_ascii=False),
    [], options={"offset_unit": "codepoint"},
    desc="A ligature before the entity and offsets counted on the text as it is.")

# ============================================================================= (e) letter / haraka edge
t = "سافرَ الوفدُ إلى دِمَشْقَ أمسِ"
s, e = find(t, "دِمَشْقَ")
add("e", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e - 1, "LOC", t[s:e - 1])])]),
    ["E004"], [sug("r1", 0, (s, e - 1), (s, e), "E004", "medium")],
    desc="The span ends between the last letter and its fatha.")

t = "كتبَ ابنُ بطوطةَ عن رحلته"
s, e = find(t, "ابنُ بطوطةَ")
fs = t.index("َ")  # fatha of the first word
assert t[fs - 1] == "ب"
add("e", 2, False, "canonical", jl([canon("r1", t, "codepoint", [sp(fs, e, "PER", t[fs:e])])]),
    ["E004"], [sug("r1", 0, (fs, e), (s, e), "E004", "medium")],
    desc="The span starts at the fatha of the previous word, inside that word's last grapheme cluster.")

t = "زار الشاعرُ بيروتَ في الربيع"
s, e = find(t, "بيروتَ")
add("e", 3, False, "label_studio", json.dumps([ls_task(14, t, [(s, e - 1, "LOC", "بيروت")])], ensure_ascii=False),
    ["E004"], [sug("14:1", 0, (s, e - 1), (s, e), "E004", "medium")], options={"offset_unit": "codepoint"},
    desc="Label Studio region that leaves out the final fatha of the place name.")

t = "وُلِدَ ابنُ سينا في بُخارى"
s1, e1 = find(t, "ابنُ سينا")
s2, e2 = find(t, "بُخارى")
add("e", 4, True, "canonical", jl([canon("r1", t, "codepoint", [sp(s1, e1, "PER", "ابنُ سينا"), sp(s2, e2, "LOC", "بُخارى")])]),
    [], desc="Vocalised text with span edges on grapheme boundaries.")

t = "وصلنا إلى جدّة ظهرًا"
s, e = find(t, "جدّة")
assert t[s + 2] == "ّ"
add("e", 5, False, "spacy", jl([{"text": t, "entities": [[s, s + 2, "LOC"]]}]),
    ["E004"], [sug("L1", 0, (s, s + 2), (s, e), "E004", "low")], options={"offset_unit": "codepoint"},
    desc="spaCy-style entity that ends between a letter and its shadda; the grapheme repair still leaves the word cut, so the suggestion also extends to the word end.")

# ============================================================================= (f) tatweel
t = "رحلة من جـــدة إلى مكة المكرمة"
st = t.replace(TATWEEL, "")
a1 = find(st, "جدة")
a2 = find(st, "مكة المكرمة")
o1 = find(t, "جـــدة")
o2 = find(t, "مكة المكرمة")
add("f", 1, False, "canonical",
    jl([canon("r1", t, "codepoint", [sp(*a1, "LOC", "جدة"), sp(*a2, "LOC", "مكة المكرمة")])]),
    ["E003", "E011"], [sug("r1", 0, a1, o1, "E011", "high"), sug("r1", 1, a2, o2, "E011", "high")],
    desc="The text keeps tatweel; the offsets and span texts come from a copy with tatweel removed.")

t = "تقع مدينة الريـــاض في وسط المملكة وتبعد عن الدمام مسافة طويلة"
st = t.replace(TATWEEL, "")
a1 = find(st, "الرياض")
a2 = find(st, "الدمام")
o1 = find(t, "الريـــاض")
o2 = find(t, "الدمام")
add("f", 2, False, "doccano", jl([{"id": 902, "text": t, "label": [[a1[0], a1[1], "LOC"], [a2[0], a2[1], "LOC"]]}]),
    ["E011"], [sug("902", 0, a1, o1, "E011", "medium"), sug("902", 1, a2, o2, "E011", "medium")],
    options={"offset_unit": "codepoint"},
    desc="doccano export without span text; offsets counted on the text after tatweel removal.")

src = "افتتح المعرض في الريـــاض بحضور الزوار"
t = src.replace(TATWEEL, "")
so = find(src, "الريـــاض")
s, e = find(t, "الرياض")
add("f", 3, False, "canonical", jl([canon("r1", t, "codepoint", [sp(*so, "LOC", "الريـــاض")])]),
    ["E003", "E011"], [sug("r1", 0, so, (s, e), "E011", "medium")],
    desc="Tatweel was removed from the text after annotation; the span text and offsets still come from the version with tatweel.")

t = "تشتهر مدينة الطائـــف بالورد"
s, e = find(t, "الطائـــف")
add("f", 4, True, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", "الطائـــف")])]), [],
    desc="Tatweel kept in the text and counted in the offsets.")

t = "زار الوفد مدينة صـــلالة ثم مسقط"
st = t.replace(TATWEEL, "")
a1 = find(st, "صلالة")
a2 = find(st, "مسقط")
o1 = find(t, "صـــلالة")
o2 = find(t, "مسقط")
add("f", 5, False, "label_studio",
    json.dumps([ls_task(18, t, [(a1[0], a1[1], "LOC", "صلالة"), (a2[0], a2[1], "LOC", "مسقط")])], ensure_ascii=False),
    ["E003", "E011"], [sug("18:1", 0, a1, o1, "E011", "high"), sug("18:1", 1, a2, o2, "E011", "high")],
    options={"offset_unit": "codepoint"},
    desc="Label Studio regions computed on a tatweel-free copy of a text that keeps tatweel.")

# ============================================================================= (g) bidi and zero-width controls
t = "انتقل المقر إلى " + RLM + "الرياض في العام الماضي"
s, e = find(t, RLM + "الرياض")
add("g", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", t[s:e])])]),
    ["E012"], [sug("r1", 0, (s, e), (s + 1, e), "E012", "high")],
    desc="A right-to-left mark (U+200F) is the first character of the span.")

t = "وصلت البعثة إلى بيروت" + ZWNJ + " صباحًا"
s, e = find(t, "بيروت" + ZWNJ)
add("g", 2, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", t[s:e])])]),
    ["E012"], [sug("r1", 0, (s, e), (s, e - 1), "E012", "high")],
    desc="A zero-width non-joiner (U+200C) is the last character of the span.")

t = "سافر الفريق إلى " + ALM + "تونس للمشاركة"
s, e = find(t, ALM + "تونس")
add("g", 3, False, "doccano", jl([{"id": 1103, "text": t, "label": [[s, e, "LOC"]]}]),
    ["E012"], [sug("1103", 0, (s, e), (s + 1, e), "E012", "high")], options={"offset_unit": "codepoint"},
    desc="An Arabic letter mark (U+061C) opens the span.")

t = "يقع مقر " + RLM + "جامعة الدول العربية" + RLM + " في القاهرة"
s1, e1 = find(t, "جامعة الدول العربية")
s2, e2 = find(t, "القاهرة")
add("g", 4, True, "canonical", jl([canon("r1", t, "codepoint", [sp(s1, e1, "ORG", "جامعة الدول العربية"), sp(s2, e2, "LOC", "القاهرة")])]),
    [], desc="Right-to-left marks right outside the span, not inside it.")

t = "أعلنت مكتبة الإسكندرية" + ZWSP + " عن معرض جديد"
s, e = find(t, "مكتبة الإسكندرية" + ZWSP)
add("g", 5, False, "label_studio", json.dumps([ls_task(22, t, [(s, e, "ORG", t[s:e])])], ensure_ascii=False),
    ["E012"], [sug("22:1", 0, (s, e), (s, e - 1), "E012", "high")], options={"offset_unit": "codepoint"},
    desc="A zero-width space (U+200B) at the end of a Label Studio region.")

# ============================================================================= (h) clitics
t = "سافر الوفد إلى جدة والرياض"
s, e = find(t, "الرياض")
add("h", 1, False, "canonical",
    jl([canon("r1", t, "codepoint", [sp(*find(t, "جدة"), "LOC", "جدة"), sp(s, e, "LOC", "الرياض")], clitic_policy="include")]),
    ["E008"], [sug("r1", 1, (s, e), (s - 1, e), "E008", "medium")],
    desc="clitic_policy include: the span leaves out the conjunction و attached to the place name.")

t = "زرنا جدة والرياض"
s, e = find(t, "والرياض")
add("h", 2, False, "canonical",
    jl([canon("r1", t, "codepoint", [sp(*find(t, "جدة"), "LOC", "جدة"), sp(s, e, "LOC", "والرياض")], clitic_policy="exclude")]),
    ["E008"], [sug("r1", 1, (s, e), (s + 1, e), "E008", "medium")],
    desc="clitic_policy exclude: the span includes the conjunction و.")

t = "أقمنا أسبوعًا بمكة ثم سافرنا"
s, e = find(t, "مكة")
add("h", 3, True, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", "مكة")], clitic_policy="exclude")]), [],
    desc="clitic_policy exclude: the preposition ب stays outside the span.")

t = "أقمنا أسبوعًا بمكة ثم سافرنا"
s, e = find(t, "بمكة")
add("h", 4, True, "doccano", jl([{"id": 1304, "text": t, "label": [[s, e, "LOC"]]}]), [],
    options={"offset_unit": "codepoint", "clitic_policy": "include"},
    desc="clitic_policy include: the preposition ب is inside the span.")

t = "قدّمت المنظمة تقريرها للأمم المتحدة"
s, e = find(t, "للأمم المتحدة")
add("h", 5, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "ORG", "للأمم المتحدة")], clitic_policy="exclude")]),
    ["E008"], [sug("r1", 0, (s, e), (s + 1, e), "E008", "medium")],
    desc="clitic_policy exclude: the span starts with the preposition ل fused with the article (لل).")

t = "زرنا جدة والرياض"
s, e = find(t, "رياض")
add("h", 6, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", "رياض")], clitic_policy="exclude")]),
    ["E008"], [sug("r1", 0, (s, e), (s - 2, e), "E008", "medium")],
    desc="clitic_policy exclude keeps the definite article with the name; this span also drops the article.")

# ============================================================================= (i) word or token edge
t = "صدر تقرير عن الأمم المتحدة أمس"
s, e = find(t, "الأمم المتحدة")
add("i", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e - 2, "ORG", t[s:e - 2])])]),
    ["E007"], [sug("r1", 0, (s, e - 2), (s, e), "E007", "low")],
    desc="The span ends two letters before the end of the word.")

t = "تعمل منظمة الصحة العالمية في جنيف"
toks, pos = [], 0
for w in t.split(" "):
    toks.append({"text": w, "start": pos, "end": pos + len(w), "id": len(toks)})
    pos += len(w) + 1
s, e = find(t, "منظمة الصحة العالمية")
add("i", 2, False, "spacy", jl([{"text": t, "tokens": toks, "spans": [{"start": s, "end": e - 3, "label": "ORG"}]}]),
    ["E007"], [sug("L1", 0, (s, e - 3), (s, e), "E007", "low")], options={"offset_unit": "codepoint"},
    desc="Prodigy-style record with tokens; the span ends inside the token العالمية.")

t = "انعقدت قمة جامعة الدول العربية في الجزائر"
s, e = find(t, "جامعة الدول العربية")
add("i", 3, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s + 2, e, "ORG", t[s + 2:e])])]),
    ["E007"], [sug("r1", 0, (s + 2, e), (s, e), "E007", "low")],
    desc="The span starts inside the word جامعة (not after a clitic).")

t = "انعقدت قمة جامعة الدول العربية في الجزائر"
toks, pos = [], 0
for w in t.split(" "):
    toks.append({"start": pos, "end": pos + len(w)})
    pos += len(w) + 1
add("i", 4, True, "canonical",
    jl([canon("r1", t, "codepoint", [sp(*find(t, "جامعة الدول العربية"), "ORG"), sp(*find(t, "الجزائر"), "LOC")], tokens=toks)]),
    [], desc="Multi-word entity whose edges match token edges.")

t = "يقع متحف اللوفر أبوظبي على جزيرة السعديات"
s, e = find(t, "اللوفر أبوظبي")
add("i", 5, False, "doccano", jl([{"id": 1505, "text": t, "label": [[s, e - 2, "ORG"]]}]),
    ["E007"], [sug("1505", 0, (s, e - 2), (s, e), "E007", "low")], options={"offset_unit": "codepoint"},
    desc="doccano span that cuts the last word of the entity.")

# ============================================================================= (j) overlaps
t = "تأسست جامعة الدول العربية في القاهرة"
a = find(t, "جامعة الدول العربية")
b_ = find(t, "الدول العربية في")
add("j", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(*a, "ORG"), sp(*b_, "LOC")])]),
    ["E005"], desc="Two spans cross: the second starts inside the first and ends after it.")

t = "عقد الاجتماع في القاهرة"
a = find(t, "القاهرة")
add("j", 2, False, "canonical", jl([canon("r1", t, "codepoint", [sp(*a, "LOC"), sp(*a, "LOC")])]),
    ["E005"], desc="The same span with the same label appears twice.")

t = "زار الوفد الرياض ثم جدة"
add("j", 3, True, "canonical",
    jl([canon("r1", t, "codepoint", [sp(*find(t, "الرياض"), "LOC"), sp(*find(t, "جدة"), "LOC")], nested_policy="allow")]),
    [], desc="Two separate spans; no overlap.")

t = "ألقى الكاتب نجيب محفوظ محاضرة في جامعة القاهرة"
a = find(t, "نجيب محفوظ")
b_ = find(t, "محفوظ محاضرة")
add("j", 4, False, "doccano", jl([{"id": 1604, "text": t, "label": [[a[0], a[1], "PER"], [b_[0], b_[1], "ORG"]]}]),
    ["E005"], options={"offset_unit": "codepoint", "nested_policy": "allow"},
    desc="Crossing spans are an error even when nesting is allowed.")

t = "تحدث المتنبي عن حلب وأهلها"
a = find(t, "المتنبي عن")
b_ = find(t, "عن حلب")
add("j", 5, False, "label_studio", json.dumps([ls_task(25, t, [(a[0], a[1], "PER", t[a[0]:a[1]]), (b_[0], b_[1], "LOC", t[b_[0]:b_[1]])])], ensure_ascii=False),
    ["E005"], options={"offset_unit": "codepoint"}, desc="Two Label Studio regions share the word عن.")

# ============================================================================= (k) nesting
t = "تخرجت ليلى النجار في جامعة الملك سعود عام ٢٠١٠"
outer = find(t, "جامعة الملك سعود")
inner = find(t, "الملك سعود")
add("k", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(*outer, "ORG"), sp(*inner, "PER")], nested_policy="forbid")]),
    ["E006"], desc="A person name nested inside an organisation name under nested_policy forbid.")
add("k", 2, True, "canonical", jl([canon("r1", t, "codepoint", [sp(*outer, "ORG"), sp(*inner, "PER")], nested_policy="allow")]),
    [], desc="The same nesting under nested_policy allow.", template="dev-t-k01")

t = "تقع الكويت على الخليج العربي"
a = find(t, "الكويت")
add("k", 3, False, "canonical", jl([canon("r1", t, "codepoint", [sp(*a, "LOC"), sp(*a, "ORG")], nested_policy="forbid")]),
    ["E006"], desc="Two labels on the same extent under nested_policy forbid.")
add("k", 4, True, "doccano", jl([{"id": 1704, "text": t, "label": [[a[0], a[1], "LOC"], [a[0], a[1], "ORG"]]}]),
    [], options={"offset_unit": "codepoint", "nested_policy": "allow"},
    desc="Two labels on the same extent under nested_policy allow.", template="dev-t-k03")

t = "زرت مكتبة الملك فهد الوطنية"
add("k", 5, False, "canonical", jl([canon("r1", t, "codepoint", [sp(*find(t, "مكتبة الملك فهد الوطنية"), "ORG"), sp(*find(t, "الملك فهد"), "PER")])]),
    ["E006"], desc="nested_policy not given: the default is forbid.")

# ============================================================================= (l) empty, zero-length, reversed
t = "يقيم المهرجان في مدينة العلا"
s, e = find(t, "العلا")
add("l", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, s, "LOC")])]), ["E002"],
    desc="Zero-length span.")
add("l", 2, False, "canonical", jl([canon("r1", t, "codepoint", [sp(e, s, "LOC")])]), ["E002"],
    [sug("r1", 0, (e, s), (s, e), "E002", "low")], desc="Reversed span (start after end).", template="dev-t-l01")
w = t.index(" ", s - 2)
add("l", 3, False, "canonical", jl([canon("r1", t, "codepoint", [sp(w, w + 1, "LOC")])]), ["E002"],
    desc="A span that covers a single space.", template="dev-t-l01")
t = "ولد الخوارزمي في خوارزم"
s, e = find(t, "الخوارزمي")
add("l", 4, False, "doccano", jl([{"id": 1804, "text": t, "label": [[e, s, "PER"]]}]), ["E002"],
    [sug("1804", 0, (e, s), (s, e), "E002", "low")], options={"offset_unit": "codepoint"},
    desc="doccano span with start and end swapped.")
add("l", 5, False, "canonical", jl([canon("r1", t, "codepoint", [sp(len(t), len(t), "LOC")])]), ["E002"],
    desc="Zero-length span at the end of the text.", template="dev-t-l04")

# ============================================================================= (m) tags
add("m", 1, False, "conll", conll([[("عاد", "O"), ("ابن", "O"), ("بطوطة", "I-PER"), ("إلى", "O"), ("طنجة", "B-LOC")]]),
    ["E009"], options={"scheme": "IOB2"}, desc="IOB2: I-PER after O.")
add("m", 2, False, "conll", conll([[("زار", "O"), ("نجيب", "B-PER"), ("محفوظ", "I-LOC"), ("الإسكندرية", "B-LOC")]]),
    ["E009"], options={"scheme": "IOB2"}, desc="IOB2: I-LOC after B-PER.")
add("m", 3, False, "conll", conll([[("تعمل", "O"), ("اليونسكو", "L-ORG"), ("في", "O"), ("باريس", "U-LOC")]]),
    ["E009"], options={"scheme": "BILUO"}, desc="BILUO: L-ORG without a B- tag.")
add("m", 4, False, "conll", conll([[("سافر", "O"), ("إلى", "O"), ("الدار", "B-LOC"), ("صباحًا", "O")]]),
    ["E009"], options={"scheme": "BIOES"}, desc="BIOES: an entity that starts with B- and is never closed.")
add("m", 5, True, "conll", conll([[("زارت", "O"), ("أم", "B-PER"), ("كلثوم", "E-PER"), ("دمشق", "S-LOC"), ("عام", "O"), ("١٩٥٥", "S-DATE")]]),
    [], options={"scheme": "BIOES"}, desc="BIOES: well-formed tags.")
add("m", 6, False, "hf_tokens", jl([{"id": "h6", "tokens": ["يقع", "مقر", "البنك", "الدولي", "في", "واشنطن"], "ner_tags": [0, 0, 4, 4, 0, 5]}]),
    ["E009"], options={"scheme": "IOB2", "tag_names": ["O", "B-PER", "I-PER", "B-ORG", "I-ORG", "B-LOC", "I-LOC"]},
    desc="Hugging Face token rows with integer tags: I-ORG after O.")
t = "ألّف طه حسين كتاب الأيام"
add("m", 7, False, "canonical", jl([canon("r1", t, "codepoint", [sp(*find(t, "طه حسين"), "PERSON")], label_set=["PER", "LOC", "ORG"])]),
    ["E010"], desc="A span label that is not in label_set.")

# ============================================================================= (n) CRLF vs LF
t = "السطر الأول عن المؤتمر\r\nانعقد المؤتمر في الدوحة أمس"
s, e = find(t, "الدوحة")
add("n", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s - 1, e - 1, "LOC", "الدوحة")])]),
    ["E003", "E013"], [sug("r1", 0, (s - 1, e - 1), (s, e), "E013", "high")],
    desc="The text has CRLF line breaks; the offsets count each line break as one character.")
t = "السطر الأول عن المؤتمر\nانعقد المؤتمر في الدوحة أمس"
s, e = find(t, "الدوحة")
add("n", 2, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s + 1, e + 1, "LOC", "الدوحة")])]),
    ["E003", "E013"], [sug("r1", 0, (s + 1, e + 1), (s, e), "E013", "high")],
    desc="The text has LF line breaks; the offsets were counted on a CRLF copy.")
t = "افتتاح الملتقى\r\nفي مدينة المنامة\r\nبمشاركة جامعة البحرين"
s1, e1 = find(t, "المنامة")
s2, e2 = find(t, "جامعة البحرين")
add("n", 3, False, "doccano", jl([{"id": 2003, "text": t, "label": [[s1 - 1, e1 - 1, "LOC"], [s2 - 2, e2 - 2, "ORG"]]}]),
    ["E013"], [sug("2003", 0, (s1 - 1, e1 - 1), (s1, e1), "E013", "medium"), sug("2003", 1, (s2 - 2, e2 - 2), (s2, e2), "E013", "medium")],
    options={"offset_unit": "codepoint"},
    desc="doccano export of a CRLF text whose offsets count each line break once; the shift grows by one per line.")
t = "عنوان\r\nزار الوفد عمّان"
s, e = find(t, "عمّان")
add("n", 4, True, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", "عمّان")])]), [],
    desc="CRLF text with offsets that count CRLF as two characters.")
t = "مقدمة\r\nزار الوفد مدينة صنعاء"
s, e = find(t, "صنعاء")
add("n", 5, False, "label_studio", json.dumps([ls_task(30, t, [(s - 1, e - 1, "LOC", "صنعاء")])], ensure_ascii=False),
    ["E003", "E013"], [sug("30:1", 0, (s - 1, e - 1), (s, e), "E013", "high")], options={"offset_unit": "codepoint"},
    desc="Label Studio region on a CRLF text, offsets counted with LF.")

# ============================================================================= (o) BOM
t = "تقع مدينة تبوك في شمال المملكة"
s, e = find(t, "تبوك")
FILE_BOM = {"record_id": None, "span_index": None, "old": None, "new": None, "reason_code": "E018",
            "confidence": "high", "action": "remove_bom"}
add("o", 1, False, "canonical", BOM + jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", "تبوك")])]),
    ["E018"], [FILE_BOM], desc="A JSON Lines file that starts with a UTF-8 byte order mark.")
t = BOM + "افتتحت جامعة الملك عبدالعزيز فرعًا جديدًا"
s, e = find(t, "جامعة الملك عبدالعزيز")
add("o", 2, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s - 1, e - 1, "ORG", "جامعة الملك عبدالعزيز")])]),
    ["E003", "E018"], [sug("r1", 0, (s - 1, e - 1), (s, e), "E018", "high")],
    desc="The text field starts with U+FEFF and the offsets were counted without it.")
add("o", 3, False, "conll", BOM + conll([[("تقع", "O"), ("الأحساء", "B-LOC"), ("شرق", "O"), ("المملكة", "O")]]),
    ["E018"], [FILE_BOM], options={"scheme": "IOB2"}, desc="A CoNLL file that starts with a byte order mark.")
t = BOM + "يزور السياح مدينة الأقصر كل شتاء"
s, e = find(t, "الأقصر")
add("o", 4, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", "الأقصر")])]), ["E018"],
    desc="The text starts with U+FEFF; the offsets count it, but the character itself should not be in the text.")
t = "يقام المعرض في مدينة نزوى"
s, e = find(t, "نزوى")
add("o", 5, False, "doccano", BOM + jl([{"id": 2105, "text": t, "label": [[s, e, "LOC"]]}]), ["E018"], [FILE_BOM],
    options={"offset_unit": "codepoint"}, desc="A doccano JSONL export that starts with a byte order mark.")

# ============================================================================= (p) span text mismatch
t = "عقدت الندوة في الرياض"
s, e = find(t, "الرياض")
add("p", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", "الدمام")])]), ["E003"],
    desc="The span text names a different place than the text at the offsets.")
t = "انطلقت الحافلة من مكة إلى جدة"
s, e = find(t, "مكة")
js, je = find(t, "جدة")
add("p", 2, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", "جدة")])]), ["E003"],
    [sug("r1", 0, (s, e), (js, je), "E003", "low")],
    desc="The span text occurs once elsewhere in the text; the suggestion moves the offsets there.")
t = "شاركت جامعة القاهرة في الملتقى"
s, e = find(t, "القاهرة")
add("p", 3, False, "label_studio", json.dumps([ls_task(33, t, [(s, e, "LOC", "القاهره")])], ensure_ascii=False),
    ["E003"], options={"offset_unit": "codepoint"}, desc="Label Studio value.text differs from the text by one letter.")
t = "يقع جبل طويق قرب الرياض"
add("p", 4, True, "canonical", jl([canon("r1", t, "codepoint", [sp(*find(t, "جبل طويق"), "LOC", "جبل طويق"), sp(*find(t, "الرياض"), "LOC", "الرياض")])]),
    [], desc="Span texts match the text.")
t = "فاز نادي الهلال في الرياض"
s, e = find(t, "الهلال")
add("p", 5, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "ORG", "الهلالي")])]), ["E003"],
    desc="The span text has an extra letter.")

# ============================================================================= (q) punctuation at edges
t = "زرنا الرياض، ثم جدة"
s, e = find(t, "الرياض،")
add("q", 1, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", "الرياض،"), sp(*find(t, "جدة"), "LOC", "جدة")])]),
    ["W102"], [sug("r1", 0, (s, e), (s, e - 1), "W102", "medium")], desc="An Arabic comma at the end of the span.")
t = "تقع بيروت؛ عاصمة لبنان، على البحر"
s, e = find(t, "بيروت؛")
add("q", 2, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "LOC", "بيروت؛")])]),
    ["W102"], [sug("r1", 0, (s, e), (s, e - 1), "W102", "medium")], desc="An Arabic semicolon at the end of the span.")
t = "قرأت «ألف ليلة وليلة» في الصيف"
s, e = find(t, "«ألف ليلة وليلة»")
add("q", 3, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "WORK", t[s:e])])]),
    ["W102"], [sug("r1", 0, (s, e), (s + 1, e - 1), "W102", "medium")], desc="Guillemets at both edges of a title.")
t = "هل زرت القاهرة؟"
add("q", 4, True, "canonical", jl([canon("r1", t, "codepoint", [sp(*find(t, "القاهرة"), "LOC", "القاهرة")])]), [],
    desc="An Arabic question mark right after the span, outside it.")
add("q", 5, False, "conll", conll([[("زرنا", "O"), ("الرياض،", "B-LOC"), ("ثم", "O"), ("جدة", "B-LOC")]]),
    ["W102"], options={"scheme": "IOB2"}, desc="CoNLL token with an attached Arabic comma, tagged as a location.")

# ============================================================================= (r) Latin entity in RTL text
t = "أعلنت شركة Microsoft عن مركز جديد في دبي"
add("r", 1, True, "canonical", jl([canon("r1", t, "codepoint", [sp(*find(t, "Microsoft"), "ORG", "Microsoft"), sp(*find(t, "دبي"), "LOC", "دبي")])]),
    [], desc="A Latin-script organisation name inside Arabic text, with correct offsets.")
t = "تعاونت جامعة الملك عبدالله مع " + LRM + "MIT" + LRM + " في مشروع بحثي"
s, e = find(t, LRM + "MIT" + LRM)
add("r", 2, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "ORG", t[s:e])])]),
    ["E012"], [sug("r1", 0, (s, e), (s + 1, e - 1), "E012", "high")],
    desc="Left-to-right marks around a Latin name are inside the span.")
t = "أعلنت شركة Microsoft عن مركز جديد"
s, e = find(t, "Microsoft")
add("r", 3, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, s + 5, "ORG", "Micro")])]),
    ["E007"], [sug("r1", 0, (s, s + 5), (s, e), "E007", "low")], desc="The span cuts the Latin-script name.")
t = "عمل المهندس سابقًا في جامعة ستانفورد وانتقل بعدها لـMozilla"
s, e = find(t, "Mozilla")
add("r", 4, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "ORG", "Mozilla")], clitic_policy="include")]),
    ["E008"], [sug("r1", 0, (s, e), (s - 2, e), "E008", "medium")],
    desc="clitic_policy include: the Arabic preposition لـ attached to a Latin-script name is left out of the span.")
t = "شاركت شركةNVIDIA في المعرض"
s, e = find(t, "NVIDIA")
add("r", 5, False, "canonical", jl([canon("r1", t, "codepoint", [sp(s, e, "ORG", "NVIDIA")])]), ["E016"],
    desc="A Latin-script name glued to the preceding Arabic word without a space.")

# ============================================================================= (v) valid records in each format
t = "التقى وفد من البنك الدولي بممثلين عن الاتحاد الأفريقي في أديس أبابا"
add("v", 1, True, "canonical",
    jl([canon("r1", t, "codepoint", [sp(*find(t, "البنك الدولي"), "ORG", "البنك الدولي"), sp(*find(t, "الاتحاد الأفريقي"), "ORG", "الاتحاد الأفريقي"),
                                     sp(*find(t, "أديس أبابا"), "LOC", "أديس أبابا")], label_set=["PER", "LOC", "ORG"], clitic_policy="exclude")]),
    [], desc="Three entities, a label set and the exclude clitic policy.")
t1 = "عاش ابن رشد في قرطبة"
t2 = "درّس الفارابي في بغداد ودمشق"
add("v", 2, True, "doccano",
    jl([{"id": 2602, "text": t1, "label": [[*find(t1, "ابن رشد"), "PER"], [*find(t1, "قرطبة"), "LOC"]]},
        {"id": 2603, "text": t2, "label": [[*find(t2, "الفارابي"), "PER"], [*find(t2, "بغداد"), "LOC"], [*find(t2, "دمشق"), "LOC"]]}]),
    [], options={"offset_unit": "codepoint", "clitic_policy": "exclude"}, desc="doccano JSONL with two records.")
t = "افتتحت مكتبة الملك عبدالعزيز العامة فرعًا في بكين"
task = ls_task(40, t, [(*find(t, "مكتبة الملك عبدالعزيز العامة"), "ORG", "مكتبة الملك عبدالعزيز العامة"), (*find(t, "بكين"), "LOC", "بكين")])
task2 = ls_task(40, t, [(*find(t, "بكين"), "LOC", "بكين")], ann_id=2)
task["annotations"].append(task2["annotations"][0])
add("v", 3, True, "label_studio", json.dumps([task], ensure_ascii=False), [], options={"offset_unit": "codepoint"},
    desc="One Label Studio task with two annotations; each annotation is checked as its own record.")
t = "رسم الإدريسي خريطة العالم في صقلية"
add("v", 4, True, "spacy", jl([[t, {"entities": [[*find(t, "الإدريسي"), "PER"], [*find(t, "صقلية"), "LOC"]]}]]), [],
    options={"offset_unit": "codepoint"}, desc="spaCy training tuple written as a JSON list.")
add("v", 5, True, "conll",
    conll([[("ولد", "O"), ("جبران", "B-PER"), ("خليل", "I-PER"), ("جبران", "I-PER"), ("في", "O"), ("بشري", "B-LOC")],
           [("ثم", "O"), ("هاجر", "O"), ("إلى", "O"), ("بوسطن", "B-LOC")]]),
    [], options={"scheme": "IOB2"}, desc="CoNLL IOB2 file with two sentences.")
add("v", 6, True, "hf_tokens", jl([{"id": "h7", "tokens": ["تقع", "جامعة", "الملك", "سعود", "في", "الرياض"],
                                    "ner_tags": ["O", "B-ORG", "I-ORG", "I-ORG", "O", "B-LOC"]}]),
    [], options={"scheme": "IOB2"}, desc="Hugging Face token row with string tags.")
t = "عاشَ المُتَنَبّي في حَلَبَ زمنًا"
s1, e1 = find(t, "المُتَنَبّي")
s2, e2 = find(t, "حَلَبَ")
add("v", 7, True, "canonical", jl([canon("r1", t, "grapheme", [sp(gr(t, s1), gr(t, e1), "PER", "المُتَنَبّي"), sp(gr(t, s2), gr(t, e2), "LOC", "حَلَبَ")])]),
    [], desc="Vocalised text with offsets counted in grapheme clusters.")


def main():
    assert len(FIX) == 100, len(FIX)
    ids = [f["fixture_id"] for f in FIX]
    assert len(set(ids)) == len(ids)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        for f in FIX:
            fh.write(json.dumps(f, ensure_ascii=False, sort_keys=False) + "\n")
    digest = hashlib.sha256(open(OUT, "rb").read()).hexdigest()
    per = {}
    for f in FIX:
        blob = json.dumps(f, ensure_ascii=False, sort_keys=True).encode("utf-8")
        per[f["fixture_id"]] = hashlib.sha256(blob).hexdigest()
    with open(os.path.join(ROOT, "fixtures", "dev", "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump({"file": "fixtures/dev/fixtures.jsonl", "sha256": digest, "fixtures": len(FIX),
                   "per_fixture_sha256": per}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    cats = {}
    for f in FIX:
        cats.setdefault(f["category"], [0, 0])[0 if f["valid"] else 1] += 1
    print(digest)
    print({k: tuple(v) for k, v in sorted(cats.items())})


if __name__ == "__main__":
    main()
