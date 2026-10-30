# Changelog

## 0.1.0 (2026-10-30)

First release.

- Python package and command-line tool `arabic-ner-validator` (6 input formats, 27 finding codes with English and Arabic messages, JSON, shareable JSON and CSV reports, audit diff and `--apply-suggestions`).
- JSON Schema 2020-12 of the canonical record and 20 rejected examples.
- 100 dev and 100 acceptance test cases (CC BY 4.0).
- Arabic drift inventory for Unicode 16.0.0 and 17.0.0, offset-convention matrix, browser port.
- Changes after the acceptance set was first run (no test case edited): canonical `tokens` may be strings; E008 kind `article_split` for a span that starts inside the definite article; W102, W101 and E012 kind `span_text` when only the span text carries the edge character; edge warnings are kept and edge repairs preferred when the span text is found elsewhere.
