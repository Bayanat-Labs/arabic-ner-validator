"""Default tokenisation when a format has no tokens: runs of word characters (letters, marks,
digits, connector punctuation); every other character that is not whitespace is a token of its own."""
from __future__ import annotations

from .chars import is_word, is_ws


def tokenize(text: str):
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if is_ws(ch):
            i += 1
            continue
        if is_word(ch):
            j = i + 1
            while j < n and is_word(text[j]):
                j += 1
            out.append((i, j))
            i = j
            continue
        out.append((i, i + 1))
        i += 1
    return out
