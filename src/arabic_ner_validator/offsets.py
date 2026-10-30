"""Offset maps between units and alternative readings of a text with alignment maps.

Units: codepoint (Python str index), utf16 (JavaScript String index), utf8_byte, grapheme
(extended grapheme clusters, regex \\X). Internally every offset is a code point index.
"""
from __future__ import annotations

import unicodedata
from bisect import bisect_right

from .chars import BOM, DIACRITICS, TATWEEL, grapheme_boundaries

UNITS = ("codepoint", "utf16", "utf8_byte", "grapheme")


class OffsetMap:
    def __init__(self, text: str):
        self.text = text
        self.n = len(text)
        u16 = [0]
        u8 = [0]
        for ch in text:
            o = ord(ch)
            u16.append(u16[-1] + (2 if o > 0xFFFF else 1))
            u8.append(u8[-1] + (1 if o < 0x80 else 2 if o < 0x800 else 3 if o < 0x10000 else 4))
        self.u16 = u16
        self.u8 = u8
        self.gb = grapheme_boundaries(text)
        self.gb_set = set(self.gb)
        self._inv = {"utf16": {v: i for i, v in enumerate(u16)}, "utf8_byte": {v: i for i, v in enumerate(u8)}}

    def total(self, unit: str) -> int:
        if unit == "codepoint":
            return self.n
        if unit == "utf16":
            return self.u16[-1]
        if unit == "utf8_byte":
            return self.u8[-1]
        return len(self.gb) - 1

    def to_cp(self, value: int, unit: str):
        """(cp, None) or (None, 'range') or (None, 'mid')."""
        if value < 0 or value > self.total(unit):
            return None, "range"
        if unit == "codepoint":
            return value, None
        if unit == "grapheme":
            return self.gb[value], None
        cp = self._inv[unit].get(value)
        if cp is None:
            return None, "mid"
        return cp, None

    def from_cp(self, cp: int, unit: str):
        if unit == "codepoint":
            return cp
        if unit == "utf16":
            return self.u16[cp]
        if unit == "utf8_byte":
            return self.u8[cp]
        if cp in self.gb_set:
            return self.gb.index(cp)
        return None

    def convert(self, s: int, e: int):
        return {u: [self.from_cp(s, u), self.from_cp(e, u)] for u in UNITS}

    def cluster_of(self, cp: int):
        """(start, end) of the grapheme cluster that contains position cp (cp strictly inside)."""
        i = bisect_right(self.gb, cp) - 1
        return self.gb[i], self.gb[i + 1]


class Reading:
    """A transformed text T with maps from positions in T to positions in the original text.

    start_map[p] is the original position for a span that starts at p in T; end_map[p] for a span
    that ends at p. None means that p has no counterpart (inside an expansion)."""

    def __init__(self, name: str, text: str, start_map: list, end_map: list):
        self.name = name
        self.text = text
        self.start_map = start_map
        self.end_map = end_map
        self._omap = None

    @property
    def omap(self) -> OffsetMap:
        if self._omap is None:
            self._omap = OffsetMap(self.text)
        return self._omap


def _norm_reading(text: str, form: str):
    t = unicodedata.normalize(form, text)
    if t == text:
        return None
    gb = grapheme_boundaries(text)
    chunks = [text[gb[i]:gb[i + 1]] for i in range(len(gb) - 1)]
    merged: list[str] = []
    for c in chunks:
        if merged and unicodedata.normalize(form, merged[-1] + c) != unicodedata.normalize(form, merged[-1]) + unicodedata.normalize(form, c):
            merged[-1] += c
        else:
            merged.append(c)
    if "".join(unicodedata.normalize(form, c) for c in merged) != t:
        merged = [text]
    start_map: list = []
    end_map: list = []
    a = 0
    for c in merged:
        nc = unicodedata.normalize(form, c)
        if nc == c:
            for k in range(len(c)):
                start_map.append(a + k)
                end_map.append(a + k)
        else:
            start_map.append(a)
            end_map.append(a)
            for _ in range(len(nc) - 1):
                start_map.append(None)
                end_map.append(None)
        a += len(c)
    start_map.append(a)
    end_map.append(a)
    assert len(start_map) == len(t) + 1
    return Reading(form, t, start_map, end_map)


def _removal_reading(name: str, text: str, remove, extend_end: bool):
    kept = [i for i, ch in enumerate(text) if not remove(i, ch)]
    if len(kept) == len(text):
        return None
    t = "".join(text[i] for i in kept)
    n = len(text)
    start_map = [kept[p] if p < len(kept) else n for p in range(len(kept) + 1)]
    end_map = [0]
    for p in range(1, len(kept) + 1):
        q = kept[p - 1] + 1
        if extend_end:
            while q < n and remove(q, text[q]):
                q += 1
        end_map.append(q)
    return Reading(name, t, start_map, end_map)


def _lf_to_crlf(text: str):
    parts, start_map, end_map = [], [], []
    changed = False
    for i, ch in enumerate(text):
        if ch == "\n" and (i == 0 or text[i - 1] != "\r"):
            parts.append("\r\n")
            start_map += [i, None]
            end_map += [i, None]
            changed = True
        else:
            parts.append(ch)
            start_map.append(i)
            end_map.append(i)
    if not changed:
        return None
    start_map.append(len(text))
    end_map.append(len(text))
    return Reading("lf_to_crlf", "".join(parts), start_map, end_map)


def _add_bom(text: str):
    t = BOM + text
    start_map = [0] + list(range(len(text) + 1))
    end_map = [0] + list(range(len(text) + 1))
    return Reading("add_bom", t, start_map, end_map)


READING_NAMES = ("NFC", "NFKC", "remove_tatweel", "remove_diacritics", "crlf_to_lf", "lf_to_crlf", "strip_bom", "add_bom")


def make_reading(text: str, name: str, file_bom: bool = False):
    if name in ("NFC", "NFKC"):
        return _norm_reading(text, name)
    if name == "remove_tatweel":
        return _removal_reading(name, text, lambda i, ch: ch == TATWEEL, False)
    if name == "remove_diacritics":
        return _removal_reading(name, text, lambda i, ch: ch in DIACRITICS, True)
    if name == "crlf_to_lf":
        return _removal_reading(name, text, lambda i, ch: ch == "\r" and i + 1 < len(text) and text[i + 1] == "\n", False)
    if name == "lf_to_crlf":
        return _lf_to_crlf(text)
    if name == "strip_bom":
        if text.startswith(BOM):
            return _removal_reading(name, text, lambda i, ch: i == 0, False)
        return None
    if name == "add_bom":
        return _add_bom(text) if file_bom and not text.startswith(BOM) else None
    raise ValueError(name)


def apply_policy(s: str, policy: str) -> str:
    """The string-level form of a reading, for comparing span texts."""
    if policy in ("NFC", "NFKC"):
        return unicodedata.normalize(policy, s)
    if policy == "remove_tatweel":
        return s.replace(TATWEEL, "")
    if policy == "remove_diacritics":
        return "".join(ch for ch in s if ch not in DIACRITICS)
    if policy == "crlf_to_lf":
        return s.replace("\r\n", "\n")
    raise ValueError(policy)
