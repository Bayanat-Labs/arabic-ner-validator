# Offset conventions on Arabic text

The same entity in 20 Arabic probe texts ([`probes.py`](probes.py)), located by each tool or unit. 11 rows were measured on 2026-10-30; 2 rows (Label Studio, doccano) were read from the tools' source code at a pinned commit and were not measured.

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

Per-probe offsets: [`probe_measurements.csv`](probe_measurements.csv). Raw measurements: [`evidence/`](evidence) (SHA-256 in `offset_conventions.csv`); source references with commit, file, lines and file hashes: [`evidence/source_references.json`](evidence/source_references.json).

What the probes show:

- Python `str`, spaCy and the Hugging Face fast tokenizers count code points; JavaScript (Node and Chromium) counts UTF-16 units. They differ only after a character outside the BMP: the emoji probes.
- Grapheme clusters count a letter with its harakat, the CRLF pair and a ZWJ emoji sequence as one unit; `regex` \X and `Intl.Segmenter` agreed on every probe.
- The tokenizers normalise internally (NFKC in xlm-roberta-base; control characters dropped by the BERT normalisers) but their offsets still point into the original text.
- spaCy's blank Arabic tokenizer keeps a bidi mark or an attached conjunction in the same token as the name, so `Doc.char_span` in `strict` and `contract` modes returns nothing for such spans and `expand` widens them.
- Label Studio's text regions count code points (its own tests say so); doccano counts UTF-16 units unless a project switches on grapheme mode.

Reproduce: `python matrix/measure.py TOKENIZERS_JSON`, `node matrix/measure_node.mjs`, `python matrix/measure_browser.py` (Playwright), then `python matrix/build_matrix.py`.
