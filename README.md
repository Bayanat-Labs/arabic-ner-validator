# Arabic NER Offset Validator

By **Bayanat Labs**. Version 0.1.0.

`arabic-ner-validator` checks Arabic named-entity annotations before they are used for training. It finds offsets counted in the wrong unit (code points, UTF-16 units, UTF-8 bytes, grapheme clusters), text that changed after annotation (NFC, NFKC, tatweel or diacritic removal, CRLF and LF, a byte order mark), span edges that cut a letter from its haraka or a clitic from its word, bidi and zero-width controls at span edges, overlaps and nesting, and BIO, BIOES and BILUO tag errors. It reads 6 formats: its own JSON Lines contract, doccano JSONL, Label Studio JSON, spaCy JSONL, CoNLL and Hugging Face token rows.

Repairs are written as an audit diff of offsets and are never applied unless you ask: labels and text are never changed. The offset unit is never guessed; when it is missing or wrong, the report says which unit makes the offsets fit.

- Web app (runs in the browser, nothing is uploaded): https://huggingface.co/spaces/Bayanat-Labs/arabic-ner-offset-validator
- Test cases as a dataset: https://huggingface.co/datasets/Bayanat-Labs/arabic-ner-offset-fixtures

## Install

```bash
pip install "git+https://github.com/Bayanat-Labs/arabic-ner-validator@v0.1.0"
```

Python 3.10 or later. The only runtime dependency is [`regex`](https://pypi.org/project/regex/) (grapheme clusters and Unicode properties).

## Use

```bash
# canonical records declare their unit; other formats take --offset-unit
arabic-ner-validator check annotations.jsonl --json report.json
arabic-ner-validator check export.jsonl --format doccano --offset-unit utf16 --clitic-policy exclude -v
arabic-ner-validator check project.json --format label_studio --offset-unit codepoint --labels PER,LOC,ORG --csv findings.csv
arabic-ner-validator check train.conll --format conll --scheme IOB2
arabic-ner-validator check export.jsonl --format doccano --offset-unit utf16 --json share.json --share
arabic-ner-validator check export.jsonl --format doccano --offset-unit codepoint --apply-suggestions repaired.jsonl
arabic-ner-validator convert export.jsonl --format spacy --offset-unit codepoint --to BILUO
arabic-ner-validator codes --lang ar
```

The exit status is 1 when there is an error (and with `--strict`, a warning), 2 on a usage error.

```python
from arabic_ner_validator import validate, share_report

report, records, repairs = validate(open("export.jsonl", "rb").read(),
                                    {"format": "doccano", "offset_unit": "utf16", "clitic_policy": "exclude"})
print(report["summary"]["by_code"])
```

## Input

The canonical record ([`schema/input.schema.json`](schema/input.schema.json), JSON Schema 2020-12):

```json
{"id": "r1", "text": "زرنا جدة والرياض", "offset_unit": "codepoint", "clitic_policy": "exclude",
 "nested_policy": "forbid", "spans": [{"start": 5, "end": 8, "label": "LOC", "text": "جدة"},
                                      {"start": 10, "end": 16, "label": "LOC", "text": "الرياض"}]}
```

- `offset_unit` (required): `codepoint` (Python `str` index), `utf16` (JavaScript `String` index), `utf8_byte`, or `grapheme` (extended grapheme clusters, UAX #29). Offsets are `[start, end)` on the text exactly as stored.
- `clitic_policy`: `include` (proclitics و ف ب ك ل and the article are inside the span), `exclude` (conjunctions and prepositions are outside; the article stays with the name, as in «الرياض» from «والرياض»), or `unspecified` (default; reported as a note only).
- `nested_policy`: `forbid` (default) or `allow`. Crossing spans are always an error.
- `normalization_declared`: `none` (default), `NFC`, `NFKC`, `NFD`, `NFKD` or `policy:<id>`.
- Optional `tokens` (strings in text order, or `{start, end}` objects) and `tags` with `scheme` (IO, IOB1, IOB2, IOE1, IOE2, BIOES, BILUO).

`schema/rejected_examples.jsonl` holds 20 records that the contract rejects; the tests check that the schema and the validator both reject each one.

## What it checks

| | Category | Code | Dev cases | Acceptance cases |
|---|---|---|---|---|
| a | Astral character (emoji) before the span: UTF-16 vs code point offsets | E014, E015 | 5 | 5 |
| b | UTF-8 byte offsets | E014, E015 | 5 | 5 |
| c | NFC composition drift | E011, E004 | 5 | 5 |
| d | NFKC ligature expansion | E011 | 5 | 5 |
| e | Span edge between a letter and its haraka or shadda | E004 | 5 | 5 |
| f | Tatweel removed after annotation | E011 | 5 | 5 |
| g | Bidi or zero-width control at a span edge | E012 | 5 | 5 |
| h | Clitic boundary under the include or exclude policy | E008 | 6 | 7 |
| i | Span edge inside a word or token | E007 | 5 | 5 |
| j | Overlapping spans | E005 | 5 | 5 |
| k | Nested spans under the forbid or allow policy | E006 | 5 | 5 |
| l | Empty, zero-length or reversed span | E002 | 5 | 5 |
| m | Invalid tag or tag transition (IOB2, BIOES, BILUO) | E009, E010 | 7 | 6 |
| n | CRLF vs LF line-break shift | E013 | 5 | 5 |
| o | UTF-8 byte order mark | E018 | 5 | 5 |
| p | Span text differs from text[start:end] | E003 | 5 | 5 |
| q | Arabic punctuation at a span edge | W102 | 5 | 5 |
| r | Latin-script entity inside right-to-left text | E016, E012, E007, E008, E003 | 5 | 5 |
| v | Valid records that must produce no error or warning | none | 7 | 7 |

The checks, the readings tried for drift and the repair rules are described in [`docs/CHECKS.md`](docs/CHECKS.md).

## Codes

Each finding has a stable code, a message in English and Arabic, the span index and offsets.

| Code | Severity | Meaning |
|---|---|---|
| E001 | error | Offset out of range |
| E002 | error | Empty, zero-length or reversed span |
| E003 | error | Span text differs from the text at the offsets |
| E004 | error | Span edge inside a grapheme cluster |
| E005 | error | Overlapping spans |
| E006 | error | Nested span while nesting is forbidden |
| E007 | error | Span edge inside a word or token |
| E008 | error | Clitic policy violation |
| E009 | error | Invalid tag or tag transition |
| E010 | error | Label not in the label set |
| E011 | error | Normalisation drift |
| E012 | error | Bidi or zero-width control at a span edge |
| E013 | error | Line-break shift (CRLF vs LF) |
| E014 | error | Offset unit mismatch |
| E015 | error | Offset not on a character boundary |
| E016 | error | Span edge between joined Arabic and Latin letters |
| E017 | error | Input is not valid UTF-8 |
| E018 | error | Byte order mark |
| E019 | error | Offset unit not declared |
| E020 | error | Input does not follow the input contract |
| W101 | warning | Whitespace at a span edge |
| W102 | warning | Punctuation at a span edge |
| I201 | note | Characters outside the Basic Multilingual Plane |
| I202 | note | Text changes length under normalisation |
| I203 | note | Offset unit hint |
| I204 | note | Clitic boundary with no declared policy |
| I205 | note | Tagging scheme not declared |

## Reports

The JSON report has a summary by code, the findings of each record, every span's offsets in all four units (`conversion_map`), the audit diff (`suggested_export`), `validator_version` and `settings_hash`. `--share` writes the same report without any text: record ids, codes, offsets, counts, version and settings hash only. `--csv` writes one row per finding.

## Quality checks

- Dev cases: 100 of 100 give exactly the expected codes and the expected repair suggestions (25 valid, 75 invalid, written before the validator code and frozen with SHA-256 checksums in `fixtures/FIXTURES.sha256`).
- Acceptance cases: 96 of 100 pass (26 valid, 74 invalid). The set was written separately from the category list, without the validator code or the dev cases. On the validator as frozen before the set was read, 86 of 100 passed; four fixes followed (string tokens in canonical records, a span that starts inside the definite article, punctuation that only the span text carries, and edge warnings kept when the span text is found elsewhere). The four cases that still fail are listed in `docs/QA.md`.
- spaCy agreement: on the 51 records of the valid cases that BILUO tags can express, our conversions agree with spaCy's `offsets_to_biluo_tags`, `biluo_tags_to_offsets`, `iob_to_biluo` and `biluo_to_iob` in 197 of 197 comparisons, and offsets to tags and back returns the same spans on 44 of 44 span records (4 records with nested spans are left out because BILUO cannot write them).
- Property tests: 10,000 generated Arabic records (words with harakat, tatweel, emoji, Latin names and the drift sequences below) go from offsets to IOB2, BIOES, BILUO, IOE2 and IOB1 tags and back unchanged and match spaCy's BILUO tags; 2,000 generated well-formed records give no error or warning. Tag transitions agree with seqeval's strict mode on 3,000 generated sequences.
- Drift inventory: every one of the 570 length-changing sequences (Unicode 16.0.0) is caught as normalisation drift (E011) by a generated test, and every reordered mark pair is caught in span texts.
- Browser port: the JavaScript port and the Python package give the same report on all 200 cases and on 18,000 random inputs (0 differences).

Details: [`docs/QA.md`](docs/QA.md).

## Offset conventions of common tools

Measured on 20 Arabic probe texts (harakat, tatweel, emoji, ZWNJ, RLM and ALM, CRLF, the lam-alef ligature, Arabic-Indic digits, a Latin name); Label Studio and doccano were read from their source code. Data and method: [`matrix/`](matrix/README.md).

| Tool | Version | Offset unit | CRLF counts as | Emoji (U+1F600) | How it was determined |
|---|---|---|---|---|---|
| Python str | CPython 3.14.7 | codepoint | 2 | U+1F600 counts 1 (probe p04 at 12-15) | measured |
| UTF-8 bytes | CPython 3.14.7 | utf8_byte | 2 | U+1F600 counts 4; an Arabic letter counts 2 (p04 at 23-29) | measured |
| JavaScript String | node 22.23.2 (V8 12.4.254.21-node.56) | utf16 | 2 | U+1F600 counts 2 (p04 at 13-16; code points 12-15) | measured |
| JavaScript String | chromium 156.0.8078.4 | utf16 | 2 | U+1F600 counts 2 (p04 at 13-16) | measured |
| regex \X grapheme clusters | regex 2026.9.29 | grapheme | 1 | U+1F600 counts 1; the ZWJ family emoji counts 1 (p05 at 11-18, code points 15-22) | measured |
| Intl.Segmenter grapheme clusters | node 22.23.2 (ICU 78.2, Unicode 17.0) | grapheme | 1 | as regex \X (p05 at 11-18) | measured |
| Intl.Segmenter grapheme clusters | chromium 156.0.8078.4 | grapheme | 1 | as regex \X (p05 at 11-18) | measured |
| spaCy Doc.char_span | spaCy 3.8.18 (blank 'ar' pipeline) | codepoint | 2 | U+1F600 counts 1 (p04 at 12-15) | measured |
| Hugging Face fast tokenizer offset_mapping | tokenizers 0.23.3, google-bert/bert-base-multilingual-cased@3f076fdb1ab6 | codepoint | 2 | U+1F600 counts 1 (p04 covered by 12-15) | measured |
| Hugging Face fast tokenizer offset_mapping | tokenizers 0.23.3, xlm-roberta-base@e73636d4f797 | codepoint | 2 | U+1F600 counts 1 (p04 covered by 12-15) | measured |
| Hugging Face fast tokenizer offset_mapping | tokenizers 0.23.3, aubmindlab/bert-base-arabertv02@016fb9d6768f | codepoint | 2 | U+1F600 counts 1 (p04 covered by 12-15) | measured |
| Label Studio | develop branch at commit 224dd4f78067 (latest release 1.23.2) | codepoint | 2 (carriage return and line feed are one position each) | U+1F600 counts 1 | from source code, not measured |
| doccano | master at commit ab6b765ea326 (latest release v1.8.5), v-annotator 0.1.28 at commit ab973f0ff806 | utf16 (default); grapheme when the project's grapheme mode is on | not determined from source | U+1F600 counts 2 by default, 1 in grapheme mode | from source code, not measured |

## Arabic drift inventory

[`inventory/`](inventory) lists every sequence in the Arabic blocks that NFC or NFKC changes, computed from the Unicode Character Database, versions 16.0.0 and 17.0.0, with a normaliser that passes `NormalizationTest.txt` of both versions: 4,679 rows for 16.0.0 (570 change length) and 4,859 for 17.0.0 (570 change length). Normalisation in the validator follows the Python runtime (`unicodedata`) or the browser (`String.prototype.normalize`); the report records which.

## Limitations

- Structural checks only: the validator does not judge whether a label is the right entity type.
- When a text was normalised after annotation and neither the text nor the span texts keep a trace of the change, the shift is reported (E003, E001 or edge errors) but the cause cannot be named.
- Clitic checks use orthographic rules (و ف ب ك ل and the article), not a lexicon: under `exclude`, a name whose own first letters look like a preposition and the article (بالتيمور, Baltimore) is read as بـ + الـ.
- Grapheme clusters follow the `regex` module in Python and `Intl.Segmenter` in the browser; both passed the same 766 cases of `GraphemeBreakTest.txt` 17.0.0 in our runs.

## Licence

Code: Apache-2.0 ([`LICENSE`](LICENSE)). Test cases, inventory, matrix and documentation: CC BY 4.0 ([`LICENSE-data`](LICENSE-data)). Data derived from the Unicode Character Database: Unicode License v3 ([`NOTICE`](NOTICE)). The web app's font, IBM Plex Sans Arabic: SIL OFL 1.1 (`web/fonts/OFL.txt`).

## Citation

See [`CITATION.cff`](CITATION.cff). Bayanat Labs (2026). Arabic NER Offset Validator, version 0.1.0. https://github.com/Bayanat-Labs/arabic-ner-validator

Questions and corrections: hello@bayanatlabs.com
