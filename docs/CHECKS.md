# Checks

Every offset is converted from the declared unit to code points. An offset that falls outside the text is E001; one that falls inside a UTF-8 byte sequence or a UTF-16 surrogate pair is E015; a span whose start equals or follows its end is E002.

## Content of a span

For a span [s, e) on the text:

- E002 when it contains no letter or digit.
- E003 when a span text is given and differs from `text[s:e]`.
- E004 when s or e falls inside an extended grapheme cluster, for example between a letter and its haraka, shadda or combining hamza.
- E012 when a bidi control or zero-width character (U+061C, U+200B to U+200F, U+202A to U+202E, U+2060, U+2066 to U+2069, U+FEFF, U+00AD) is at an edge; W101 for whitespace at an edge; W102 for punctuation at an edge (percent signs, and a full stop after a Latin letter, are not counted).
- E007 when an edge falls inside a word (letters, marks, digits) or, when tokens are given, inside a token; E016 instead when that point joins Arabic and Latin letters.
- E008 when the clitic policy is broken: under `include` the span leaves out a proclitic (و ف ب ك ل, the article) attached to the word; under `exclude` it starts with a conjunction or preposition fused with the article (وال، بال، كال، فال، لل) or with an Arabic proclitic attached to a Latin name, or it leaves out the article, or starts inside it. Under `unspecified` a span that starts after a proclitic gets the note I204.

## Drift

When a span does not fit (its span text differs, or without span text it has an edge error), the validator reads the same offsets in other ways:

1. in the other units (code points, UTF-16 units, UTF-8 bytes, and grapheme clusters last);
2. on the text after CRLF to LF, LF to CRLF, removing a leading U+FEFF, adding a byte order mark (when the file had one), NFC, NFKC, tatweel removal and diacritic removal, each with an exact map back to the text.

A reading fits when the span text then matches, or, without span text, when the span then has no edge error (UTF-8 and grapheme readings are only tried this way when an offset is out of range or inside a character). If every reading that fits gives the same span, the first one names the cause (E014 unit, E013 line breaks, E018 byte order mark, E011 normalisation) and its offsets become the suggestion; the others are listed under `also_fits`. If readings disagree, the span stays an error with no suggestion. If none fits, the span text is searched in the text as it is and after each normalisation; one match gives a suggestion (E011 when a normalisation was needed).

When the offsets are right but the span text differs only by normalisation, the code is E011 (or E013 for line breaks) with kind `span_text_form`; when it differs only by punctuation, whitespace or a control character at an edge, those characters are reported (W102, W101, E012 with kind `span_text`).

## Records

- E005 for crossing or duplicate spans; E006 for a span inside another (or two labels on one extent) under `nested_policy: forbid`.
- E009 for tags that cannot be read, that use a prefix the scheme does not have, or that break its transitions; E010 for labels outside `label_set`.
- E011 (kind `declared_form`) when the text is not in the declared normalisation form; E018 when the file or the text starts with a byte order mark; E019 when no offset unit is declared (with a hint of which unit fits); E020 when a record does not follow the input contract; E017 when the file is not valid UTF-8.
- Notes: I201 characters outside the BMP, I202 text that changes length under NFC or NFKC, I203 a unit that fits more spans than the declared one, I205 a tag scheme read from the prefixes because none was declared.

## Repairs

At most one suggestion per span, in the declared unit: the drift reading when one fits; otherwise edge repairs in this order: clitic policy, trimming controls, whitespace and punctuation, completing a grapheme cluster, extending to the word or token edge; a reversed span is swapped. Each suggestion has a confidence (high, medium, low). `--apply-suggestions OUT` writes a copy with those offsets (medium and high by default); labels, ids and text are not changed, and a byte order mark at the start of the file is dropped.

## Codes

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
