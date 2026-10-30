# Arabic NER offset fixtures: acceptance set

100 synthetic test cases for a validator of Arabic named-entity annotations. Each case is one record
(or one small file) in one of 6 annotation formats, a flag that says whether a correct validator must
accept it, and one English sentence that says what is wrong and where.

The cases cover 18 kinds of offset and tagging defect found in Arabic annotation exports, plus a
group of clean records. 26 cases are valid and 74 are invalid.

## Files

| File | Content |
|---|---|
| `acceptance.jsonl` | the fixtures, one JSON object per line |
| `make_acceptance.py` | the script that writes the fixtures and checks them |
| `README.md` | this description |
| `SHA256SUMS` | SHA-256 checksums of the three files above |

Rebuild and check with `python3 make_acceptance.py`; check without rewriting with
`python3 make_acceptance.py --check`. The script needs the Python standard library; when the `regex`
package is installed it also compares its grapheme segmentation with `regex`'s `\X`.

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

Invisible format characters (U+061C, U+200C, U+200F, U+2066, U+2069, U+FEFF) are written as `\uXXXX` escapes in the JSON so that they survive copying; they decode to the real characters.

## Formats as stored in `input`

- `canonical`: a JSON object `{id, text, offset_unit, normalization_declared, scheme, nested_policy,
  clitic_policy, spans: [{start, end, label, text}], tokens?, tags?}`. Offsets are half-open
  `[start, end)` in `offset_unit`: `utf8_byte` (bytes of the UTF-8 encoding), `codepoint` (Unicode
  code points, as Python `str` indices), `utf16` (UTF-16 code units, as JavaScript string indices) or
  `grapheme` (extended grapheme clusters, UAX #29). `tokens` is a list of strings that occur in `text`
  in order, separated by whitespace; when present, span edges must fall on token edges. `tags` has one
  tag per token in `scheme`. `normalization_declared` is `none` in this set.
- `conll_iob2` / `conll_biluo`: the file text as one string, one `token<TAB>tag` line per token, a blank
  line between sentences, LF line ends.
- `doccano_jsonl`: one JSONL record `{"id", "text", "label": [[start, end, "LABEL"], ...]}`.
- `labelstudio_json`: the export file as a JSON array of tasks
  `{"id", "data": {"text"}, "annotations": [{"id", "result": [{"value": {"start", "end", "text", "labels"}, ...}]}]}`.
- `spacy_jsonl`: one JSONL record `{"text", "entities": [[start, end, "LABEL"], ...]}`.

Labels are PER, LOC, ORG and MISC.

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
| (a) | astral emoji before the span (UTF-16 vs code point) | 5 | 1 | 4 |
| (b) | UTF-8 byte offsets | 5 | 2 | 3 |
| (c) | NFC composition drift | 5 | 0 | 5 |
| (d) | NFKC ligature expansion | 5 | 0 | 5 |
| (e) | span edge between a letter and its haraka or shadda | 5 | 1 | 4 |
| (f) | tatweel removed after annotation | 5 | 0 | 5 |
| (g) | bidi and zero-width controls at span edges | 5 | 1 | 4 |
| (h) | clitic boundary under include/exclude policy | 7 | 4 | 3 |
| (i) | token boundary inside the span | 5 | 1 | 4 |
| (j) | overlapping spans | 5 | 0 | 5 |
| (k) | nested spans under forbid/allow | 5 | 2 | 3 |
| (l) | empty, zero-length and reversed spans | 5 | 0 | 5 |
| (m) | invalid tag transitions (IOB2, BIOES/BILUO) | 6 | 0 | 6 |
| (n) | CRLF vs LF shifts | 5 | 1 | 4 |
| (o) | UTF-8 byte-order mark | 5 | 0 | 5 |
| (p) | span text differs from text[start:end] | 5 | 0 | 5 |
| (q) | Arabic punctuation attached at span edges | 5 | 3 | 2 |
| (r) | English entity inside right-to-left text | 5 | 3 | 2 |
| (v) | valid records | 7 | 7 | 0 |

| Format | Cases |
|---|---|
| canonical | 71 |
| conll_biluo | 3 |
| conll_iob2 | 5 |
| doccano_jsonl | 8 |
| labelstudio_json | 9 |
| spacy_jsonl | 4 |

## Licence

The fixtures and this README are licensed under CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). Attribution: Bayanat Labs, Arabic NER offset
fixtures, acceptance set. `make_acceptance.py` is licensed under Apache-2.0.

Questions and corrections: hello@bayanatlabs.com
