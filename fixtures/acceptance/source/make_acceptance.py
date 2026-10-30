#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Bayanat Labs
"""Build and check the acceptance fixtures for an Arabic NER offset validator.

Writes acceptance.jsonl, README.md and SHA256SUMS next to this script.

Each offset in the fixtures is computed here from the sentence text, in the unit the
record declares, and then checked again by slicing. A small reference checker at the
end of this file re-reads each fixture: a record marked valid must give no error, and a
record marked invalid must show the defect its expected_problem sentence describes.

Usage
  python3 make_acceptance.py           build the files and check them
  python3 make_acceptance.py --check   check the files on disk without rewriting them

Standard library. When the third-party 'regex' module is installed, its \\X grapheme
segmentation is compared with the built-in segmenter on each fixture text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
JSONL = HERE / "acceptance.jsonl"
README = HERE / "README.md"
SUMS = HERE / "SHA256SUMS"

try:  # optional cross-check of grapheme clusters
    import regex as _regex  # type: ignore
except ImportError:  # pragma: no cover
    _regex = None

CATS = {
    "a": "astral emoji before the span (UTF-16 vs code point)",
    "b": "UTF-8 byte offsets",
    "c": "NFC composition drift",
    "d": "NFKC ligature expansion",
    "e": "span edge between a letter and its haraka or shadda",
    "f": "tatweel removed after annotation",
    "g": "bidi and zero-width controls at span edges",
    "h": "clitic boundary under include/exclude policy",
    "i": "token boundary inside the span",
    "j": "overlapping spans",
    "k": "nested spans under forbid/allow",
    "l": "empty, zero-length and reversed spans",
    "m": "invalid tag transitions (IOB2, BIOES/BILUO)",
    "n": "CRLF vs LF shifts",
    "o": "UTF-8 byte-order mark",
    "p": "span text differs from text[start:end]",
    "q": "Arabic punctuation attached at span edges",
    "r": "English entity inside right-to-left text",
    "v": "valid records",
}

TATWEEL = "\u0640"
BOM = "\ufeff"
RLM, ALM, ZWNJ, LRI, PDI = "\u200f", "\u061c", "\u200c", "\u2066", "\u2069"
BIDI_AND_ZW = {"\u200b", "\u200c", "\u200d", "\u200e", "\u200f", "\u061c", "\u202a", "\u202b", "\u202c",
               "\u202d", "\u202e", "\u2066", "\u2067", "\u2068", "\u2069", BOM}

# --------------------------------------------------------------------------------------
# Grapheme clusters (UAX #29 extended grapheme clusters, enough for the scripts used here)
# --------------------------------------------------------------------------------------

def _is_pictographic(o: int) -> bool:
    return (0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF or 0x2300 <= o <= 0x23FF
            or 0x2B00 <= o <= 0x2BFF or o in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D))


def _gcb(ch: str) -> str:
    o = ord(ch)
    if ch == "\r":
        return "CarriageReturn"
    if ch == "\n":
        return "LineFeed"
    if o == 0x200D:
        return "ZWJ"
    if o == 0x200C or 0xFE00 <= o <= 0xFE0F or 0x1F3FB <= o <= 0x1F3FF or 0xE0020 <= o <= 0xE007F:
        return "Extend"
    if 0x1F1E6 <= o <= 0x1F1FF:
        return "RI"
    if 0x0600 <= o <= 0x0605 or o in (0x06DD, 0x070F, 0x0890, 0x0891, 0x08E2):
        return "Prepend"
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me"):
        return "Extend"
    if cat == "Mc":
        return "SpacingMark"
    if cat in ("Cc", "Cf", "Zl", "Zp"):
        return "Control"
    if _is_pictographic(o):
        return "ExtPict"
    return "Other"


def _builtin_clusters(text: str) -> list[str]:
    out: list[str] = []
    cur = ""
    prev = None
    ri_run = 0
    pict_zwj = False  # inside ExtPict Extend* ZWJ
    pict_seen = False
    for ch in text:
        g = _gcb(ch)
        brk = True
        if prev is None:
            brk = True
        elif prev == "CarriageReturn" and g == "LineFeed":
            brk = False
        elif prev in ("CarriageReturn", "LineFeed", "Control") or g in ("CarriageReturn", "LineFeed", "Control"):
            brk = True
        elif g in ("Extend", "ZWJ", "SpacingMark"):
            brk = False
        elif prev == "Prepend":
            brk = False
        elif g == "ExtPict" and pict_zwj:
            brk = False
        elif prev == "RI" and g == "RI" and ri_run % 2 == 1:
            brk = False
        if brk and cur:
            out.append(cur)
            cur = ""
        cur += ch
        # state for GB11 / GB12-13
        if g == "ExtPict":
            pict_seen = True
            pict_zwj = False
        elif g == "Extend" and pict_seen:
            pass
        elif g == "ZWJ" and pict_seen:
            pict_zwj = True
        else:
            pict_seen = False
            pict_zwj = False
        ri_run = ri_run + 1 if g == "RI" else 0
        prev = g
    if cur:
        out.append(cur)
    return out


def clusters(text: str) -> list[str]:
    own = _builtin_clusters(text)
    if _regex is not None:
        rx = _regex.findall(r"\X", text)
        if rx != own:
            raise AssertionError(f"grapheme segmentation differs from regex \\X for {text!r}")
    return own


def boundaries(text: str) -> list[int]:
    out, pos = [0], 0
    for c in clusters(text):
        pos += len(c)
        out.append(pos)
    return out

# --------------------------------------------------------------------------------------
# Offset units
# --------------------------------------------------------------------------------------

def width(ch: str, unit: str) -> int:
    if unit == "utf16":
        return 2 if ord(ch) > 0xFFFF else 1
    if unit == "utf8_byte":
        return len(ch.encode("utf-8"))
    return 1


def cp_to(text: str, cp: int, unit: str) -> int:
    """Code-point position -> offset in unit (raises if not representable)."""
    if not 0 <= cp <= len(text):
        raise ValueError("code point out of range")
    if unit == "codepoint":
        return cp
    if unit == "grapheme":
        b = boundaries(text)
        if cp not in b:
            raise ValueError("not a grapheme boundary")
        return b.index(cp)
    return sum(width(c, unit) for c in text[:cp])


def to_cp(text: str, off, unit: str):
    """Offset in unit -> (code point or None, reason)."""
    if not isinstance(off, int) or isinstance(off, bool):
        return None, "not an integer"
    if off < 0:
        return None, "out of range"
    if unit == "codepoint":
        return (off, "") if off <= len(text) else (None, "out of range")
    if unit == "grapheme":
        b = boundaries(text)
        return (b[off], "") if off < len(b) else (None, "out of range")
    acc = 0
    for i, ch in enumerate(text):
        if acc == off:
            return i, ""
        acc += width(ch, unit)
        if acc > off:
            return None, "inside a character"
    return (len(text), "") if acc == off else (None, "out of range")


def find(text: str, sub: str, occ: int = 1) -> tuple[int, int]:
    pos = -1
    for _ in range(occ):
        pos = text.find(sub, pos + 1)
        if pos < 0:
            raise ValueError(f"{sub!r} not found in {text!r}")
    return pos, pos + len(sub)


def U(on: str, sub: str, label: str, unit: str = "codepoint", occ: int = 1, stext=None, cut=(0, 0)) -> dict:
    """Span over `sub` in the annotation-time text `on`, with offsets in `unit` computed on `on`."""
    s, e = find(on, sub, occ)
    s, e = s + cut[0], e + cut[1]
    return {"start": cp_to(on, s, unit), "end": cp_to(on, e, unit), "label": label,
            "text": on[s:e] if stext is None else stext}


def shift(t: str, sp: dict, sub: str, unit: str = "codepoint", occ: int = 1, edge: str = "start") -> int:
    """Stored offset minus the true offset of `sub` in the stored text `t` (in `unit`)."""
    s, e = find(t, sub, occ)
    return sp[edge] - cp_to(t, s if edge == "start" else e, unit)


def moved(n: int, unit: str = "code point") -> str:
    assert n != 0
    return f"{abs(n)} {unit}{'s' if abs(n) != 1 else ''} towards the {'end' if n > 0 else 'start'}"


def late(n: int) -> str:
    assert n != 0
    return f"{abs(n)} code point{'s' if abs(n) != 1 else ''} too {'late' if n > 0 else 'early'}"


def sl(text: str, sp: dict, unit: str):
    s, _ = to_cp(text, sp["start"], unit)
    e, _ = to_cp(text, sp["end"], unit)
    return None if s is None or e is None else text[s:e]


def nfc(s):
    return unicodedata.normalize("NFC", s)


def nfd(s):
    return unicodedata.normalize("NFD", s)


def nfkc(s):
    return unicodedata.normalize("NFKC", s)

# --------------------------------------------------------------------------------------
# Format builders
# --------------------------------------------------------------------------------------

def canon(fid, text, spans, unit="codepoint", norm="none", scheme="IOB2", nested="forbid",
          clitic="unspecified", tokens=None, tags=None) -> dict:
    rec = {"id": fid, "text": text, "offset_unit": unit, "normalization_declared": norm, "scheme": scheme,
           "nested_policy": nested, "clitic_policy": clitic, "spans": spans}
    if tokens is not None:
        rec["tokens"] = tokens
    if tags is not None:
        rec["tags"] = tags
    return rec


def opts(unit="codepoint", nested="forbid", clitic="unspecified", scheme="IOB2", norm="none") -> dict:
    return {"offset_unit": unit, "normalization_declared": norm, "scheme": scheme,
            "nested_policy": nested, "clitic_policy": clitic}


def doccano(text, spans, rid=1) -> dict:
    return {"id": rid, "text": text, "label": [[s["start"], s["end"], s["label"]] for s in spans]}


def labelstudio(text, spans, rid=1) -> list:
    res = [{"id": f"r{i + 1}", "from_name": "label", "to_name": "text", "type": "labels",
            "value": {"start": s["start"], "end": s["end"], "text": s["text"], "labels": [s["label"]]}}
           for i, s in enumerate(spans)]
    return [{"id": rid, "data": {"text": text}, "annotations": [{"id": rid, "result": res}]}]


def spacy(text, spans) -> dict:
    return {"text": text, "entities": [[s["start"], s["end"], s["label"]] for s in spans]}


def conll(sents, bom=False) -> str:
    body = "\n".join("".join(f"{tok}\t{tag}\n" for tok, tag in s) for s in sents)
    return (BOM if bom else "") + body


def conll_line(sents, si, ti) -> int:
    """1-based line number of token ti of sentence si in the conll() file text."""
    line = 1
    for k in range(si):
        line += len(sents[k]) + 1
    return line + ti

# --------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------

F: list[dict] = []


def add(fid, cat, valid, fmt, inp, problem, note, options=None, expect=(), warn=()):
    assert fid.startswith(f"acc-{cat}"), fid
    F.append({"fixture_id": fid, "category": f"{cat}: {CATS[cat]}", "valid": valid, "format": fmt,
              "options": options, "input": inp, "expected_problem": problem, "author_note": note,
              "_expect": set(expect), "_warn": set(warn)})


def build() -> None:
    # ---------------- (a) astral emoji before the span ----------------
    t = "🎉 مبروك للجميع، فاز نادي الهلال بكأس الملك"
    s0 = U(t, "نادي الهلال", "ORG", "utf16")
    add("acc-a01", "a", False, "canonical", canon("acc-a01", t, [s0]),
        f"Span 0 (ORG) is stored as [{s0['start']}, {s0['end']}] in UTF-16 code units while offset_unit is codepoint; "
        f"the emoji U+1F389 at offset 0 is two UTF-16 units, so the code-point slice is shifted {moved(shift(t, s0, 'نادي الهلال'))}.",
        "Offsets read from a JavaScript string index; the declared unit was left at codepoint.",
        expect={"text_mismatch", "realign:unit:utf16"})

    t = "😂😂 والله ضحكت، شفت مقطع ناصر القصبي أمس؟"
    s0 = U(t, "ناصر القصبي", "PER", "utf16")
    add("acc-a02", "a", True, "canonical", canon("acc-a02", t, [s0], unit="utf16"),
        "No error: the offsets are UTF-16 code units as declared and the span matches the text (a warning that astral characters are present is acceptable).",
        "Gulf conversational sentence with two astral emoji before a public figure's name; control case for UTF-16 offsets.",
        warn={"astral"})

    t = "🛬 وصلنا مطار حمد الدولي والحين رايحين الفندق"
    s0 = U(t, "مطار حمد الدولي", "LOC", "codepoint")
    assert sl(t, s0, "utf16") == t[find(t, "مطار حمد الدولي")[0] - 1:find(t, "مطار حمد الدولي")[1] - 1]
    add("acc-a03", "a", False, "canonical", canon("acc-a03", t, [s0], unit="utf16"),
        f"Span 0 (LOC) is stored as code points [{s0['start']}, {s0['end']}] while offset_unit is utf16; "
        f"the emoji U+1F6EC at offset 0 is two UTF-16 units, so the UTF-16 slice is shifted {moved(shift(t, s0, 'مطار حمد الدولي', 'utf16'), 'unit')} and drops the last letter.",
        "Offsets computed with Python str indices and then declared as UTF-16.",
        expect={"text_mismatch", "realign:unit:codepoint"})

    t = "🌙🕌 رمضان كريم من دبي لكل الأهل في الرياض"
    sp = [U(t, "دبي", "LOC", "utf16"), U(t, "الرياض", "LOC", "utf16")]
    add("acc-a04", "a", False, "labelstudio_json", labelstudio(t, sp),
        f"Both results (LOC at [{sp[0]['start']}, {sp[0]['end']}] and LOC at [{sp[1]['start']}, {sp[1]['end']}]) count "
        f"the two astral emoji U+1F319 and U+1F54C as two units each, so with code-point offsets each slice is shifted "
        f"{moved(shift(t, sp[0], 'دبي'))} and differs from value.text.",
        "Label Studio style export whose offsets were counted in UTF-16 units; the run declares code points.",
        options=opts("codepoint"), expect={"text_mismatch", "realign:unit:utf16"})

    t = "شاركت جامعة الكويت 🏆 في مسابقة نظمتها جامعة السلطان قابوس هذا العام"
    sp = [U(t, "جامعة الكويت", "ORG", "utf16"), U(t, "جامعة السلطان قابوس", "ORG", "utf16")]
    assert shift(t, sp[0], "جامعة الكويت") == 0 and shift(t, sp[1], "جامعة السلطان قابوس") == 1
    assert shift(t, sp[0], "جامعة الكويت", edge="end") == 0
    add("acc-a05", "a", False, "canonical", canon("acc-a05", t, sp),
        f"Span 1 (ORG, stored [{sp[1]['start']}, {sp[1]['end']}]) comes after the emoji U+1F3C6 and uses UTF-16 offsets under offset_unit codepoint, "
        f"so it is shifted {moved(shift(t, sp[1], 'جامعة السلطان قابوس'))}; span 0 before the emoji is correct.",
        "Two spans around one astral emoji: only the span after it drifts.",
        expect={"text_mismatch", "realign:unit:utf16", "ok_span:0"})

    # ---------------- (b) UTF-8 byte offsets ----------------
    t = "استضافت مدينة العلا مهرجان شتاء طنطورة"
    sp = [U(t, "العلا", "LOC", "utf8_byte"), U(t, "شتاء طنطورة", "MISC", "utf8_byte")]
    add("acc-b01", "b", True, "canonical", canon("acc-b01", t, sp, unit="utf8_byte"),
        "No error: both spans are UTF-8 byte offsets as declared (two bytes per Arabic letter, one per space) and match the text.",
        "Control case for byte offsets on Arabic text.")

    t = "افتتح متحف اللوفر أبوظبي"
    s0 = U(t, "متحف اللوفر أبوظبي", "ORG", "utf8_byte")
    add("acc-b02", "b", False, "canonical", canon("acc-b02", t, [s0]),
        f"Span 0 (ORG) is stored as UTF-8 byte offsets [{s0['start']}, {s0['end']}] under offset_unit codepoint; "
        f"the end {s0['end']} is beyond the text length of {len(t)} code points.",
        "Byte offsets from a C or Rust tokenizer pasted into a code-point record.",
        expect={"range"})

    t = "قالت وزارة الطاقة إن الإنتاج ارتفع"
    s0 = U(t, "وزارة الطاقة", "ORG", "codepoint")
    assert to_cp(t, s0["start"], "utf8_byte")[0] is None
    assert t.encode("utf-8")[s0["start"] - 1:s0["start"] + 1].decode("utf-8") == "ل"
    add("acc-b03", "b", False, "canonical", canon("acc-b03", t, [s0], unit="utf8_byte"),
        f"Span 0 (ORG) is stored as code points [{s0['start']}, {s0['end']}] under offset_unit utf8_byte; "
        f"byte {s0['start']} falls inside the two-byte letter ل of the first word, so the start is not on a character boundary.",
        "Code-point offsets declared as bytes; the start lands in the middle of a UTF-8 sequence.",
        expect={"unit_boundary"})

    t = "تأهل منتخب المغرب إلى نصف النهائي"
    s, e = find(t, "المغرب")
    s0 = {"start": cp_to(t, s, "utf8_byte"), "end": cp_to(t, e, "utf8_byte") - 1, "label": "LOC", "text": "المغرب"}
    assert t.encode("utf-8")[s0["end"] - 1:s0["end"] + 1].decode("utf-8") == "ب" and t[e - 1] == "ب"
    add("acc-b04", "b", False, "canonical", canon("acc-b04", t, [s0], unit="utf8_byte"),
        f"Span 0 (LOC) ends at byte {s0['end']}, which is the second byte of the final letter ب, so the end is inside a UTF-8 sequence.",
        "End offset one byte short, a common off-by-one when byte lengths are computed by hand.",
        expect={"unit_boundary"})

    t = "📍 موقعنا: شارع 25، حي العليا، الرياض"
    sp = [U(t, "حي العليا", "LOC", "utf8_byte"), U(t, "الرياض", "LOC", "utf8_byte")]
    add("acc-b05", "b", True, "canonical", canon("acc-b05", t, sp, unit="utf8_byte"),
        "No error: the four-byte emoji, one-byte digits and two-byte letters are all counted correctly in UTF-8 bytes (a warning that astral characters are present is acceptable).",
        "Mixed widths before the spans: U+1F4CD (4 bytes), ASCII digits (1 byte), Arabic letters (2 bytes).",
        warn={"astral"})

    # ---------------- (c) NFC composition drift ----------------
    t = nfd("أعلنت") + " شركة طيران الخليج عن رحلات جديدة إلى مسقط"
    on = nfc(t)
    sp = [U(on, "طيران الخليج", "ORG"), U(on, "مسقط", "LOC")]
    d = shift(t, sp[0], "طيران الخليج")
    assert d == shift(t, sp[1], "مسقط")
    add("acc-c01", "c", False, "canonical", canon("acc-c01", t, sp),
        "Both spans were counted on the NFC form of the text, but the stored text writes the first word with U+0627 U+0654 instead of U+0623, "
        f"so each span slice is shifted {moved(d)}.",
        "First word typed with a decomposed alef plus hamza above; the annotation tool normalised to NFC before counting.",
        expect={"text_mismatch", "realign:nfc"})

    t = "انطلق " + nfd("مؤتمر") + " الأدباء العرب في مدينة تونس"
    on = nfc(t)
    s0 = U(on, "تونس", "LOC")
    add("acc-c02", "c", False, "canonical", canon("acc-c02", t, [s0]),
        f"Span 0 (LOC, [{s0['start']}, {s0['end']}]) was counted on NFC text, but an earlier word stores waw plus hamza above (U+0648 U+0654) "
        f"as two code points, so the slice is shifted {moved(shift(t, s0, 'تونس'))}.",
        "Decomposed U+0624 in a word before the entity.",
        expect={"text_mismatch", "realign:nfc"})

    t = "شارك منتخب " + nfd("الجزائر") + " في البطولة"
    on = nfc(t)
    s0 = U(on, "الجزائر", "LOC")
    assert t[s0["end"]] == "ر"
    add("acc-c03", "c", False, "canonical", canon("acc-c03", t, [s0]),
        f"Span 0 (LOC) ends at {s0['end']}, counted on NFC text, but inside the span the stored text writes yeh plus hamza above (U+064A U+0654), "
        f"so the slice stops before the final letter ر.",
        "Decomposed U+0626 inside the entity itself; the start is right and the end is one short.",
        expect={"text_mismatch", "realign:nfc"})

    t = "زار وفد من الإمارات معرض الكتاب في الشارقة"
    on = nfd(t)
    sp = [U(on, nfd("الإمارات"), "LOC"), U(on, "الشارقة", "LOC")]
    assert shift(t, sp[0], "الإمارات") == 0
    add("acc-c04", "c", False, "canonical", canon("acc-c04", t, sp),
        "The stored text is NFC, but both spans (and the text of span 0) were taken from its NFD form, where U+0625 in «الإمارات» is two code points; "
        f"span 0 ends {late(shift(t, sp[0], 'الإمارات', edge='end'))} and span 1 is shifted {moved(shift(t, sp[1], 'الشارقة'))}.",
        "Reverse drift: a pipeline decomposed the text (for diacritic handling) before counting offsets.",
        expect={"text_mismatch", "realign:nfd"})

    t = "تستضيف قطر بطولة كأس آسيا لكرة القدم"
    s0 = U(t, "كأس آسيا", "MISC", stext=nfd("كأس آسيا"))
    assert s0["text"] != t[s0["start"]:s0["end"]] and nfc(s0["text"]) == t[s0["start"]:s0["end"]]
    sp = [U(t, "قطر", "LOC"), s0]
    add("acc-c05", "c", False, "canonical", canon("acc-c05", t, sp),
        "Span 1 (MISC) has the right offsets, but its text field stores U+0627 U+0654 and U+0627 U+0653 where the text has U+0623 and U+0622, "
        "so span.text equals the slice only after NFC.",
        "The span text was copied from a decomposed source while the record text is NFC.",
        expect={"text_mismatch", "realign:nfc_of_span_text"})

    # ---------------- (d) NFKC ligature expansion ----------------
    t = "قال المتحدث \ufefb توجد رحلات إلى بيروت اليوم"
    on = nfkc(t)
    s0 = U(on, "بيروت", "LOC")
    add("acc-d01", "d", False, "canonical", canon("acc-d01", t, [s0]),
        f"Span 0 (LOC, [{s0['start']}, {s0['end']}]) was counted on NFKC text, where the lam-alef ligature U+FEFB before it becomes two letters, "
        f"so in the stored text the slice is shifted {moved(shift(t, s0, 'بيروت'))}.",
        "Text extracted from a PDF keeps the presentation-form ligature; the annotation tool applied NFKC.",
        expect={"text_mismatch", "realign:nfkc"})

    t = "استقبل عبد\ufdf2 الزهراني الضيوف في أبها"
    on = nfkc(t)
    sp = [U(on, "عبدالله الزهراني", "PER"), U(on, "أبها", "LOC")]
    assert sp[0]["start"] == find(t, "عبد")[0]
    add("acc-d02", "d", False, "canonical", canon("acc-d02", t, sp),
        "The stored text writes the name with the ligature U+FDF2 (one code point) while both spans were counted on NFKC text, where it is four letters; "
        f"span 0 ends {late(sp[0]['end'] - find(t, 'الزهراني')[1])} and span 1 is shifted {moved(shift(t, sp[1], 'أبها'))}.",
        "Invented person name written with the Allah ligature, as some keyboards and PDF fonts produce.",
        expect={"text_mismatch", "realign:nfkc"})

    orig = "تألق \ufefbعبو نادي الاتحاد في جدة"
    t = nfkc(orig)
    sp = [U(orig, "نادي الاتحاد", "ORG"), U(orig, "جدة", "LOC")]
    d = shift(t, sp[0], "نادي الاتحاد")
    assert d == shift(t, sp[1], "جدة")
    add("acc-d03", "d", False, "canonical", canon("acc-d03", t, sp, norm="none"),
        "The stored text was NFKC-normalised after annotation, which expanded U+FEFB in the second word into two letters, "
        f"so both spans, counted on the original text, are shifted {moved(d)}.",
        "Normalisation applied to the text field but not to the offsets.",
        expect={"text_mismatch", f"realign:shift:{-d:+d}"})

    t = "تخرج الشيخ من جامعة ا\ufef7زهر في القاهرة"
    on = nfkc(t)
    sp = [U(on, "جامعة الأزهر", "ORG"), U(on, "القاهرة", "LOC")]
    add("acc-d04", "d", False, "canonical", canon("acc-d04", t, sp),
        "Inside span 0 (ORG) the stored text uses U+FEF7 (lam-alef with hamza above), which NFKC expands to two letters; "
        f"the spans were counted on NFKC text, so span 0 ends {late(sp[0]['end'] - find(t, 'زهر')[1])} and span 1 is shifted {moved(shift(t, sp[1], 'القاهرة'))}.",
        "Ligature inside the entity, from PDF text extraction.",
        expect={"text_mismatch", "realign:nfkc"})

    t = "إن شاء \ufdf2 نشوفك الأسبوع الجاي في مسقط"
    on = nfkc(t)
    s0 = U(on, "مسقط", "LOC")
    add("acc-d05", "d", False, "canonical", canon("acc-d05", t, [s0]),
        f"Span 0 (LOC, [{s0['start']}, {s0['end']}]) was counted after NFKC expanded U+FDF2 into four letters, "
        f"so in the stored text it is shifted {moved(shift(t, s0, 'مسقط'))} and its end is beyond the text length of {len(t)} code points.",
        "Gulf conversational sentence with the Allah ligature before the entity.",
        expect={"range"})

    # ---------------- (e) span edge between a letter and its haraka or shadda ----------------
    t = nfc("وَصَلَ الوَفْدُ إِلَى دِمَشْقَ صَبَاحًا")
    w = nfc("دِمَشْقَ")
    s0 = U(t, w, "LOC", cut=(0, -1))
    assert t[s0["end"] - 1] == "ق" and t[s0["end"]] == "\u064e"
    add("acc-e01", "e", False, "canonical", canon("acc-e01", t, [s0]),
        f"Span 0 (LOC) ends at {s0['end']}, between the letter ق and its fatha, so the end falls inside a grapheme cluster.",
        "Fully vocalised sentence; the annotator left the case-ending vowel outside the span.",
        expect={"grapheme"})

    t = nfc("سَافَرَ أَخِي إِلَى بَغْدَادَ")
    w = nfc("بَغْدَادَ")
    s0 = U(t, w, "LOC", cut=(1, 0))
    assert t[s0["start"] - 1] == "ب" and t[s0["start"]] == "\u064e"
    add("acc-e02", "e", False, "canonical", canon("acc-e02", t, [s0]),
        f"Span 0 (LOC) starts at {s0['start']}, on the fatha that belongs to the first letter ب, so the span begins with a combining mark inside a grapheme cluster.",
        "Start offset one code point too far on vocalised text.",
        expect={"grapheme"})

    t = nfc("فَازَ الرَّسَّامُ الهَاشِمِيُّ بِالجَائِزَةِ")
    w = nfc("الهَاشِمِيُّ")
    s0 = U(t, w, "PER", cut=(0, -2))
    assert t[s0["end"] - 1] == "ي" and t[s0["end"]:s0["end"] + 2] == "\u064f\u0651"
    assert unicodedata.combining(t[find(t, w)[1] - 1]) and t[find(t, w)[1] - 2] in "\u064f\u0651"
    add("acc-e03", "e", False, "canonical", canon("acc-e03", t, [s0]),
        f"Span 0 (PER) ends at {s0['end']}, right after the letter ي and before its damma and shadda, so the end falls inside a grapheme cluster.",
        "Invented surname with a doubled nisba yeh; the shadda and case vowel were cut off.",
        expect={"grapheme"})

    t = nfc("زَارَ خَالِدٌ مَدِينَةَ تَبُوكَ")
    sp = [U(t, nfc("خَالِدٌ"), "PER", "grapheme"), U(t, nfc("تَبُوكَ"), "LOC", "grapheme")]
    add("acc-e04", "e", True, "canonical", canon("acc-e04", t, sp, unit="grapheme"),
        "No error: offsets are grapheme clusters as declared, each letter with its vowel counts as one, and both spans keep their final vowels.",
        "Control case for grapheme offsets on vocalised text.")

    t = nfc("يَعِيشُ أَخِي فِي القَاهِرَةِ مُنْذُ سَنَوَاتٍ")
    w = nfc("القَاهِرَةِ")
    s0 = U(t, w, "LOC", cut=(0, -1))
    assert t[s0["end"] - 1] == "ة" and t[s0["end"]] == "\u0650"
    add("acc-e05", "e", False, "doccano_jsonl", doccano(t, [s0]),
        f"The label [{s0['start']}, {s0['end']}, LOC] ends between the final ة and its kasra, so the end falls inside a grapheme cluster.",
        "doccano style label triple on vocalised text.",
        options=opts("codepoint"), expect={"grapheme"})

    # ---------------- (f) tatweel ----------------
    on = "مرحبـــاً بكم في مهرجـــان الورد في الطائف"
    t = on.replace(TATWEEL, "")
    sp = [U(on, "مهرجـــان الورد", "MISC"), U(on, "الطائف", "LOC")]
    add("acc-f01", "f", False, "canonical", canon("acc-f01", t, sp),
        "The spans were annotated on a version of the text with tatweel (span 0 text still contains U+0640), then the tatweel was removed from the text; "
        f"in the stored text span 0 is shifted {moved(shift(t, sp[0], 'مهرجان الورد'))} and span 1 {moved(shift(t, sp[1], 'الطائف'))}.",
        "Display stretching removed after annotation without updating the offsets.",
        expect={"text_mismatch"})

    t = "يـــا هلا والله، وصلتوا الدمام؟"
    on = t.replace(TATWEEL, "")
    s0 = U(on, "الدمام", "LOC")
    add("acc-f02", "f", False, "canonical", canon("acc-f02", t, [s0]),
        f"Span 0 (LOC, [{s0['start']}, {s0['end']}]) was counted on the text without tatweel, but the stored text keeps {t.count(TATWEEL)} U+0640 in the first word, "
        f"so the slice is shifted {moved(shift(t, s0, 'الدمام'))}.",
        "Gulf greeting with stretched first word; the tool stripped tatweel before counting.",
        expect={"text_mismatch", "realign:tatweel"})

    t = "أجمل مدينة زرتها هي مـسـقـط"
    on = t.replace(TATWEEL, "")
    s0 = U(on, "مسقط", "LOC")
    add("acc-f03", "f", False, "canonical", canon("acc-f03", t, [s0]),
        f"The entity is written with {t.count(TATWEEL)} tatweel characters in the stored text but span 0 ([{s0['start']}, {s0['end']}]) was counted without them, "
        f"so the slice ends in the middle of the stretched word.",
        "Tatweel inside the entity.",
        expect={"text_mismatch", "realign:tatweel"})

    t = "عـاجـل: البنك المركزي السعودي يصدر تقريره السنوي"
    on = t.replace(TATWEEL, "")
    s0 = U(on, "البنك المركزي السعودي", "ORG")
    add("acc-f04", "f", False, "labelstudio_json", labelstudio(t, [s0]),
        f"The result ([{s0['start']}, {s0['end']}], ORG) was counted on the text without tatweel, but data.text keeps {t.count(TATWEEL)} U+0640 in the first word, "
        f"so value.text differs from the slice, which is shifted {moved(shift(t, s0, 'البنك المركزي السعودي'))}.",
        "Stretched label word at the start of a short report line.",
        options=opts("codepoint"), expect={"text_mismatch", "realign:tatweel"})

    on = "شكـــراً لفريق نادي النصر"
    t = on.replace(TATWEEL, "")
    s0 = U(on, "نادي النصر", "ORG")
    add("acc-f05", "f", False, "spacy_jsonl", spacy(t, [s0]),
        f"The entity [{s0['start']}, {s0['end']}, ORG] was counted before {on.count(TATWEEL)} tatweel characters were removed from the text, "
        f"so its end {s0['end']} is beyond the text length of {len(t)} code points.",
        "Tatweel removed after annotation; the entity is at the end of the text, so the drift runs out of range.",
        options=opts("codepoint"), expect={"range"})

    # ---------------- (g) bidi and zero-width controls ----------------
    t = f"قضينا عطلة جميلة في الدوحة{RLM} مع العائلة"
    s0 = U(t, f"الدوحة{RLM}", "LOC")
    add("acc-g01", "g", False, "canonical", canon("acc-g01", t, [s0]),
        f"Span 0 (LOC) ends at {s0['end']}, after a RIGHT-TO-LEFT MARK (U+200F), so the span ends with an invisible bidi control.",
        "Text copied from a chat window that inserts RLM after words.",
        expect={"control_edge"})

    t = f"ودي أروح {ZWNJ}صلالة هالصيف"
    s0 = U(t, f"{ZWNJ}صلالة", "LOC")
    add("acc-g02", "g", False, "canonical", canon("acc-g02", t, [s0]),
        f"Span 0 (LOC) starts at {s0['start']} on a ZERO WIDTH NON-JOINER (U+200C), so the span begins with an invisible control.",
        "Gulf conversational sentence; the ZWNJ came from a Persian keyboard layout.",
        expect={"control_edge"})

    t = f"الفائز بالمركز الأول: {ALM}فيصل العنزي"
    s0 = U(t, f"{ALM}فيصل العنزي", "PER")
    add("acc-g03", "g", False, "canonical", canon("acc-g03", t, [s0]),
        f"Span 0 (PER) starts at {s0['start']} on an ARABIC LETTER MARK (U+061C), so the span begins with an invisible bidi control.",
        "Invented name; the ALM was added by an editor after the colon.",
        expect={"control_edge"})

    t = f"{RLM}مرحبا، أنا من الكويت وأدرس في جامعة الكويت"
    sp = [U(t, "الكويت", "LOC"), U(t, "جامعة الكويت", "ORG")]
    add("acc-g04", "g", True, "canonical", canon("acc-g04", t, sp),
        "No error: the RIGHT-TO-LEFT MARK at offset 0 is not at any span edge and both spans match the text.",
        "Control case: a bidi control in the text but away from the spans.")

    t = f"تابعوا حساب {RLM}وزارة الثقافة على المنصة"
    s0 = U(t, f"{RLM}وزارة الثقافة", "ORG")
    add("acc-g05", "g", False, "doccano_jsonl", doccano(t, [s0]),
        f"The label [{s0['start']}, {s0['end']}, ORG] starts on a RIGHT-TO-LEFT MARK (U+200F), so the span begins with an invisible bidi control.",
        "doccano style label triple.",
        options=opts("codepoint"), expect={"control_edge"})

    # ---------------- (h) clitic boundary ----------------
    t = "تعاون اقتصادي بين الكويت والبحرين"
    sp = [U(t, "الكويت", "LOC"), U(t, "والبحرين", "LOC")]
    add("acc-h01", "h", False, "canonical", canon("acc-h01", t, sp, clitic="exclude"),
        "Under clitic_policy exclude, span 1 (LOC) includes the conjunction و attached to «البحرين»; it should start one code point later.",
        "Conjunction plus definite article: the clitic is unambiguous.",
        expect={"clitic"})

    t = "تقام البطولة هذا العام بالقاهرة"
    s0 = U(t, "القاهرة", "LOC")
    add("acc-h02", "h", False, "canonical", canon("acc-h02", t, [s0], clitic="include"),
        f"Under clitic_policy include, span 0 (LOC) starts at {s0['start']}, after the preposition ب, so the attached clitic is left outside the span.",
        "Preposition plus definite article.",
        expect={"clitic"})

    t = "وقعت مصر والأردن اتفاقية للربط الكهربائي"
    sp = [U(t, "مصر", "LOC"), U(t, "الأردن", "LOC")]
    add("acc-h03", "h", True, "canonical", canon("acc-h03", t, sp, clitic="exclude"),
        "No error: under clitic_policy exclude the conjunction و is outside span 1 and the definite article stays inside it.",
        "Control case for exclude; the sentence starts with a verb whose first letter is و, which is not a clitic.")

    t = "قدم الطالب بحثه لجامعة الملك سعود"
    s0 = U(t, "لجامعة الملك سعود", "ORG")
    add("acc-h04", "h", True, "canonical", canon("acc-h04", t, [s0], clitic="include"),
        "No error: under clitic_policy include the span starts at the beginning of the word and keeps the preposition ل.",
        "Control case for include with a clitic that is not followed by the article.")

    t = "سافر الوفد التجاري إلى بغداد ثم إلى بيروت"
    sp = [U(t, "بغداد", "LOC"), U(t, "بيروت", "LOC")]
    add("acc-h05", "h", True, "canonical", canon("acc-h05", t, sp, clitic="exclude"),
        "No error: the initial ب of «بغداد» and «بيروت» is part of each name, not a clitic, so nothing has to be excluded.",
        "Trap for a clitic check that strips any initial ب.")

    t = "يعمل أخي حاليا بالمنامة"
    s0 = U(t, "بالمنامة", "LOC", cut=(2, 0))
    assert t[s0["start"] - 2:s0["start"] + 1] == "بال"
    add("acc-h06", "h", False, "canonical", canon("acc-h06", t, [s0], clitic="exclude"),
        f"Span 0 (LOC) starts at {s0['start']}, between the alef and lam of the definite article in «بالمنامة», so the boundary cuts the article instead of following the clitic ب.",
        "Under exclude the span should start right after ب.",
        expect={"clitic"})

    t = "زرنا الشارقة والفجيرة في يوم واحد"
    sp = [U(t, "الشارقة", "LOC"), U(t, "والفجيرة", "LOC")]
    add("acc-h07", "h", True, "canonical", canon("acc-h07", t, sp, clitic="unspecified"),
        "No error: clitic_policy is unspecified, so the conjunction و inside span 1 is not a violation (a warning is acceptable).",
        "With no declared policy a clitic at a span edge is a project decision.",
        warn={"clitic_unspecified"})

    # ---------------- (i) token boundary ----------------
    t = "قال مسؤول مصري إن المحادثات مستمرة"
    s0 = U(t, "مصر", "LOC")
    assert t[s0["end"]] == "ي" and t[s0["end"] + 1] == " "
    add("acc-i01", "i", False, "canonical", canon("acc-i01", t, [s0], tokens=t.split(" ")),
        f"Span 0 (LOC, [{s0['start']}, {s0['end']}]) ends inside token 2 «مصري», one letter before the token boundary.",
        "Nationality adjective partly labelled as a place.",
        expect={"token_boundary"})

    t = "#قطر تستضيف بطولة جديدة للتنس"
    s0 = U(t, "قطر", "LOC")
    add("acc-i02", "i", False, "canonical", canon("acc-i02", t, [s0], tokens=t.split(" ")),
        f"Span 0 (LOC) starts at {s0['start']}, inside token 0 «#قطر», after the hash sign.",
        "Hashtag kept as one whitespace token.",
        expect={"token_boundary"})

    t = "تقع جامعة الملك عبدالعزيز في جدة"
    sp = [U(t, "جامعة الملك عبد", "ORG"), U(t, "جدة", "LOC")]
    add("acc-i03", "i", False, "canonical", canon("acc-i03", t, sp, tokens=t.split(" ")),
        f"Span 0 (ORG) ends at {sp[0]['end']}, inside token 3 «عبدالعزيز», because the annotator expected a space inside the name.",
        "The name is written without a space in this text.",
        expect={"token_boundary", "ok_span:1"})

    t = "يقع برج خليفة في مدينة دبي"
    toks = t.split(" ")
    sp = [U(t, "برج خليفة", "LOC"), U(t, "دبي", "LOC")]
    add("acc-i04", "i", True, "canonical",
        canon("acc-i04", t, sp, tokens=toks, tags=["O", "B-LOC", "I-LOC", "O", "O", "B-LOC"]),
        "No error: span 0 covers two whole tokens, the token boundary inside it is expected, and the IOB2 tags agree with the spans.",
        "Control case for a multi-token span.")

    t = "أدرجت منظمة (اليونسكو) الموقع ضمن قائمة التراث العالمي"
    s0 = U(t, "اليونسكو", "ORG")
    add("acc-i05", "i", False, "canonical", canon("acc-i05", t, [s0], tokens=t.split(" ")),
        f"Span 0 (ORG, [{s0['start']}, {s0['end']}]) starts and ends inside token 2 «(اليونسكو)», because the whitespace token keeps the parentheses.",
        "Brackets attached to the word in a whitespace tokenisation.",
        expect={"token_boundary"})

    # ---------------- (j) overlapping spans ----------------
    t = "اجتمع وزراء مجلس التعاون الخليجي في الرياض"
    sp = [U(t, "مجلس التعاون", "ORG"), U(t, "التعاون الخليجي", "ORG"), U(t, "الرياض", "LOC")]
    add("acc-j01", "j", False, "canonical", canon("acc-j01", t, sp),
        f"Spans 0 [{sp[0]['start']}, {sp[0]['end']}] and 1 [{sp[1]['start']}, {sp[1]['end']}] overlap on «التعاون» without one containing the other.",
        "Two partial annotations of one organisation name merged into one record.",
        expect={"overlap"})

    t = "تخرجت من جامعة الملك فهد للبترول والمعادن في الظهران"
    sp = [U(t, "جامعة الملك فهد", "ORG"), U(t, "الملك فهد للبترول والمعادن", "ORG"), U(t, "الظهران", "LOC")]
    add("acc-j02", "j", False, "canonical", canon("acc-j02", t, sp, nested="allow"),
        f"Spans 0 [{sp[0]['start']}, {sp[0]['end']}] and 1 [{sp[1]['start']}, {sp[1]['end']}] cross each other; nested_policy allow permits containment, not partial overlap.",
        "Crossing spans under the permissive nesting policy.",
        expect={"overlap"})

    t = "أعلنت شركة أرامكو السعودية نتائجها الفصلية"
    sp = [U(t, "شركة أرامكو", "ORG"), U(t, "أرامكو السعودية", "ORG")]
    add("acc-j03", "j", False, "doccano_jsonl", doccano(t, sp),
        f"The labels [{sp[0]['start']}, {sp[0]['end']}] and [{sp[1]['start']}, {sp[1]['end']}] overlap on «أرامكو» without one containing the other.",
        "doccano style labels from two annotators.",
        options=opts("codepoint"), expect={"overlap"})

    t = "تقع جزيرة ياس في أبوظبي"
    sp = [U(t, "جزيرة ياس", "LOC"), U(t, "ياس في أبوظبي", "LOC")]
    add("acc-j04", "j", False, "labelstudio_json", labelstudio(t, sp),
        f"The two results [{sp[0]['start']}, {sp[0]['end']}] and [{sp[1]['start']}, {sp[1]['end']}] overlap on «ياس»; this is a crossing overlap, which nesting rules do not cover.",
        "Label Studio style export; the run allows nesting.",
        options=opts("codepoint", nested="allow"), expect={"overlap"})

    t = "حضرنا حفلا في دار الأوبرا السلطانية مسقط"
    sp = [U(t, "دار الأوبرا السلطانية", "ORG"), U(t, "السلطانية مسقط", "LOC")]
    add("acc-j05", "j", False, "spacy_jsonl", spacy(t, sp),
        f"The entities [{sp[0]['start']}, {sp[0]['end']}] and [{sp[1]['start']}, {sp[1]['end']}] overlap on «السلطانية» without one containing the other.",
        "spaCy style entity list; a spaCy Doc cannot hold these two entities at once.",
        options=opts("codepoint"), expect={"overlap"})

    # ---------------- (k) nested spans ----------------
    t = "ألقى الباحث محاضرة في جامعة الملك سعود"
    sp = [U(t, "جامعة الملك سعود", "ORG"), U(t, "الملك سعود", "PER")]
    add("acc-k01", "k", False, "canonical", canon("acc-k01", t, sp, nested="forbid"),
        f"Span 1 (PER, [{sp[1]['start']}, {sp[1]['end']}]) lies inside span 0 (ORG, [{sp[0]['start']}, {sp[0]['end']}]) while nested_policy is forbid.",
        "A person name inside an institution name.",
        expect={"nested"})

    t = "زرنا جامع الشيخ زايد الكبير في أبوظبي"
    sp = [U(t, "جامع الشيخ زايد الكبير", "LOC"), U(t, "الشيخ زايد", "PER"), U(t, "أبوظبي", "LOC")]
    add("acc-k02", "k", True, "canonical", canon("acc-k02", t, sp, nested="allow"),
        "No error: span 1 lies wholly inside span 0, which nested_policy allow permits, and all spans match the text.",
        "Control case for allowed nesting.")

    t = "هبطت الطائرة في مطار دبي الدولي"
    sp = [U(t, "مطار دبي الدولي", "LOC"), U(t, "دبي", "LOC")]
    add("acc-k03", "k", False, "doccano_jsonl", doccano(t, sp),
        f"The label [{sp[1]['start']}, {sp[1]['end']}, LOC] lies inside [{sp[0]['start']}, {sp[0]['end']}, LOC] while the run forbids nesting.",
        "doccano style labels; a city inside an airport name.",
        options=opts("codepoint", nested="forbid"), expect={"nested"})

    t = "يعمل أخي في بنك قطر الوطني"
    sp = [U(t, "بنك قطر الوطني", "ORG"), U(t, "قطر", "LOC")]
    add("acc-k04", "k", True, "labelstudio_json", labelstudio(t, sp),
        "No error: the LOC result lies inside the ORG result and the run allows nesting.",
        "Label Studio style control case for allowed nesting.",
        options=opts("codepoint", nested="allow"))

    t = "حضرنا أمسية في متحف قطر الوطني"
    sp = [U(t, "متحف قطر الوطني", "ORG"), U(t, "متحف قطر", "ORG")]
    add("acc-k05", "k", False, "canonical", canon("acc-k05", t, sp, nested="forbid"),
        f"Span 1 (ORG, [{sp[1]['start']}, {sp[1]['end']}]) shares its start with span 0 and lies inside it while nested_policy is forbid.",
        "Nesting with a shared start offset.",
        expect={"nested"})

    # ---------------- (l) empty, zero-length and reversed ----------------
    t = "تفتتح سلطنة عمان معرض مسقط الدولي للكتاب"
    s, _ = find(t, "معرض")
    sp = [U(t, "سلطنة عمان", "LOC"), {"start": s, "end": s, "label": "MISC", "text": ""}]
    add("acc-l01", "l", False, "canonical", canon("acc-l01", t, sp),
        f"Span 1 (MISC) has start = end = {s}, so it is empty.",
        "Leftover click in the annotation tool.",
        expect={"empty", "ok_span:0"})

    t = "شارك فريق من جامعة الإمارات في المؤتمر"
    s0 = U(t, "جامعة الإمارات", "ORG")
    s0["start"], s0["end"] = s0["end"], s0["start"]
    add("acc-l02", "l", False, "canonical", canon("acc-l02", t, [s0]),
        f"Span 0 (ORG) has start {s0['start']} greater than end {s0['end']}, so it is reversed.",
        "Selection made from right to left and stored without ordering the ends.",
        expect={"reversed"})

    t = "وش رايك نتغدى اليوم في الخبر؟"
    s, _ = find(t, "اليوم")
    sp = [{"start": s, "end": s, "label": "MISC", "text": ""}, U(t, "الخبر", "LOC")]
    add("acc-l03", "l", False, "doccano_jsonl", doccano(t, sp),
        f"The first label [{s}, {s}, MISC] is zero-length.",
        "doccano style labels in a Gulf conversational sentence.",
        options=opts("codepoint"), expect={"empty", "ok_span:1"})

    t = "ولد الشاعر في مدينة المحرق"
    s0 = U(t, "المحرق", "LOC")
    s0["start"], s0["end"] = s0["end"], s0["start"]
    add("acc-l04", "l", False, "labelstudio_json", labelstudio(t, [s0]),
        f"The result has value.start {s0['start']} greater than value.end {s0['end']}, so it is reversed.",
        "Label Studio style result with swapped ends.",
        options=opts("codepoint"), expect={"reversed"})

    t = "مبروك للفائزين من جامعة قطر"
    sp = [U(t, "جامعة قطر", "ORG"), {"start": len(t), "end": len(t), "label": "MISC", "text": ""}]
    add("acc-l05", "l", False, "canonical", canon("acc-l05", t, sp),
        f"Span 1 (MISC) has start = end = {len(t)}, the end of the text, so it is empty.",
        "Zero-length span at the very end; still in range, still empty.",
        expect={"empty", "ok_span:0"})

    # ---------------- (m) invalid tag transitions ----------------
    toks = "أعلن وزير خارجية سلطنة عمان عن زيارة رسمية".split(" ")
    sents = [list(zip(toks, ["O", "O", "O", "I-LOC", "I-LOC", "O", "O", "O"]))]
    add("acc-m01", "m", False, "conll_iob2", conll(sents),
        f"Token 3 «سلطنة» (line {conll_line(sents, 0, 3)}) is tagged I-LOC directly after O; IOB2 requires B-LOC at the start of an entity.",
        "IOB1 habits carried into an IOB2 file.",
        options=opts(None, scheme="IOB2"), expect={"scheme"})

    toks = "قاد عمر المختار المقاومة في ليبيا".split(" ")
    sents = [list(zip(toks, ["O", "B-PER", "I-LOC", "O", "O", "B-LOC"]))]
    add("acc-m02", "m", False, "conll_iob2", conll(sents),
        f"Token 2 «المختار» (line {conll_line(sents, 0, 2)}) is tagged I-LOC directly after B-PER; the entity type changes inside one entity.",
        "Historical figure; wrong type on the second token.",
        options=opts(None, scheme="IOB2"), expect={"scheme"})

    toks = "تأسست الجامعة العربية عام ١٩٤٥".split(" ")
    sents = [list(zip(toks, ["O", "O", "L-ORG", "O", "O"]))]
    add("acc-m03", "m", False, "conll_biluo", conll(sents),
        f"Token 2 «العربية» (line {conll_line(sents, 0, 2)}) is tagged L-ORG after O; in BILUO an L- tag must close an entity opened with B-.",
        "The B-ORG on the previous token was lost.",
        options=opts(None, scheme="BILUO"), expect={"scheme"})

    toks = "غنت فيروز في مهرجانات بعلبك".split(" ")
    sents = [list(zip(toks, ["O", "B-PER", "O", "B-MISC", "L-MISC"]))]
    add("acc-m04", "m", False, "conll_biluo", conll(sents),
        f"Token 1 «فيروز» (line {conll_line(sents, 0, 1)}) is tagged B-PER and followed by O; a one-token entity in BILUO must be U-PER.",
        "IOB2 tag kept during conversion to BILUO.",
        options=opts(None, scheme="BILUO"), expect={"scheme"})

    t = "أصدرت منظمة الصحة العالمية تقريرا جديدا"
    toks = t.split(" ")
    s0 = U(t, "منظمة الصحة العالمية", "ORG")
    add("acc-m05", "m", False, "canonical",
        canon("acc-m05", t, [s0], scheme="BIOES", tokens=toks, tags=["O", "B-ORG", "I-ORG", "I-ORG", "O", "O"]),
        "Token 3 «العالمية» is tagged I-ORG and followed by O; in BIOES the last token of the entity must be E-ORG.",
        "Canonical record with tokens and BIOES tags; the span shows the intended entity.",
        expect={"scheme"})

    toks = "وصلنا الكويت أمس الساعة عشر".split(" ")
    sents = [list(zip(toks, ["O", "U-LOC", "O", "O", "O"]))]
    add("acc-m06", "m", False, "conll_iob2", conll(sents),
        f"Token 1 «الكويت» (line {conll_line(sents, 0, 1)}) is tagged U-LOC, a BILUO tag that does not exist in IOB2.",
        "Mixed tag schemes in one file.",
        options=opts(None, scheme="IOB2"), expect={"scheme"})

    # ---------------- (n) CRLF vs LF ----------------
    t = "البند الأول: افتتاح معرض جدة للكتاب\r\nالبند الثاني: قمة اقتصادية في الكويت"
    on = t.replace("\r\n", "\n")
    sp = [U(on, "معرض جدة للكتاب", "MISC"), U(on, "الكويت", "LOC")]
    add("acc-n01", "n", False, "canonical", canon("acc-n01", t, sp),
        f"Span 1 (LOC) on the second line was counted on LF text, but the stored text has CRLF, so its slice is shifted {moved(shift(t, sp[1], 'الكويت'))}; span 0 on the first line is correct.",
        "Two-line record saved on Windows after annotation.",
        expect={"text_mismatch", "realign:crlf_to_lf", "ok_span:0"})

    t = "سارة: وينك؟\r\nنورة: في الرياض\r\nسارة: تعالي جدة"
    on = t.replace("\r\n", "\n")
    sp = [U(on, "سارة", "PER"), U(on, "الرياض", "LOC"), U(on, "جدة", "LOC")]
    add("acc-n02", "n", False, "canonical", canon("acc-n02", t, sp),
        f"Spans 1 and 2 were counted on LF text, so in the stored CRLF text span 1 (line 2) is shifted {moved(shift(t, sp[1], 'الرياض'))} "
        f"and span 2 (line 3) {moved(shift(t, sp[2], 'جدة'))}; span 0 on line 1 is correct.",
        "Gulf chat with invented first names; the shift grows by one per line break.",
        expect={"text_mismatch", "realign:crlf_to_lf", "ok_span:0"})

    t = "أهلا وسهلا\nمعكم برنامج الصباح من دبي"
    on = t.replace("\n", "\r\n")
    s0 = U(on, "دبي", "LOC")
    add("acc-n03", "n", False, "doccano_jsonl", doccano(t, [s0]),
        f"The label [{s0['start']}, {s0['end']}, LOC] was counted on a CRLF copy of the text, but the stored text has LF, "
        f"so the end {s0['end']} is beyond the text length of {len(t)} code points.",
        "doccano style label; the entity is the last word, so the drift runs out of range.",
        options=opts("codepoint"), expect={"range"})

    t = "عاجل\nارتفاع درجات الحرارة في الكويت\nالتفاصيل بعد قليل"
    on = t.replace("\n", "\r\n")
    s0 = U(on, "الكويت", "LOC")
    add("acc-n04", "n", False, "labelstudio_json", labelstudio(t, [s0]),
        f"The result ([{s0['start']}, {s0['end']}], LOC) was counted on CRLF text but data.text uses LF, so value.text differs from the slice, which is shifted {moved(shift(t, s0, 'الكويت'))}.",
        "Label Studio style export; offsets taken from a Windows copy of the text.",
        options=opts("codepoint"), expect={"text_mismatch", "realign:lf_to_crlf"})

    t = "رسالة من قطر\r\nرد من البحرين"
    sp = [U(t, "قطر", "LOC"), U(t, "البحرين", "LOC")]
    add("acc-n05", "n", True, "canonical", canon("acc-n05", t, sp),
        "No error: the carriage return is counted as one code point and both spans match the stored CRLF text.",
        "Control case: CRLF text with offsets that count it correctly.")

    # ---------------- (o) UTF-8 byte-order mark ----------------
    t = BOM + "استقبل متحف المستقبل في دبي آلاف الزوار"
    on = t[1:]
    sp = [U(on, "متحف المستقبل", "ORG"), U(on, "دبي", "LOC")]
    d = shift(t, sp[0], "متحف المستقبل")
    assert d == shift(t, sp[1], "دبي")
    add("acc-o01", "o", False, "canonical", canon("acc-o01", t, sp),
        f"The text starts with U+FEFF left over from a UTF-8 BOM, while both spans were counted without it, so each slice is shifted {moved(d)}.",
        "File read with a decoder that kept the BOM.",
        expect={"text_mismatch", "realign:strip_bom", "bom"})

    t = BOM + "جدة تستعد لاستضافة سباق الجائزة الكبرى"
    on = t[1:]
    s0 = U(on, "جدة", "LOC")
    assert t[s0["end"]] == "ة"
    add("acc-o02", "o", False, "doccano_jsonl", doccano(t, [s0]),
        f"The text starts with U+FEFF from a BOM and the label [{s0['start']}, {s0['end']}, LOC] was counted without it, so the span begins on the invisible U+FEFF and drops the last letter of «جدة».",
        "doccano style label triple; the entity is the first word.",
        options=opts("codepoint"), expect={"control_edge", "bom"})

    sents = [list(zip(["الرياض", "عاصمة", "السعودية"], ["B-LOC", "O", "B-LOC"]))]
    add("acc-o03", "o", False, "conll_iob2", conll(sents, bom=True),
        "The file starts with a UTF-8 byte-order mark, so token 0 on line 1 reads as U+FEFF followed by «الرياض» and the B-LOC entity begins with an invisible character.",
        "CoNLL file saved by an editor that writes a BOM.",
        options=opts(None, scheme="IOB2"), expect={"bom", "control_edge"})

    t = BOM + "البحرين تستضيف سباق الجائزة الكبرى"
    s0 = {"start": 0, "end": len(BOM + "البحرين"), "label": "LOC", "text": BOM + "البحرين"}
    add("acc-o04", "o", False, "canonical", canon("acc-o04", t, [s0]),
        f"Span 0 (LOC, [0, {s0['end']}]) includes the U+FEFF at offset 0, so the span starts with an invisible character.",
        "Offsets and span text are consistent with each other, but both include the BOM.",
        expect={"control_edge", "bom"})

    t = BOM + "برنامج زيارة الوفد إلى صلالة"
    on = t[1:]
    s0 = U(on, "صلالة", "LOC")
    add("acc-o05", "o", False, "labelstudio_json", labelstudio(t, [s0]),
        f"data.text starts with U+FEFF from a BOM and the result ([{s0['start']}, {s0['end']}]) was counted without it, so value.text differs from the slice, which is shifted {moved(shift(t, s0, 'صلالة'))}.",
        "Label Studio style export.",
        options=opts("codepoint"), expect={"text_mismatch", "realign:strip_bom", "bom"})

    # ---------------- (p) span text differs from the slice ----------------
    t = "يقع مقر الشركة في أبوظبي"
    s0 = U(t, "أبوظبي", "LOC", stext="أبو ظبي")
    add("acc-p01", "p", False, "canonical", canon("acc-p01", t, [s0]),
        f"Span 0 (LOC) has text «أبو ظبي» with a space, but text[{s0['start']}:{s0['end']}] is «أبوظبي».",
        "Span text typed from a gazetteer spelling.",
        expect={"text_mismatch"})

    t = "حضرنا الحفلة في دبي أمس"
    s0 = U(t, "دبي", "LOC", stext="دبی")
    add("acc-p02", "p", False, "canonical", canon("acc-p02", t, [s0]),
        "Span 0 (LOC) text ends with FARSI YEH (U+06CC) while the text has ARABIC LETTER YEH (U+064A).",
        "Span text entered with a Persian keyboard layout.",
        expect={"text_mismatch"})

    t = "تأهل منتخب الامارات إلى النهائي"
    s0 = U(t, "الامارات", "LOC", stext="الإمارات")
    add("acc-p03", "p", False, "canonical", canon("acc-p03", t, [s0]),
        "Span 0 (LOC) text has alef with hamza below (U+0625) where the text has a bare alef (U+0627).",
        "Hamza spelling corrected in the span text but not in the text.",
        expect={"text_mismatch"})

    t = "وصلنا جدة الساعة عشرة"
    s0 = U(t, "جدة", "LOC", stext="جده")
    add("acc-p04", "p", False, "labelstudio_json", labelstudio(t, [s0]),
        "value.text ends with heh (U+0647) where data.text has teh marbuta (U+0629).",
        "Label Studio style export with a hand-edited value.text.",
        options=opts("codepoint"), expect={"text_mismatch"})

    t = "تقع جامعة الشارقة في وسط المدينة"
    s0 = U(t, "جامعة الشارقة", "ORG", cut=(0, 1), stext="جامعة الشارقة")
    add("acc-p05", "p", False, "canonical", canon("acc-p05", t, [s0]),
        f"Span 0 (ORG) ends at {s0['end']}, one code point late, so the slice includes the following space while span.text does not.",
        "End offset one too large.",
        expect={"text_mismatch"})

    # ---------------- (q) Arabic punctuation at span edges ----------------
    t = "زرنا دبي، ثم أبوظبي"
    sp = [U(t, "دبي،", "LOC"), U(t, "أبوظبي", "LOC")]
    add("acc-q01", "q", True, "canonical", canon("acc-q01", t, sp),
        "No error: span 0 ends with the Arabic comma (U+060C) and its text agrees, so a warning about punctuation at the edge is expected but not an error.",
        "Punctuation attached to the word without a space.",
        warn={"punct_edge"})

    t = "توقفنا في العين؛ ثم واصلنا إلى مسقط"
    sp = [U(t, "العين؛", "LOC", stext="العين"), U(t, "مسقط", "LOC")]
    add("acc-q02", "q", False, "canonical", canon("acc-q02", t, sp),
        f"Span 0 (LOC) ends at {sp[0]['end']}, after the Arabic semicolon (U+061B), but span.text «العين» does not include it.",
        "Offsets taken from a whitespace token.",
        expect={"text_mismatch", "ok_span:1"})

    t = "هل زرت صلالة؟"
    s0 = U(t, "صلالة", "LOC", stext="صلالة؟")
    add("acc-q03", "q", False, "canonical", canon("acc-q03", t, [s0]),
        f"Span 0 (LOC, [{s0['start']}, {s0['end']}]) stops before the Arabic question mark (U+061F) but span.text includes it.",
        "Span text copied with the trailing punctuation.",
        expect={"text_mismatch"})

    t = "شفت مباراة الهلال؟"
    s0 = U(t, "الهلال؟", "ORG")
    add("acc-q04", "q", True, "canonical", canon("acc-q04", t, [s0]),
        "No error: span 0 ends with the Arabic question mark (U+061F) and its text agrees, so a warning about punctuation at the edge is expected but not an error.",
        "Gulf conversational question.",
        warn={"punct_edge"})

    t = "من وين أنت؟ من الكويت، وأنت؟"
    s0 = U(t, "الكويت", "LOC")
    add("acc-q05", "q", True, "doccano_jsonl", doccano(t, [s0]),
        "No error: the label stops before the Arabic comma, so no punctuation is at a span edge.",
        "doccano style control case.",
        options=opts("codepoint"))

    # ---------------- (r) English entity inside RTL text ----------------
    t = "أحب أبرمج بلغة Python في وقت الفراغ"
    s0 = U(t, "Python", "MISC")
    add("acc-r01", "r", True, "canonical", canon("acc-r01", t, [s0]),
        "No error: the Latin-script entity inside Arabic text has code-point offsets that match the text.",
        "Control case for mixed-direction text.")

    t = f"تابعنا مباراة {LRI}Real Madrid{PDI} في المقهى"
    on = t.replace(LRI, "").replace(PDI, "")
    s0 = U(on, "Real Madrid", "ORG")
    assert t[s0["start"]] == LRI and t[s0["end"]] == "d"
    add("acc-r02", "r", False, "canonical", canon("acc-r02", t, [s0]),
        f"Span 0 (ORG, [{s0['start']}, {s0['end']}]) was counted on text without the LEFT-TO-RIGHT ISOLATE (U+2066) and POP DIRECTIONAL ISOLATE (U+2069) "
        f"around the English name, so the slice starts on U+2066 and drops the final d.",
        "An editor wrapped the English name in bidi isolates after annotation.",
        expect={"text_mismatch", "realign:strip_bidi"})

    t = "أتعلم Python وJavaScript هذا الفصل"
    sp = [U(t, "Python", "MISC"), U(t, "JavaScript", "MISC")]
    add("acc-r03", "r", False, "canonical", canon("acc-r03", t, sp, clitic="include"),
        f"Under clitic_policy include, span 1 (MISC) starts at {sp[1]['start']}, after the Arabic conjunction و attached to the English name, so the clitic is left outside the span.",
        "Arabic clitic directly attached to a Latin-script word.",
        expect={"clitic", "ok_span:0"})

    t = "درست في MIT ثم رجعت أشتغل في الدمام"
    sp = [U(t, "MIT", "ORG"), U(t, "الدمام", "LOC")]
    add("acc-r04", "r", True, "spacy_jsonl", spacy(t, sp),
        "No error: both entities match the text; the English acronym and the Arabic place use the same code-point counting.",
        "spaCy style control case.",
        options=opts("codepoint"))

    t = "تابعت مباراة Manchester City أمس مع أصدقائي في الشارقة"
    sp = [U(t, "Manchester City", "ORG"), U(t, "الشارقة", "LOC")]
    add("acc-r05", "r", True, "labelstudio_json", labelstudio(t, sp),
        "No error: the two-word English entity and the Arabic place both match the text.",
        "Label Studio style control case.",
        options=opts("codepoint"))

    # ---------------- (v) valid records ----------------
    t = "ولد نجيب محفوظ في القاهرة عام ١٩١١"
    sp = [U(t, "نجيب محفوظ", "PER"), U(t, "القاهرة", "LOC")]
    add("acc-v01", "v", True, "spacy_jsonl", spacy(t, sp),
        "No error: both entities match the text.",
        "Biographical sentence about a public figure; the first word begins with a root و that is not a clitic.",
        options=opts("codepoint"))

    t = "ودي أزور أبها في الصيف لأن جوها حلو"
    s0 = U(t, "أبها", "LOC")
    add("acc-v02", "v", True, "canonical", canon("acc-v02", t, [s0]),
        "No error: the span matches the text.",
        "Gulf conversational sentence.")

    sents = [list(zip("افتتح معرض الرياض الدولي للكتاب أبوابه".split(" "), ["O", "B-MISC", "I-MISC", "I-MISC", "I-MISC", "O"])),
             list(zip("وحضر الافتتاح وفد من سلطنة عمان".split(" "), ["O", "O", "O", "O", "B-LOC", "I-LOC"]))]
    add("acc-v03", "v", True, "conll_iob2", conll(sents),
        "No error: two sentences with well-formed IOB2 tags.",
        "Two sentences separated by a blank line.",
        options=opts(None, scheme="IOB2"))

    sents = [list(zip("وصل فريق نادي الوحدة إلى الطائف".split(" "), ["O", "O", "B-ORG", "L-ORG", "O", "U-LOC"]))]
    add("acc-v04", "v", True, "conll_biluo", conll(sents),
        "No error: well-formed BILUO tags with a two-token and a one-token entity.",
        "Control case for BILUO.",
        options=opts(None, scheme="BILUO"))

    t = "تحدثت ليلى الكعبي عن تجربتها في دبي"
    sp = [U(t, "ليلى الكعبي", "PER"), U(t, "دبي", "LOC")]
    add("acc-v05", "v", True, "canonical",
        canon("acc-v05", t, sp, scheme="BIOES", tokens=t.split(" "), tags=["O", "B-PER", "E-PER", "O", "O", "O", "S-LOC"]),
        "No error: well-formed BIOES tags that agree with both spans.",
        "Invented person name; canonical record with tokens and tags.")

    t = "الجو اليوم حار جدا"
    add("acc-v06", "v", True, "canonical", canon("acc-v06", t, []),
        "No error: a record with no spans is valid.",
        "Sentence with no entities.")

    t = "سجّل اللاعب ٣ أهداف في مرمى نادي الاتحاد"
    s0 = U(t, "نادي الاتحاد", "ORG", "utf16")
    add("acc-v07", "v", True, "canonical", canon("acc-v07", t, [s0], unit="utf16"),
        "No error: with no astral characters UTF-16 and code-point offsets coincide, and the span matches the text.",
        "Arabic-Indic digit and a shadda before the span.")

# --------------------------------------------------------------------------------------
# Reference checker
# --------------------------------------------------------------------------------------

PREFIX = {"IOB2": "BI", "BIOES": "BIES", "BILUO": "BILU"}
SINGLE = {"BIOES": "S", "BILUO": "U"}
LAST = {"BIOES": "E", "BILUO": "L"}


def decode_tags(tags, scheme):
    spans, probs, cur = [], [], None
    single, last = SINGLE.get(scheme), LAST.get(scheme)

    def close_iob(k):
        nonlocal cur
        if cur is not None:
            spans.append((cur[0], k, cur[1]))
            cur = None

    for k, tag in enumerate(tags):
        if tag == "O":
            if cur is not None:
                if scheme == "IOB2":
                    close_iob(k)
                else:
                    probs.append((k, "entity not closed before O"))
                    cur = None
            continue
        if len(tag) < 3 or tag[1] != "-" or tag[0] not in PREFIX[scheme]:
            probs.append((k, f"tag {tag} not in {scheme}"))
            cur = None
            continue
        p, lab = tag[0], tag[2:]
        if p == "B":
            if cur is not None:
                if scheme == "IOB2":
                    close_iob(k)
                else:
                    probs.append((k, "entity not closed before B"))
            cur = (k, lab)
        elif p == "I":
            if cur is None or cur[1] != lab:
                probs.append((k, "I- without matching B-"))
                cur = None
        elif p == last:
            if cur is None or cur[1] != lab:
                probs.append((k, f"{last}- without matching B-"))
                cur = None
            else:
                spans.append((cur[0], k + 1, lab))
                cur = None
        elif p == single:
            if cur is not None:
                probs.append((k, "entity not closed before single"))
                cur = None
            spans.append((k, k + 1, lab))
    if cur is not None:
        if scheme == "IOB2":
            close_iob(len(tags))
        else:
            probs.append((len(tags), "entity not closed at end"))
    return spans, probs


def align_tokens(text, tokens):
    pos, out = 0, []
    for tok in tokens:
        i = text.find(tok, pos)
        if i < 0 or text[pos:i].strip() != "":
            return None
        out.append((i, i + len(tok)))
        pos = i + len(tok)
    if text[pos:].strip() != "":
        return None
    return out


def parse_conll(s):
    sents, cur = [], []
    for line in s.split("\n"):
        if line == "":
            if cur:
                sents.append(cur)
                cur = []
            continue
        tok, tag = line.split("\t")
        cur.append((tok, tag))
    if cur:
        sents.append(cur)
    return sents


def to_records(fx):
    fmt, inp, o = fx["format"], fx["input"], fx["options"] or {}

    def rec(text, spans, **kw):
        r = {"text": text, "offset_unit": o.get("offset_unit"), "normalization_declared": o.get("normalization_declared"),
             "scheme": o.get("scheme"), "nested_policy": o.get("nested_policy"), "clitic_policy": o.get("clitic_policy"),
             "spans": spans}
        r.update(kw)
        return r

    if fmt == "canonical":
        return [inp]
    if fmt == "doccano_jsonl":
        return [rec(inp["text"], [{"start": a, "end": b, "label": c, "text": None} for a, b, c in inp["label"]])]
    if fmt == "spacy_jsonl":
        return [rec(inp["text"], [{"start": a, "end": b, "label": c, "text": None} for a, b, c in inp["entities"]])]
    if fmt == "labelstudio_json":
        out = []
        for task in inp:
            spans = []
            for ann in task["annotations"]:
                for r in ann["result"]:
                    v = r["value"]
                    spans.append({"start": v["start"], "end": v["end"], "label": v["labels"][0], "text": v["text"]})
            out.append(rec(task["data"]["text"], spans))
        return out
    if fmt in ("conll_iob2", "conll_biluo"):
        out = []
        for sent in parse_conll(inp):
            toks = [a for a, _ in sent]
            tags = [b for _, b in sent]
            out.append(rec(" ".join(toks), None, tokens=toks, tags=tags, offset_unit="codepoint"))
        return out
    raise ValueError(fmt)


def check_record(r):
    errors, warns = set(), set()
    text, unit = r["text"], r["offset_unit"]
    if text.startswith(BOM):
        errors.add("bom")
    if not text.isascii() and any(ord(c) > 0xFFFF for c in text):
        warns.add("astral")
    bnd = set(boundaries(text))
    tokpos = None
    if r.get("tokens") is not None:
        tokpos = align_tokens(text, r["tokens"])
        if tokpos is None:
            errors.add("token_align")
    spans = r["spans"]
    if r.get("tags") is not None:
        tspans, probs = decode_tags(r["tags"], r["scheme"])
        if probs:
            errors.add("scheme")
        elif tokpos is not None:
            derived = [{"start": cp_to(text, tokpos[i][0], unit), "end": cp_to(text, tokpos[j - 1][1], unit), "label": lab,
                        "text": text[tokpos[i][0]:tokpos[j - 1][1]]} for i, j, lab in tspans]
            if spans is None:
                spans = derived
            elif sorted((d["start"], d["end"], d["label"]) for d in derived) != sorted((s["start"], s["end"], s["label"]) for s in spans):
                errors.add("tags_spans_mismatch")
    spans = spans or []
    good = []
    for idx, sp in enumerate(spans):
        span_err = set()
        cs, why_s = to_cp(text, sp["start"], unit)
        ce, why_e = to_cp(text, sp["end"], unit)
        if cs is None or ce is None:
            span_err.add("unit_boundary" if "inside" in (why_s + why_e) else "range")
        elif cs == ce:
            span_err.add("empty")
        elif cs > ce:
            span_err.add("reversed")
        else:
            piece = text[cs:ce]
            if sp.get("text") is not None and piece != sp["text"]:
                span_err.add("text_mismatch")
                for tag in realign(text, sp, unit):
                    errors.add("realign:" + tag)
            if cs not in bnd or ce not in bnd:
                span_err.add("grapheme")
            if unicodedata.category(piece[0]) in ("Cc", "Cf") or unicodedata.category(piece[-1]) in ("Cc", "Cf"):
                span_err.add("control_edge")
            if piece[0].isspace() or piece[-1].isspace():
                warns.add("ws_edge")
            if unicodedata.category(piece[0]).startswith("P") or unicodedata.category(piece[-1]).startswith("P"):
                warns.add("punct_edge")
            if tokpos is not None:
                if cs not in {a for a, _ in tokpos} or ce not in {b for _, b in tokpos}:
                    span_err.add("token_boundary")
            ws = cs
            while ws > 0 and not text[ws - 1].isspace():
                ws -= 1
            prefix = text[ws:cs]
            pol = r.get("clitic_policy")
            if pol == "include" and prefix:
                span_err.add("clitic")
            if pol == "exclude":
                if prefix and not all(c in "وفبلك" for c in prefix):
                    span_err.add("clitic")
                if len(piece) > 3 and piece[0] in "وفبلك" and (piece[1:3] == "ال" or piece[1].isascii() and piece[1].isalpha()):
                    span_err.add("clitic")
            if pol == "unspecified" and len(piece) > 3 and piece[0] in "وفبلك" and piece[1:3] == "ال":
                warns.add("clitic_unspecified")
            if not span_err:
                good.append((idx, cs, ce))
        if span_err:
            errors |= span_err
        else:
            errors.add(f"ok_span:{idx}")
    for x in range(len(good)):
        for y in range(x + 1, len(good)):
            _, a1, b1 = good[x]
            _, a2, b2 = good[y]
            if a2 < b1 and a1 < b2:  # they intersect
                inside = (a1 <= a2 and b2 <= b1) or (a2 <= a1 and b1 <= b2)
                if not inside:
                    errors.add("overlap")
                elif r.get("nested_policy") != "allow":
                    errors.add("nested")
    return errors, warns


def realign(text, sp, unit):
    tags = []
    for u in ("codepoint", "utf16", "utf8_byte", "grapheme"):
        if u != unit and sl(text, sp, u) == sp["text"]:
            tags.append("unit:" + u)
    variants = {
        "nfc": nfc(text), "nfkc": nfkc(text), "nfd": nfd(text), "tatweel": text.replace(TATWEEL, ""),
        "crlf_to_lf": text.replace("\r\n", "\n"), "lf_to_crlf": text.replace("\n", "\r\n") if "\r" not in text else text,
        "strip_bom": text[1:] if text.startswith(BOM) else text,
        "strip_bidi": "".join(c for c in text if c not in BIDI_AND_ZW),
    }
    for name, v in variants.items():
        if v != text and sl(v, sp, unit) == sp["text"]:
            tags.append(name)
    piece = sl(text, sp, unit)
    if piece is not None and piece != sp["text"] and nfc(sp["text"]) == piece:
        tags.append("nfc_of_span_text")
    s, _ = to_cp(text, sp["start"], unit)
    if s is not None and unit == "codepoint":
        for d in range(-4, 5):
            if d and text[max(0, s + d):max(0, s + d) + len(sp["text"])] == sp["text"]:
                tags.append(f"shift:{d:+d}")
    return tags


def check_fixture(fx):
    errors, warns = set(), set()
    for r in to_records(fx):
        e, w = check_record(r)
        errors |= e
        warns |= w
    real = {e for e in errors if not (e.startswith("ok_span:") or e.startswith("realign:") or e.startswith("shift:"))}
    if fx["valid"]:
        assert not real, f"{fx['fixture_id']}: valid fixture shows {sorted(real)}"
        extra = warns - fx["_warn"]
        assert not extra, f"{fx['fixture_id']}: unexpected warnings {sorted(extra)}"
        assert fx["_warn"] <= warns, f"{fx['fixture_id']}: expected warnings {sorted(fx['_warn'] - warns)} not raised"
    else:
        assert real, f"{fx['fixture_id']}: invalid fixture shows no defect"
        missing = fx["_expect"] - errors
        assert not missing, f"{fx['fixture_id']}: expected {sorted(missing)} but found {sorted(errors)}"
    # every canonical-like input text and span text must survive a JSON round trip unchanged
    assert json.loads(dumps(fx["input"])) == fx["input"]
    return errors, warns


def static_checks(fx):
    """Checks on the written record itself, independent of the reference checker."""
    assert fx["format"] in ("canonical", "conll_iob2", "conll_biluo", "doccano_jsonl", "labelstudio_json", "spacy_jsonl")
    if fx["format"] == "canonical":
        r = fx["input"]
        assert r["offset_unit"] in ("utf8_byte", "codepoint", "utf16", "grapheme")
        assert r["normalization_declared"] in ("none", "NFC", "NFKC")
        assert r["scheme"] in ("IOB2", "BIOES", "BILUO")
        assert r["nested_policy"] in ("forbid", "allow")
        assert r["clitic_policy"] in ("include", "exclude", "unspecified")
        assert r["id"] == fx["fixture_id"]
        assert fx["options"] is None
    else:
        assert fx["options"] is not None
    if fx["valid"]:
        for r in to_records(fx):
            t = r["text"]
            assert nfc(t) == t and nfkc(t) == t, f"{fx['fixture_id']}: valid text changes under NFC/NFKC"
            assert TATWEEL not in t and BOM not in t, fx["fixture_id"]

# --------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------

def _escape_invisible(s: str) -> str:
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat in ("Cf", "Zl", "Zp") or (cat == "Cc" and ch not in "\n\r\t"):
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def dumps(obj) -> str:
    return _escape_invisible(json.dumps(obj, ensure_ascii=False, separators=(", ", ": ")))


def public(fx):
    return {k: v for k, v in fx.items() if not k.startswith("_")}


def counts():
    by_cat, by_fmt = {}, {}
    for fx in F:
        c = fx["category"].split(":")[0]
        d = by_cat.setdefault(c, [0, 0])
        d[0 if fx["valid"] else 1] += 1
        by_fmt[fx["format"]] = by_fmt.get(fx["format"], 0) + 1
    return by_cat, by_fmt


def readme_text() -> str:
    by_cat, by_fmt = counts()
    n = len(F)
    nv = sum(1 for fx in F if fx["valid"])
    rows = "\n".join(f"| ({c}) | {CATS[c]} | {by_cat[c][0] + by_cat[c][1]} | {by_cat[c][0]} | {by_cat[c][1]} |"
                     for c in CATS)
    frows = "\n".join(f"| {k} | {v} |" for k, v in sorted(by_fmt.items()))
    invisible, labels = set(), set()

    def walk(x):
        if isinstance(x, str):
            invisible.update(c for c in x if unicodedata.category(c) == "Cf")
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for fx in F:
        walk(fx["input"])
        for r in to_records(fx):
            labels.update(s["label"] for s in (r["spans"] or []))
            labels.update(t[2:] for t in (r.get("tags") or []) if t != "O")
    inv = ", ".join(f"U+{ord(c):04X}" for c in sorted(invisible))
    order = ["PER", "LOC", "ORG", "MISC"]
    assert labels <= set(order), labels
    labs = [x for x in order if x in labels]
    return README_TEMPLATE.format(n=n, nv=nv, ni=n - nv, ncat=len(CATS) - 1, rows=rows, frows=frows,
                                  nfmt=len(by_fmt), inv=inv, labels=", ".join(labs[:-1]) + " and " + labs[-1])


README_TEMPLATE = """# Arabic NER offset fixtures: acceptance set

{n} synthetic test cases for a validator of Arabic named-entity annotations. Each case is one record
(or one small file) in one of {nfmt} annotation formats, a flag that says whether a correct validator must
accept it, and one English sentence that says what is wrong and where.

The cases cover {ncat} kinds of offset and tagging defect found in Arabic annotation exports, plus a
group of clean records. {nv} cases are valid and {ni} are invalid.

## Files

| File | Content |
|---|---|
| `acceptance.jsonl` | the fixtures, one JSON object per line |
| `make_acceptance.py` | the script that writes the fixtures and checks them |
| `README.md` | this description |
| `SHA256SUMS` | SHA-256 checksums of the three files above |

Rebuild and check with `python3 make_acceptance.py`; check without rewriting with
`python3 make_acceptance.py --check`. The script needs the Python standard library; when the `regex`
package is installed it also compares its grapheme segmentation with `regex`'s `\\X`.

## Method

- The sentences were written for this set: formal Modern Standard Arabic in a reporting register,
  everyday conversational Arabic and Gulf dialect. Names are public figures, places, organisations or
  invented personal names. No sentence describes a real private person.
- The set was written from the validator's input specification, without reference to the validator's
  source code or to its development fixtures.
- Each offset is computed by `make_acceptance.py` from the sentence text in the unit the record declares
  (or, for a drift case, on the text as it was at annotation time) and checked again by slicing.
- A reference checker in the same script re-reads each fixture. Valid cases must give no error and
  no unexpected warning; invalid cases must show the defect named in `expected_problem`.
- `acceptance.jsonl` is byte-identical when built with Python 3.12 (Unicode 15.0.0) and Python 3.14
  (Unicode 16.0.0).

The Arabic text has not yet been reviewed by a native Arabic writer; the English governs.

## Fixture fields

| Field | Meaning |
|---|---|
| `fixture_id` | `acc-` + category letter + number |
| `category` | category letter and name, for example `a: astral emoji before the span (UTF-16 vs code point)` |
| `valid` | `true`: a correct validator reports no error (warnings are allowed where `expected_problem` says so); `false`: it reports at least one error for the defect described |
| `format` | `canonical`, `conll_iob2`, `conll_biluo`, `doccano_jsonl`, `labelstudio_json` or `spacy_jsonl` |
| `options` | run settings for formats that cannot state them (`offset_unit`, `normalization_declared`, `scheme`, `nested_policy`, `clitic_policy`); `null` for `canonical`, which states them in the record; `offset_unit` is `null` for CoNLL files, which have no offsets |
| `input` | the record or file as the format stores it (see below) |
| `expected_problem` | one sentence: what is wrong and where (for valid cases, why it is clean) |
| `author_note` | how the case was built |

Invisible format characters ({inv}) are written as `\\uXXXX` escapes in the JSON so that they survive copying; they decode to the real characters.

## Formats as stored in `input`

- `canonical`: a JSON object `{{id, text, offset_unit, normalization_declared, scheme, nested_policy,
  clitic_policy, spans: [{{start, end, label, text}}], tokens?, tags?}}`. Offsets are half-open
  `[start, end)` in `offset_unit`: `utf8_byte` (bytes of the UTF-8 encoding), `codepoint` (Unicode
  code points, as Python `str` indices), `utf16` (UTF-16 code units, as JavaScript string indices) or
  `grapheme` (extended grapheme clusters, UAX #29). `tokens` is a list of strings that occur in `text`
  in order, separated by whitespace; when present, span edges must fall on token edges. `tags` has one
  tag per token in `scheme`. `normalization_declared` is `none` in this set.
- `conll_iob2` / `conll_biluo`: the file text as one string, one `token<TAB>tag` line per token, a blank
  line between sentences, LF line ends.
- `doccano_jsonl`: one JSONL record `{{"id", "text", "label": [[start, end, "LABEL"], ...]}}`.
- `labelstudio_json`: the export file as a JSON array of tasks
  `{{"id", "data": {{"text"}}, "annotations": [{{"id", "result": [{{"value": {{"start", "end", "text", "labels"}}, ...}}]}}]}}`.
- `spacy_jsonl`: one JSONL record `{{"text", "entities": [[start, end, "LABEL"], ...]}}`.

Labels are {labels}.

## Conventions used to decide validity

- Clitics. The attached clitics are the conjunctions و and ف, the prepositions ب, ل and ك, and the
  definite article ال. Under `include` a span starts at the beginning of the written word, so attached
  clitics are inside it. Under `exclude` the conjunctions and prepositions are outside the span and the
  definite article stays inside it as part of the name (as in «الأردن» from «والأردن»). Under
  `unspecified` a clitic at a span edge is not an error. A letter that belongs to the name (the ب of
  «بغداد») is never a clitic.
- Nesting and overlap. Under `forbid` a span may not lie inside another; under `allow` it may. Spans
  that cross (each has text outside the other) are an error under both policies. Spans that only touch
  do not overlap.
- Punctuation and whitespace at a span edge are warnings, not errors, when the span text agrees with
  the slice.
- A span edge inside a grapheme cluster (between a letter and its haraka or shadda) is an error.
- A bidi or zero-width control, or U+FEFF, as the first or last character of a span is an error.
- A record with no spans is valid.

## Counts

| Category | Name | Cases | Valid | Invalid |
|---|---|---|---|---|
{rows}

| Format | Cases |
|---|---|
{frows}

## Licence

The fixtures and this README are licensed under CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). Attribution: Bayanat Labs, Arabic NER offset
fixtures, acceptance set. `make_acceptance.py` is licensed under Apache-2.0.

Questions and corrections: hello@bayanatlabs.com
"""


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="check the files on disk without rewriting them")
    a = ap.parse_args()
    build()
    ids = [fx["fixture_id"] for fx in F]
    assert len(ids) == len(set(ids)) == 100, len(ids)
    for fx in F:
        static_checks(fx)
        check_fixture(fx)
    by_cat, _ = counts()
    for c in CATS:
        assert sum(by_cat[c]) >= 4, c
    assert sum(1 for fx in F if fx["valid"]) >= 15
    body = "".join(dumps(public(fx)) + "\n" for fx in F)
    readme = readme_text()
    if a.check:
        assert JSONL.read_text(encoding="utf-8") == body, "acceptance.jsonl differs from a fresh build"
        assert README.read_text(encoding="utf-8") == readme, "README.md differs from a fresh build"
        for line in SUMS.read_text(encoding="utf-8").splitlines():
            h, name = line.split("  ", 1)
            assert sha256(HERE / name) == h, f"checksum mismatch for {name}"
    else:
        JSONL.write_text(body, encoding="utf-8")
        README.write_text(readme, encoding="utf-8")
        names = ["README.md", "acceptance.jsonl", "make_acceptance.py"]
        SUMS.write_text("".join(f"{sha256(HERE / nm)}  {nm}\n" for nm in names), encoding="utf-8")
    # round trip of the file as written
    for line, fx in zip(JSONL.read_text(encoding="utf-8").splitlines(), F):
        assert json.loads(line) == public(fx)
    nv = sum(1 for fx in F if fx["valid"])
    print(f"{len(F)} fixtures, {nv} valid, {len(F) - nv} invalid; unicodedata {unicodedata.unidata_version}; "
          f"regex cross-check {'on' if _regex else 'off'}")
    for c in CATS:
        print(f"  ({c}) {sum(by_cat[c]):3d}  valid {by_cat[c][0]:2d}  invalid {by_cat[c][1]:2d}  {CATS[c]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
