"""Tagging schemes: tag parsing, transition checks, and conversion between spans and tags.

Implemented independently of spaCy and seqeval; the tests compare the results with
spacy.training.offsets_to_biluo_tags / biluo_tags_to_offsets / iob_to_biluo / biluo_to_iob and with
seqeval's strict mode.
"""
from __future__ import annotations

SCHEMES = ("IO", "IOB1", "IOB2", "IOE1", "IOE2", "BIOES", "BILUO")
ALIASES = {"BIO": "IOB2", "IOB": "IOB2", "BILOU": "BILUO", "IOBES": "BIOES", "BIOLU": "BILUO"}
PREFIXES = {"IO": "I", "IOB1": "IB", "IOB2": "BI", "IOE1": "IE", "IOE2": "IE", "BIOES": "BIES", "BILUO": "BILU"}
# Role of each prefix letter: begin, inside, end, single.
ROLE = {"BIOES": {"B": "B", "I": "I", "E": "E", "S": "S"}, "BILUO": {"B": "B", "I": "I", "L": "E", "U": "S"}}


def parse_tag(tag):
    """('O', None) or (prefix, label); None if the tag cannot be read."""
    if not isinstance(tag, str):
        return None
    if tag == "O":
        return ("O", None)
    if len(tag) >= 3 and tag[1] == "-" and tag[0].isascii() and tag[0].isalpha() and tag[0].isupper():
        return (tag[0], tag[2:])
    return None


def check_tags(tags, scheme):
    """List of (index, kind, tag, prev) problems. kind: malformed, bad_prefix, transition, unfinished."""
    out = []
    allowed = PREFIXES[scheme]
    parsed = []
    for i, t in enumerate(tags):
        p = parse_tag(t)
        if p is None:
            out.append((i, "malformed", t, None))
            parsed.append(("O", None))
            continue
        if p[0] != "O" and p[0] not in allowed:
            out.append((i, "bad_prefix", t, None))
            parsed.append(("O", None))
            continue
        parsed.append(p)
    n = len(parsed)
    if scheme in ("BIOES", "BILUO"):
        role = ROLE[scheme]
        inside = None  # label of the open entity
        prev_tag = None
        for i, (p, lab) in enumerate(parsed):
            r = role.get(p) if p != "O" else "O"
            if inside is not None:
                if r in ("I", "E") and lab == inside:
                    if r == "E":
                        inside = None
                else:
                    kind = "unfinished" if r in ("O", "B", "S") else "transition"
                    out.append((i, kind, tags[i], prev_tag))
                    inside = lab if r in ("B", "I") else None
            else:
                if r in ("I", "E"):
                    out.append((i, "transition", tags[i], prev_tag if prev_tag is not None else "the start"))
                    inside = lab if r == "I" else None
                elif r == "B":
                    inside = lab
            prev_tag = tags[i]
        if inside is not None and n:
            out.append((n - 1, "unfinished", "the end", tags[n - 1]))
    elif scheme == "IOB2":
        prev = ("O", None)
        for i, (p, lab) in enumerate(parsed):
            if p == "I" and not (prev[0] in ("B", "I") and prev[1] == lab):
                out.append((i, "transition", tags[i], tags[i - 1] if i else "the start"))
            prev = (p, lab)
    elif scheme == "IOB1":
        prev = ("O", None)
        for i, (p, lab) in enumerate(parsed):
            if p == "B" and not (prev[0] in ("B", "I") and prev[1] == lab):
                out.append((i, "transition", tags[i], tags[i - 1] if i else "the start"))
            prev = (p, lab)
    elif scheme == "IOE2":
        for i, (p, lab) in enumerate(parsed):
            if p == "I":
                nxt = parsed[i + 1] if i + 1 < n else ("O", None)
                if not (nxt[0] in ("I", "E") and nxt[1] == lab):
                    out.append((i + 1 if i + 1 < n else i, "unfinished", tags[i + 1] if i + 1 < n else "the end", tags[i]))
    elif scheme == "IOE1":
        for i, (p, lab) in enumerate(parsed):
            if p == "E":
                nxt = parsed[i + 1] if i + 1 < n else ("O", None)
                if not (nxt[0] in ("I", "E") and nxt[1] == lab):
                    out.append((i, "transition", tags[i], tags[i - 1] if i else "the start"))
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def tags_to_entities(tags, scheme):
    """Lenient reading of a tag sequence: list of (first_token, last_token_inclusive, label)."""
    ents = []
    cur = None  # [start, end, label]

    def close():
        nonlocal cur
        if cur is not None:
            ents.append(tuple(cur))
            cur = None

    role = ROLE.get(scheme)
    for i, t in enumerate(tags):
        p = parse_tag(t)
        if p is None or p[0] == "O" or p[0] not in PREFIXES[scheme]:
            close()
            continue
        pre, lab = p
        if scheme == "IO":
            if cur is not None and cur[2] == lab:
                cur[1] = i
            else:
                close()
                cur = [i, i, lab]
        elif scheme in ("IOB1", "IOB2"):
            if pre == "B":
                close()
                cur = [i, i, lab]
            elif cur is not None and cur[2] == lab:
                cur[1] = i
            else:
                close()
                cur = [i, i, lab]
        elif scheme in ("IOE1", "IOE2"):
            if cur is not None and cur[2] == lab:
                cur[1] = i
            else:
                close()
                cur = [i, i, lab]
            if pre == "E":
                close()
        else:
            r = role[pre]
            if r == "B":
                close()
                cur = [i, i, lab]
            elif r == "I":
                if cur is not None and cur[2] == lab:
                    cur[1] = i
                else:
                    close()
                    cur = [i, i, lab]
            elif r == "E":
                if cur is not None and cur[2] == lab:
                    cur[1] = i
                else:
                    close()
                    cur = [i, i, lab]
                close()
            else:
                close()
                ents.append((i, i, lab))
    close()
    return ents


def entities_to_tags(n_tokens, entities, scheme):
    """Tags for (first_token, last_token_inclusive, label) entities that do not overlap."""
    tags = ["O"] * n_tokens
    ents = sorted(entities)
    for k, (a, b, lab) in enumerate(ents):
        if any(tags[i] != "O" for i in range(a, b + 1)):
            raise ValueError("overlapping entities")
        prev_same = k > 0 and ents[k - 1][1] == a - 1 and ents[k - 1][2] == lab
        nxt_same = k + 1 < len(ents) and ents[k + 1][0] == b + 1 and ents[k + 1][2] == lab
        for i in range(a, b + 1):
            if scheme == "IO":
                tags[i] = "I-" + lab
            elif scheme == "IOB2":
                tags[i] = ("B-" if i == a else "I-") + lab
            elif scheme == "IOB1":
                tags[i] = ("B-" if i == a and prev_same else "I-") + lab
            elif scheme == "IOE2":
                tags[i] = ("E-" if i == b else "I-") + lab
            elif scheme == "IOE1":
                tags[i] = ("E-" if i == b and nxt_same else "I-") + lab
            elif scheme == "BIOES":
                tags[i] = ("S-" if a == b else "B-" if i == a else "E-" if i == b else "I-") + lab
            elif scheme == "BILUO":
                tags[i] = ("U-" if a == b else "B-" if i == a else "L-" if i == b else "I-") + lab
    return tags


def spans_to_entities(tokens, spans):
    """Token entities for character spans; tokens are (start, end) pairs. Raises ValueError when a
    span edge is not on a token edge."""
    starts = {s: i for i, (s, _) in enumerate(tokens)}
    ends = {e: i for i, (_, e) in enumerate(tokens)}
    out = []
    for s, e, lab in spans:
        if s not in starts or e not in ends:
            raise ValueError("misaligned span")
        out.append((starts[s], ends[e], lab))
    return out


def offsets_to_tags(tokens, spans, scheme):
    return entities_to_tags(len(tokens), spans_to_entities(tokens, spans), scheme)


def tags_to_offsets(tokens, tags, scheme):
    return [(tokens[a][0], tokens[b][1], lab) for a, b, lab in tags_to_entities(tags, scheme)]


def convert_tags(tags, src, dst):
    """Re-encode a well-formed tag sequence from one scheme to another."""
    return entities_to_tags(len(tags), tags_to_entities(tags, src), dst)


def iob_to_biluo(tags):
    return convert_tags(tags, "IOB2", "BILUO")


def biluo_to_iob(tags):
    return convert_tags(tags, "BILUO", "IOB2")
