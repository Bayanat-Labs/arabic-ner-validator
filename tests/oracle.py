"""Helpers shared by the spaCy and seqeval oracle tests and the QA scripts."""
from spacy.tokens import Doc
from spacy.training import biluo_tags_to_offsets, biluo_to_iob, iob_to_biluo, offsets_to_biluo_tags
from spacy.vocab import Vocab

from arabic_ner_validator.convert import convert_tags, offsets_to_tags, tags_to_offsets
from arabic_ner_validator.tokenize import tokenize

VOCAB = Vocab()


def doc_for(text, tokens):
    """spaCy Doc whose tokens are `tokens` (code point pairs) plus whitespace tokens for the gaps."""
    words, spaces, toks = [], [], []
    pos = 0
    pairs = sorted(tokens)

    def gap(a, b):
        g = text[a:b]
        if not g:
            return
        if words and spaces[-1] is False and g == " ":
            spaces[-1] = True
            return
        if words and spaces[-1] is False and g.startswith(" ") and len(g) > 1:
            spaces[-1] = True
            g = g[1:]
            a += 1
        words.append(g)
        spaces.append(False)
        toks.append((a, a + len(g)))

    for s, e in pairs:
        gap(pos, s)
        words.append(text[s:e])
        spaces.append(False)
        toks.append((s, e))
        pos = e
    gap(pos, len(text))
    doc = Doc(VOCAB, words=words, spaces=spaces)
    assert doc.text == text
    return doc, [(t.idx, t.idx + len(t.text)) for t in doc]


def refine(text, tokens, spans):
    """Split tokens at span edges so that every span edge is a token edge."""
    cuts = {s for s, _, _ in spans} | {e for _, e, _ in spans}
    out = []
    for a, b in tokens:
        pts = [a] + sorted(c for c in cuts if a < c < b) + [b]
        out += [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    return out


def compare_record(text, spans, tokens=None):
    """Compare our conversions with spaCy on one record. Returns a dict of booleans."""
    toks = refine(text, tokens if tokens is not None else tokenize(text), spans)
    doc, dtoks = doc_for(text, toks)
    ents = [(s, e, lab) for s, e, lab in spans]
    sp_biluo = offsets_to_biluo_tags(doc, ents)
    ours_biluo = offsets_to_tags(dtoks, ents, "BILUO")
    res = {"offsets_to_biluo": sp_biluo == ours_biluo}
    res["biluo_to_offsets"] = sorted(biluo_tags_to_offsets(doc, sp_biluo)) == sorted(tags_to_offsets(dtoks, ours_biluo, "BILUO"))
    iob = offsets_to_tags(dtoks, ents, "IOB2")
    res["iob_to_biluo"] = iob_to_biluo(iob) == convert_tags(iob, "IOB2", "BILUO")
    res["biluo_to_iob"] = biluo_to_iob(ours_biluo) == convert_tags(ours_biluo, "BILUO", "IOB2")
    res["round_trip"] = sorted(tags_to_offsets(dtoks, ours_biluo, "BILUO")) == sorted(ents)
    return res


def compare_tags(text, tokens, tags, scheme):
    """Token formats: compare tag conversions with spaCy."""
    doc, dtoks = doc_for(text, tokens)
    if scheme == "BIOES":
        biluo_src = [t if t == "O" else {"B": "B", "I": "I", "E": "L", "S": "U"}[t[0]] + t[1:] for t in tags]
    elif scheme == "BILUO":
        biluo_src = list(tags)
    else:
        biluo_src = iob_to_biluo(tags)
    ours = convert_tags(tags, scheme, "BILUO")
    res = {"iob_to_biluo": ours == biluo_src}
    res["biluo_to_offsets"] = sorted(biluo_tags_to_offsets(doc, ours)) == sorted(
        (s, e, lab) for s, e, lab in tags_to_offsets(dtoks, ours, "BILUO"))
    res["offsets_to_biluo"] = offsets_to_biluo_tags(doc, tags_to_offsets(dtoks, ours, "BILUO")) == ours
    return res
