"""Character classes shared by every check.

The browser port (web/validator.js) defines the same classes with the same code point lists and
Unicode property expressions, so both give the same answers on the same text.
"""
from __future__ import annotations

import regex

_WORD = regex.compile(r"[\p{L}\p{M}\p{Nd}\p{Pc}]")
_LETTER = regex.compile(r"\p{L}")
_ALNUM = regex.compile(r"[\p{L}\p{N}]")
_MARK = regex.compile(r"\p{M}")
_PUNCT = regex.compile(r"\p{P}")
_ARABIC = regex.compile(r"\p{Script=Arabic}")
_LATIN = regex.compile(r"\p{Script=Latin}")
_GRAPHEME = regex.compile(r"\X")

# Unicode White_Space, listed explicitly so that every engine uses the same set.
WHITESPACE = frozenset(chr(c) for c in [0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20, 0x85, 0xA0, 0x1680,
                                        *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F, 0x3000])
# Bidi controls and zero-width characters that should never sit at a span edge.
CONTROLS = frozenset(chr(c) for c in [0x00AD, 0x061C, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F,
                                      0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2060,
                                      0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF])
# Punctuation that is part of an entity's content at an edge (percent and per-mille signs).
PUNCT_EXEMPT = frozenset("%٪‰؉؊")
TATWEEL = "ـ"
BOM = "﻿"


def _ranges(*pairs):
    out = set()
    for a, b in pairs:
        out.update(chr(c) for c in range(a, b + 1))
    return frozenset(out)


# Arabic diacritics removed by the remove_diacritics reading: harakat, tanween, shadda, sukun, the
# extended marks after them, superscript alef and the small Quranic marks. The hamza and madda marks
# (U+0653 to U+0655) are left alone because they change the letter.
DIACRITICS = _ranges((0x0610, 0x061A), (0x064B, 0x0652), (0x0656, 0x065F), (0x0670, 0x0670),
                     (0x06D6, 0x06DC), (0x06DF, 0x06E4), (0x06E7, 0x06E8), (0x06EA, 0x06ED))

CONJ = "وف"
PREP = "بكل"


def is_word(ch: str) -> bool:
    return bool(_WORD.match(ch))


def is_letter(ch: str) -> bool:
    return bool(_LETTER.match(ch))


def is_alnum(ch: str) -> bool:
    return bool(_ALNUM.match(ch))


def is_mark(ch: str) -> bool:
    return bool(_MARK.match(ch))


def is_ws(ch: str) -> bool:
    return ch in WHITESPACE


def is_control(ch: str) -> bool:
    return ch in CONTROLS


def is_punct(ch: str) -> bool:
    return bool(_PUNCT.match(ch))


def is_arabic_letter(ch: str) -> bool:
    return bool(_LETTER.match(ch)) and bool(_ARABIC.match(ch)) and ch != TATWEEL


def is_latin_letter(ch: str) -> bool:
    return bool(_LETTER.match(ch)) and bool(_LATIN.match(ch))


def script_of(ch: str) -> str | None:
    if is_arabic_letter(ch):
        return "Arabic"
    if is_latin_letter(ch):
        return "Latin"
    return None


def grapheme_boundaries(text: str) -> list[int]:
    """Code point positions that start a grapheme cluster, plus len(text)."""
    out, pos = [], 0
    for m in _GRAPHEME.finditer(text):
        out.append(pos)
        pos += len(m.group(0))
    out.append(pos)
    if not text:
        return [0]
    return out


def uplus(ch: str) -> str:
    return "U+%04X" % ord(ch)
