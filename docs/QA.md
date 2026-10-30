# Quality report, version 0.1.0

All numbers below are recomputed by `scripts/qa_numbers.py` into `docs/qa/numbers.json`.

## Test cases

| Set | Cases | Valid | Invalid | Formats |
|---|---|---|---|---|
| dev | 100 | 25 | 75 | canonical 63, conll 8, doccano 14, hf_tokens 2, label_studio 10, spacy 3 |
| acceptance | 100 | 26 | 74 | canonical 71, conll 8, doccano 8, label_studio 9, spacy 4 |

Every case is synthetic: sentences written for these sets, with places, organisations, public figures or invented names. The dev cases were written before the validator code; each states the exact codes and repair suggestions expected. The acceptance cases were written separately from the category list only; each states its category and whether it is valid.

How a case passes: a valid case gives no error and no warning (notes do not count); an invalid case gives at least one error or warning whose code is listed for its category in `src/arabic_ner_validator/data/categories.json`. The dev cases are held to more: the exact set of codes and the exact suggestions.

## Results

- Dev: 100 of 100.
- Acceptance: 96 of 100; 93 of 100 with the category's primary code. On the build frozen before the acceptance set was read: 86 of 100 (`docs/qa/acceptance_run_frozen.json`). Changes after reading it are listed in `CHANGELOG.md`; no case in either set was edited.
- Python and the browser port gave identical reports on every case (0 differences).

| | Category | Acceptance cases | Passed |
|---|---|---|---|
| a | Astral character (emoji) before the span: UTF-16 vs code point offsets | 5 | 5 |
| b | UTF-8 byte offsets | 5 | 5 |
| c | NFC composition drift | 5 | 5 |
| d | NFKC ligature expansion | 5 | 4 |
| e | Span edge between a letter and its haraka or shadda | 5 | 5 |
| f | Tatweel removed after annotation | 5 | 4 |
| g | Bidi or zero-width control at a span edge | 5 | 5 |
| h | Clitic boundary under the include or exclude policy | 7 | 7 |
| i | Span edge inside a word or token | 5 | 5 |
| j | Overlapping spans | 5 | 5 |
| k | Nested spans under the forbid or allow policy | 5 | 5 |
| l | Empty, zero-length or reversed span | 5 | 5 |
| m | Invalid tag or tag transition (IOB2, BIOES, BILUO) | 6 | 6 |
| n | CRLF vs LF line-break shift | 5 | 5 |
| o | UTF-8 byte order mark | 5 | 5 |
| p | Span text differs from text[start:end] | 5 | 5 |
| q | Arabic punctuation at a span edge | 5 | 3 |
| r | Latin-script entity inside right-to-left text | 5 | 5 |
| v | Valid records that must produce no error or warning | 7 | 7 |

Acceptance cases that do not pass:

| Case | Valid | Codes reported | Note |
|---|---|---|---|
| acc-d03 | invalid | E003, E007, W101 | The stored text was NFKC-normalised after annotation. Neither the text nor the span texts keep the ligature, so nothing in the record shows that a ligature expanded; the record is reported invalid (span text mismatch, edge errors and a relocation suggestion to the right offsets) but not as NFKC drift. |
| acc-f05 | invalid | E001 | Tatweel was removed after annotation in a spaCy record without span text; the entity now ends past the text. The validator reports the offset as out of range (E001); nothing in the record names tatweel as the cause. |
| acc-q01 | valid | W102 | Valid case whose span ends with an Arabic comma. The validator gives the punctuation warning W102. The set's own rules allow that warning; the stricter rule used here (no warning on a valid case) counts it as a failure. |
| acc-q04 | valid | W102 | Same as acc-q01, with an Arabic question mark. |

## Agreement with spaCy

spaCy 3.8.18 is used as an oracle in the tests only. On the valid cases, records whose spans BILUO tags can express:

| Comparison | Checked | Agree |
|---|---|---|
| `offsets_to_biluo` | 51 | 51 |
| `biluo_to_offsets` | 51 | 51 |
| `iob_to_biluo` | 51 | 51 |
| `biluo_to_iob` | 44 | 44 |
| `round_trip` | 44 | 44 |

## Unicode

- The UCD-based normaliser used for the inventory passes `NormalizationTest.txt`: 16.0.0, 399,300 checks, 0 failures; 17.0.0, 400,680 checks, 0 failures (plus the identity rule for every other code point).
- `GraphemeBreakTest.txt`: `regex` \X passes 766 of 766 cases of 17.0.0 and 1092 of 1093 of 16.0.0 (one rule changed in 17.0.0); `Intl.Segmenter` in node 22.23.2 (ICU 78.2, Unicode 17.0) gives 766 and 1092.

## Random parity runs

`scripts/parity_fuzz.py` builds random records in all formats (broken and valid) and compares the two implementations: 4 runs, 18,000 inputs, 0 differences (`docs/qa/parity_fuzz.json`).

## Public datasets (aggregate counts only)

`scripts/smoke_test.py` ran the validator on three public Arabic NER datasets read locally; only these counts are kept (`docs/qa/smoke_report.json`).

| Dataset (revision) | Read as | Records | Spans | Spans with no finding | Findings by code |
|---|---|---|---|---|---|
| unimelb-nlp/wikiann (f0a3be6dc556) | hf_tokens rows, IOB2, tag names O,B-PER,I-PER,B-ORG,I-ORG,B-LOC,I-LOC | 40,000 | 45,027 | 33,028 | E002 18, E012 3, W102 11,978 |
| HebArabNlpProject/ShamNER (49886e6a1a8b) | canonical records, offsets read as code points (the dataset's character spans), span text checked where it is not null | 23,422 | 15,335 | 10,861 | E001 3, E002 3, E003 61, E005 79, E006 744, E007 776, E011 12, E016 4, I201 1,474, I202 197, I204 2,317, W101 3,153, W102 24 |
| asas-ai/DarNERcorp (ac00a90d2312) | token rows grouped into sentences at sentence-final punctuation, CoNLL, IOB2 | 2,524 | 6,070 | 6,062 | E002 3, E009 20, I201 1, W102 5 |

Most WikiANN warnings are parentheses kept inside entity spans (W102). In the character-span dataset, W101 counts spans that start or end with whitespace, and E006 counts spans nested in another span, which is an error only under the default `forbid` policy.
