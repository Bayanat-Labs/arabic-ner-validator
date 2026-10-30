// arabic-ner-validator, browser and Node port of the Python package (same checks, same reports).
// Apache-2.0. No network access, no storage. Text is handled as arrays of code points.
import { CODES } from "./codes.js";

export const VERSION = "0.1.0";

// ------------------------------------------------------------------ character classes
const RX = {
  word: /^[\p{L}\p{M}\p{Nd}\p{Pc}]$/u,
  letter: /^\p{L}$/u,
  alnum: /^[\p{L}\p{N}]$/u,
  mark: /^\p{M}$/u,
  punct: /^\p{P}$/u,
  arabic: /^\p{Script=Arabic}$/u,
  latin: /^\p{Script=Latin}$/u,
};
const cset = (list) => new Set(list.map((c) => String.fromCodePoint(c)));
const range = (a, b) => { const o = []; for (let c = a; c <= b; c++) o.push(c); return o; };
const WHITESPACE = cset([0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x20, 0x85, 0xa0, 0x1680, ...range(0x2000, 0x200a), 0x2028, 0x2029, 0x202f, 0x205f, 0x3000]);
const CONTROLS = cset([0x00ad, 0x061c, 0x200b, 0x200c, 0x200d, 0x200e, 0x200f, 0x202a, 0x202b, 0x202c, 0x202d, 0x202e, 0x2060, 0x2066, 0x2067, 0x2068, 0x2069, 0xfeff]);
const PUNCT_EXEMPT = new Set(["%", "٪", "‰", "؉", "؊"]);
const TATWEEL = "ـ";
const BOM = "﻿";
const DIACRITICS = cset([...range(0x0610, 0x061a), ...range(0x064b, 0x0652), ...range(0x0656, 0x065f), 0x0670, ...range(0x06d6, 0x06dc), ...range(0x06df, 0x06e4), ...range(0x06e7, 0x06e8), ...range(0x06ea, 0x06ed)]);

const isWord = (ch) => RX.word.test(ch);
const isLetter = (ch) => RX.letter.test(ch);
const isAlnum = (ch) => RX.alnum.test(ch);
const isMark = (ch) => RX.mark.test(ch);
const isWs = (ch) => WHITESPACE.has(ch);
const isControl = (ch) => CONTROLS.has(ch);
const isPunct = (ch) => RX.punct.test(ch);
const isArabicLetter = (ch) => RX.letter.test(ch) && RX.arabic.test(ch) && ch !== TATWEEL;
const isLatinLetter = (ch) => RX.letter.test(ch) && RX.latin.test(ch);
const scriptOf = (ch) => (isArabicLetter(ch) ? "Arabic" : isLatinLetter(ch) ? "Latin" : null);
const uplus = (ch) => "U+" + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, "0");
const cpsOf = (s) => Array.from(s);
const join = (a) => a.join("");

let SEG = null;
function graphemeBoundaries(cps) {
  if (!cps.length) return [0];
  if (!SEG) SEG = new Intl.Segmenter("und", { granularity: "grapheme" });
  const out = [];
  let pos = 0;
  for (const g of SEG.segment(join(cps))) {
    out.push(pos);
    pos += Array.from(g.segment).length;
  }
  out.push(pos);
  return out;
}

// ------------------------------------------------------------------ offsets
const UNITS = ["codepoint", "utf16", "utf8_byte", "grapheme"];

class OffsetMap {
  constructor(cps) {
    this.cps = cps;
    this.n = cps.length;
    const u16 = [0], u8 = [0];
    for (const ch of cps) {
      const o = ch.codePointAt(0);
      u16.push(u16[u16.length - 1] + (o > 0xffff ? 2 : 1));
      u8.push(u8[u8.length - 1] + (o < 0x80 ? 1 : o < 0x800 ? 2 : o < 0x10000 ? 3 : 4));
    }
    this.u16 = u16;
    this.u8 = u8;
    this.gb = graphemeBoundaries(cps);
    this.gbSet = new Set(this.gb);
    this.gbIndex = new Map(this.gb.map((v, i) => [v, i]));
    this.inv = { utf16: new Map(u16.map((v, i) => [v, i])), utf8_byte: new Map(u8.map((v, i) => [v, i])) };
  }
  total(unit) {
    if (unit === "codepoint") return this.n;
    if (unit === "utf16") return this.u16[this.u16.length - 1];
    if (unit === "utf8_byte") return this.u8[this.u8.length - 1];
    return this.gb.length - 1;
  }
  toCp(value, unit) {
    if (value < 0 || value > this.total(unit)) return [null, "range"];
    if (unit === "codepoint") return [value, null];
    if (unit === "grapheme") return [this.gb[value], null];
    const cp = this.inv[unit].get(value);
    if (cp === undefined) return [null, "mid"];
    return [cp, null];
  }
  fromCp(cp, unit) {
    if (unit === "codepoint") return cp;
    if (unit === "utf16") return this.u16[cp];
    if (unit === "utf8_byte") return this.u8[cp];
    return this.gbIndex.has(cp) ? this.gbIndex.get(cp) : null;
  }
  convert(s, e) {
    const o = {};
    for (const u of UNITS) o[u] = [this.fromCp(s, u), this.fromCp(e, u)];
    return o;
  }
  clusterOf(cp) {
    let i = 0;
    while (i + 1 < this.gb.length && this.gb[i + 1] <= cp) i++;
    return [this.gb[i], this.gb[i + 1]];
  }
}

class Reading {
  constructor(name, cps, startMap, endMap) {
    this.name = name;
    this.cps = cps;
    this.startMap = startMap;
    this.endMap = endMap;
    this._omap = null;
  }
  get omap() {
    if (!this._omap) this._omap = new OffsetMap(this.cps);
    return this._omap;
  }
}

const norm = (s, f) => s.normalize(f);

function normReading(cps, form) {
  const text = join(cps);
  const t = norm(text, form);
  if (t === text) return null;
  const gb = graphemeBoundaries(cps);
  const chunks = [];
  for (let i = 0; i + 1 < gb.length; i++) chunks.push(join(cps.slice(gb[i], gb[i + 1])));
  let merged = [];
  for (const c of chunks) {
    if (merged.length && norm(merged[merged.length - 1] + c, form) !== norm(merged[merged.length - 1], form) + norm(c, form)) {
      merged[merged.length - 1] += c;
    } else merged.push(c);
  }
  if (merged.map((c) => norm(c, form)).join("") !== t) merged = [text];
  const sm = [], em = [];
  let a = 0;
  for (const c of merged) {
    const nc = norm(c, form);
    const cl = cpsOf(c).length;
    if (nc === c) {
      for (let k = 0; k < cl; k++) { sm.push(a + k); em.push(a + k); }
    } else {
      sm.push(a); em.push(a);
      const nl = cpsOf(nc).length;
      for (let k = 0; k < nl - 1; k++) { sm.push(null); em.push(null); }
    }
    a += cl;
  }
  sm.push(a); em.push(a);
  return new Reading(form, cpsOf(t), sm, em);
}

function removalReading(name, cps, remove, extendEnd) {
  const kept = [];
  for (let i = 0; i < cps.length; i++) if (!remove(i, cps[i])) kept.push(i);
  if (kept.length === cps.length) return null;
  const t = kept.map((i) => cps[i]);
  const n = cps.length;
  const sm = [], em = [0];
  for (let p = 0; p <= kept.length; p++) sm.push(p < kept.length ? kept[p] : n);
  for (let p = 1; p <= kept.length; p++) {
    let q = kept[p - 1] + 1;
    if (extendEnd) while (q < n && remove(q, cps[q])) q++;
    em.push(q);
  }
  return new Reading(name, t, sm, em);
}

function lfToCrlf(cps) {
  const out = [], sm = [], em = [];
  let changed = false;
  for (let i = 0; i < cps.length; i++) {
    if (cps[i] === "\n" && (i === 0 || cps[i - 1] !== "\r")) {
      out.push("\r", "\n"); sm.push(i, null); em.push(i, null); changed = true;
    } else { out.push(cps[i]); sm.push(i); em.push(i); }
  }
  if (!changed) return null;
  sm.push(cps.length); em.push(cps.length);
  return new Reading("lf_to_crlf", out, sm, em);
}

function makeReading(cps, name, fileBom) {
  if (name === "NFC" || name === "NFKC") return normReading(cps, name);
  if (name === "remove_tatweel") return removalReading(name, cps, (i, ch) => ch === TATWEEL, false);
  if (name === "remove_diacritics") return removalReading(name, cps, (i, ch) => DIACRITICS.has(ch), true);
  if (name === "crlf_to_lf") return removalReading(name, cps, (i, ch) => ch === "\r" && i + 1 < cps.length && cps[i + 1] === "\n", false);
  if (name === "lf_to_crlf") return lfToCrlf(cps);
  if (name === "strip_bom") return cps[0] === BOM ? removalReading(name, cps, (i) => i === 0, false) : null;
  if (name === "add_bom") {
    if (!fileBom || cps[0] === BOM) return null;
    const r = [0];
    for (let i = 0; i <= cps.length; i++) r.push(i);
    return new Reading("add_bom", [BOM, ...cps], r, r.slice());
  }
  throw new Error(name);
}

function applyPolicy(s, policy) {
  if (policy === "NFC" || policy === "NFKC") return norm(s, policy);
  if (policy === "remove_tatweel") return s.split(TATWEEL).join("");
  if (policy === "remove_diacritics") return cpsOf(s).filter((ch) => !DIACRITICS.has(ch)).join("");
  if (policy === "crlf_to_lf") return s.split("\r\n").join("\n");
  throw new Error(policy);
}

// ------------------------------------------------------------------ tags
const SCHEMES = ["IO", "IOB1", "IOB2", "IOE1", "IOE2", "BIOES", "BILUO"];
const ALIASES = { BIO: "IOB2", IOB: "IOB2", BILOU: "BILUO", IOBES: "BIOES", BIOLU: "BILUO" };
const PREFIXES = { IO: "I", IOB1: "IB", IOB2: "BI", IOE1: "IE", IOE2: "IE", BIOES: "BIES", BILUO: "BILU" };
const ROLE = { BIOES: { B: "B", I: "I", E: "E", S: "S" }, BILUO: { B: "B", I: "I", L: "E", U: "S" } };

function parseTag(tag) {
  if (typeof tag !== "string") return null;
  if (tag === "O") return ["O", null];
  if (tag.length >= 3 && tag[1] === "-" && /^[A-Z]$/.test(tag[0])) return [tag[0], tag.slice(2)];
  return null;
}

export function checkTags(tags, scheme) {
  const out = [];
  const allowed = PREFIXES[scheme];
  const parsed = [];
  tags.forEach((t, i) => {
    const p = parseTag(t);
    if (p === null) { out.push([i, "malformed", t, null]); parsed.push(["O", null]); return; }
    if (p[0] !== "O" && !allowed.includes(p[0])) { out.push([i, "bad_prefix", t, null]); parsed.push(["O", null]); return; }
    parsed.push(p);
  });
  const n = parsed.length;
  if (scheme === "BIOES" || scheme === "BILUO") {
    const role = ROLE[scheme];
    let inside = null, prevTag = null;
    parsed.forEach(([p, lab], i) => {
      const r = p !== "O" ? role[p] : "O";
      if (inside !== null) {
        if ((r === "I" || r === "E") && lab === inside) {
          if (r === "E") inside = null;
        } else {
          const kind = r === "O" || r === "B" || r === "S" ? "unfinished" : "transition";
          out.push([i, kind, tags[i], prevTag]);
          inside = r === "B" || r === "I" ? lab : null;
        }
      } else if (r === "I" || r === "E") {
        out.push([i, "transition", tags[i], prevTag !== null ? prevTag : "the start"]);
        inside = r === "I" ? lab : null;
      } else if (r === "B") inside = lab;
      prevTag = tags[i];
    });
    if (inside !== null && n) out.push([n - 1, "unfinished", "the end", tags[n - 1]]);
  } else if (scheme === "IOB2") {
    let prev = ["O", null];
    parsed.forEach(([p, lab], i) => {
      if (p === "I" && !((prev[0] === "B" || prev[0] === "I") && prev[1] === lab)) out.push([i, "transition", tags[i], i ? tags[i - 1] : "the start"]);
      prev = [p, lab];
    });
  } else if (scheme === "IOB1") {
    let prev = ["O", null];
    parsed.forEach(([p, lab], i) => {
      if (p === "B" && !((prev[0] === "B" || prev[0] === "I") && prev[1] === lab)) out.push([i, "transition", tags[i], i ? tags[i - 1] : "the start"]);
      prev = [p, lab];
    });
  } else if (scheme === "IOE2") {
    parsed.forEach(([p, lab], i) => {
      if (p === "I") {
        const nx = i + 1 < n ? parsed[i + 1] : ["O", null];
        if (!((nx[0] === "I" || nx[0] === "E") && nx[1] === lab)) out.push([i + 1 < n ? i + 1 : i, "unfinished", i + 1 < n ? tags[i + 1] : "the end", tags[i]]);
      }
    });
  } else if (scheme === "IOE1") {
    parsed.forEach(([p, lab], i) => {
      if (p === "E") {
        const nx = i + 1 < n ? parsed[i + 1] : ["O", null];
        if (!((nx[0] === "I" || nx[0] === "E") && nx[1] === lab)) out.push([i, "transition", tags[i], i ? tags[i - 1] : "the start"]);
      }
    });
  }
  out.sort((a, b) => (a[0] - b[0]) || (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0));
  return out;
}

export function tagsToEntities(tags, scheme) {
  const ents = [];
  let cur = null;
  const close = () => { if (cur !== null) { ents.push(cur); cur = null; } };
  const role = ROLE[scheme];
  tags.forEach((t, i) => {
    const p = parseTag(t);
    if (p === null || p[0] === "O" || !PREFIXES[scheme].includes(p[0])) { close(); return; }
    const [pre, lab] = p;
    if (scheme === "IO") {
      if (cur !== null && cur[2] === lab) cur[1] = i; else { close(); cur = [i, i, lab]; }
    } else if (scheme === "IOB1" || scheme === "IOB2") {
      if (pre === "B") { close(); cur = [i, i, lab]; } else if (cur !== null && cur[2] === lab) cur[1] = i; else { close(); cur = [i, i, lab]; }
    } else if (scheme === "IOE1" || scheme === "IOE2") {
      if (cur !== null && cur[2] === lab) cur[1] = i; else { close(); cur = [i, i, lab]; }
      if (pre === "E") close();
    } else {
      const r = role[pre];
      if (r === "B") { close(); cur = [i, i, lab]; }
      else if (r === "I") { if (cur !== null && cur[2] === lab) cur[1] = i; else { close(); cur = [i, i, lab]; } }
      else if (r === "E") { if (cur !== null && cur[2] === lab) cur[1] = i; else { close(); cur = [i, i, lab]; } close(); }
      else { close(); ents.push([i, i, lab]); }
    }
  });
  close();
  return ents;
}

// ------------------------------------------------------------------ contract
const KEYS = ["id", "text", "offset_unit", "normalization_declared", "scheme", "label_set", "nested_policy", "clitic_policy", "spans", "tokens", "tags"];
const CUNITS = ["utf8_byte", "codepoint", "utf16", "grapheme"];
const NORM_RX = /^(none|NFC|NFKC|NFD|NFKD|policy:[A-Za-z0-9._-]+)$/;
const isInt = (v) => typeof v === "number" && Number.isInteger(v);
const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

function checkCanonical(obj) {
  const out = [];
  if (!isObj(obj)) return [["$", "must be an object"]];
  for (const k of Object.keys(obj)) if (!KEYS.includes(k)) out.push([k, "is not an allowed property"]);
  if (has(obj, "id") && !(typeof obj.id === "string" || isInt(obj.id))) out.push(["id", "must be a string or an integer"]);
  if (!has(obj, "text")) out.push(["text", "is required"]);
  else if (typeof obj.text !== "string") out.push(["text", "must be a string"]);
  if (has(obj, "offset_unit") && !CUNITS.includes(obj.offset_unit)) out.push(["offset_unit", "must be one of utf8_byte, codepoint, utf16, grapheme"]);
  if (has(obj, "normalization_declared") && !(typeof obj.normalization_declared === "string" && NORM_RX.test(obj.normalization_declared))) out.push(["normalization_declared", "must be none, NFC, NFKC, NFD, NFKD or policy:<id>"]);
  if (has(obj, "scheme") && !SCHEMES.includes(obj.scheme)) out.push(["scheme", "must be one of IO, IOB1, IOB2, IOE1, IOE2, BIOES, BILUO"]);
  if (has(obj, "label_set")) {
    const ls = obj.label_set;
    if (!Array.isArray(ls) || !ls.every((x) => typeof x === "string" && x)) out.push(["label_set", "must be an array of non-empty strings"]);
    else if (new Set(ls).size !== ls.length) out.push(["label_set", "must not repeat a label"]);
  }
  if (has(obj, "nested_policy") && !["forbid", "allow"].includes(obj.nested_policy)) out.push(["nested_policy", "must be forbid or allow"]);
  if (has(obj, "clitic_policy") && !["include", "exclude", "unspecified"].includes(obj.clitic_policy)) out.push(["clitic_policy", "must be include, exclude or unspecified"]);
  if (!has(obj, "spans")) out.push(["spans", "is required"]);
  else if (!Array.isArray(obj.spans)) out.push(["spans", "must be an array"]);
  else obj.spans.forEach((sp, i) => {
    const p = `spans[${i}]`;
    if (!isObj(sp)) { out.push([p, "must be an object"]); return; }
    for (const k of Object.keys(sp)) if (!["start", "end", "label", "text"].includes(k)) out.push([p + "." + k, "is not an allowed property"]);
    for (const k of ["start", "end"]) {
      if (!has(sp, k)) out.push([p + "." + k, "is required"]);
      else if (!isInt(sp[k])) out.push([p + "." + k, "must be an integer"]);
    }
    if (!has(sp, "label")) out.push([p + ".label", "is required"]);
    else if (typeof sp.label !== "string" || !sp.label) out.push([p + ".label", "must be a non-empty string"]);
    if (has(sp, "text") && typeof sp.text !== "string") out.push([p + ".text", "must be a string"]);
  });
  if (has(obj, "tokens")) {
    const toks = obj.tokens;
    if (!Array.isArray(toks)) out.push(["tokens", "must be an array"]);
    else toks.forEach((t, i) => {
      const p = `tokens[${i}]`;
      if (typeof t === "string") return;
      if (!isObj(t)) { out.push([p, "must be a string or an object"]); return; }
      for (const k of Object.keys(t)) if (!["start", "end", "text"].includes(k)) out.push([p + "." + k, "is not an allowed property"]);
      for (const k of ["start", "end"]) {
        if (!has(t, k)) out.push([p + "." + k, "is required"]);
        else if (!isInt(t[k])) out.push([p + "." + k, "must be an integer"]);
      }
      if (has(t, "text") && typeof t.text !== "string") out.push([p + ".text", "must be a string"]);
    });
  }
  if (has(obj, "tags")) {
    const tags = obj.tags;
    if (!Array.isArray(tags) || !tags.every((x) => typeof x === "string")) out.push(["tags", "must be an array of strings"]);
    if (!has(obj, "tokens")) out.push(["tags", "needs tokens"]);
    else if (Array.isArray(tags) && Array.isArray(obj.tokens) && tags.length !== obj.tokens.length) out.push(["tags", "must have as many items as tokens"]);
  }
  return out;
}

// ------------------------------------------------------------------ adapters
export const FORMATS = ["canonical", "doccano", "label_studio", "spacy", "conll", "hf_tokens"];

function newRecord(id, line) {
  return { id, line, text: "", offset_unit: null, normalization_declared: "none", scheme: null, label_set: null,
    nested_policy: "forbid", clitic_policy: "unspecified", spans: [], tokens: null, tags: null, from_tokens: false,
    problems: [], source: null, span_refs: [], task_index: null, tokens_cp: null };
}

function lines(text) {
  return text.split("\n").map((ln, i) => [i + 1, ln.endsWith("\r") ? ln.slice(0, -1) : ln]);
}
const blank = (s) => s.replace(/^[ \t]+|[ \t]+$/g, "") === "";

function parseJson(s) {
  try { return [JSON.parse(s), null]; } catch (e) { return [undefined, "is not valid JSON"]; }
}

function jsonLines(text) {
  const out = [];
  for (const [i, ln] of lines(text)) {
    if (blank(ln)) continue;
    const [v, err] = parseJson(ln);
    out.push([i, err ? null : v, err]);
  }
  return out;
}

function rid(obj, line) {
  if (isObj(obj) && has(obj, "id") && (typeof obj.id === "string" || isInt(obj.id))) return typeof obj.id === "string" ? obj.id : String(obj.id);
  return "L" + line;
}

export function detectFormat(text) {
  const s = text.replace(/^[﻿ \t\r\n]+/, "");
  if (!s) return "canonical";
  if (s[0] !== "[" && s[0] !== "{") return "conll";
  if (s[0] === "[") {
    const [v] = parseJson(s);
    if (Array.isArray(v) && v.length && isObj(v[0])) {
      if (has(v[0], "data") || has(v[0], "annotations") || has(v[0], "predictions")) return "label_studio";
      return "canonical";
    }
    return "spacy";
  }
  let first = null;
  for (const [, obj] of jsonLines(text)) { first = obj; break; }
  if (isObj(first)) {
    if (has(first, "data") && (has(first, "annotations") || has(first, "predictions"))) return "label_studio";
    if (has(first, "tokens") && has(first, "ner_tags")) return "hf_tokens";
    if (has(first, "offset_unit")) return "canonical";
    const ents = first.entities;
    if (has(first, "label") || (Array.isArray(ents) && ents.length && isObj(ents[0]) && has(ents[0], "start_offset"))) return "doccano";
    return "spacy";
  }
  if (Array.isArray(first)) return "spacy";
  return "canonical";
}

const bad = (rec, path, problem) => rec.problems.push([path, problem]);

function spanListOffsets(rec, items, path) {
  if (!Array.isArray(items)) { bad(rec, path, "must be an array"); return; }
  items.forEach((it, k) => {
    const p = `${path}[${k}]`;
    if (!(Array.isArray(it) && it.length >= 3)) { bad(rec, p, "must be [start, end, label]"); return; }
    const [s, e, lab] = it;
    if (!isInt(s) || !isInt(e)) { bad(rec, p, "start and end must be integers"); return; }
    if (typeof lab !== "string" || !lab) { bad(rec, p, "label must be a non-empty string"); return; }
    rec.spans.push({ start: s, end: e, label: lab });
    rec.span_refs.push([path, k, "list"]);
  });
}

function fill(rec, settings, own) {
  if (!own.offset_unit && rec.offset_unit === null) rec.offset_unit = settings.offset_unit ?? null;
  for (const k of ["normalization_declared", "nested_policy", "clitic_policy"]) {
    if (!has(own, k) && settings[k] != null) rec[k] = settings[k];
  }
  if (!has(own, "scheme") && settings.scheme != null) rec.scheme = settings.scheme;
  if (!has(own, "label_set") && settings.label_set != null) rec.label_set = [...settings.label_set];
}

function alignTokens(rec, text, toks) {
  const cps = cpsOf(text);
  const out = [];
  let pos = 0;
  for (let k = 0; k < toks.length; k++) {
    const tc = cpsOf(toks[k]);
    let i = -1;
    if (tc.length) {
      for (let p = pos; p + tc.length <= cps.length; p++) {
        let ok = true;
        for (let q = 0; q < tc.length; q++) if (cps[p + q] !== tc[q]) { ok = false; break; }
        if (ok) { i = p; break; }
      }
    }
    let gapOk = i >= 0;
    if (gapOk) for (let p = pos; p < i; p++) if (!isWs(cps[p])) { gapOk = false; break; }
    if (!gapOk) { bad(rec, `tokens[${k}]`, "is not the next token of the text"); return null; }
    out.push([i, i + tc.length]);
    pos = i + tc.length;
  }
  return out;
}

function parseCanonical(text, settings) {
  const recs = [];
  const s = text.replace(/^[ \t\r\n]+/, "");
  let items = [];
  if (s.startsWith("[")) {
    const [arr] = parseJson(s);
    if (Array.isArray(arr)) items = arr.map((v, k) => [null, k + 1, v, null]);
    else items = [[1, null, null, "is not valid JSON"]];
  } else items = jsonLines(text).map(([ln, v, err]) => [ln, null, v, err]);
  for (const [line, idx, obj, err] of items) {
    let id;
    if (line !== null) id = rid(obj, line);
    else id = isObj(obj) && (typeof obj.id === "string" || isInt(obj.id)) ? rid(obj, 0) : "#" + idx;
    const rec = newRecord(id, line);
    rec.source = obj;
    if (err) { bad(rec, "$", err); recs.push(rec); continue; }
    for (const [path, problem] of checkCanonical(obj)) bad(rec, path, problem);
    if (isObj(obj)) {
      if (typeof obj.text === "string") rec.text = obj.text;
      rec.offset_unit = typeof obj.offset_unit === "string" ? obj.offset_unit : null;
      for (const k of ["normalization_declared", "nested_policy", "clitic_policy"]) if (typeof obj[k] === "string") rec[k] = obj[k];
      if (typeof obj.scheme === "string") rec.scheme = obj.scheme;
      if (Array.isArray(obj.label_set)) rec.label_set = obj.label_set.filter((x) => typeof x === "string");
      if (Array.isArray(obj.spans)) obj.spans.forEach((sp, k) => {
        if (isObj(sp) && isInt(sp.start) && isInt(sp.end) && typeof sp.label === "string") {
          const d = { start: sp.start, end: sp.end, label: sp.label };
          if (typeof sp.text === "string") d.text = sp.text;
          rec.spans.push(d);
          rec.span_refs.push(["spans", k, "dict"]);
        }
      });
      if (Array.isArray(obj.tokens)) {
        const toks = obj.tokens;
        if (toks.length && toks.every((t) => typeof t === "string")) { rec.tokens_cp = alignTokens(rec, rec.text, toks); rec.tokens = []; }
        else rec.tokens = toks.filter((t) => isObj(t) && isInt(t.start) && isInt(t.end)).map((t) => [t.start, t.end]);
      }
      if (Array.isArray(obj.tags)) rec.tags = obj.tags.filter((t) => typeof t === "string");
    }
    fill(rec, settings, isObj(obj) ? obj : {});
    recs.push(rec);
  }
  return recs;
}

function parseDoccano(text, settings) {
  const recs = [];
  for (const [line, obj, err] of jsonLines(text)) {
    const rec = newRecord(rid(obj, line), line);
    rec.source = obj;
    if (err) bad(rec, "$", err);
    else if (!isObj(obj)) bad(rec, "$", "must be an object");
    else {
      if (typeof obj.text !== "string") bad(rec, "text", "is required and must be a string");
      else rec.text = obj.text;
      if (has(obj, "label")) spanListOffsets(rec, obj.label, "label");
      if (has(obj, "entities")) {
        const ents = obj.entities;
        if (!Array.isArray(ents)) bad(rec, "entities", "must be an array");
        else ents.forEach((it, k) => {
          const p = `entities[${k}]`;
          if (!isObj(it) || !isInt(it.start_offset) || !isInt(it.end_offset)) { bad(rec, p, "must have integer start_offset and end_offset"); return; }
          if (typeof it.label !== "string" || !it.label) { bad(rec, p, "label must be a non-empty string"); return; }
          rec.spans.push({ start: it.start_offset, end: it.end_offset, label: it.label });
          rec.span_refs.push(["entities", k, "doccano"]);
        });
      }
    }
    fill(rec, settings, {});
    recs.push(rec);
  }
  return recs;
}

function parseLabelStudio(text, settings) {
  const recs = [];
  let [data, err] = parseJson(text);
  if (err) { const r = newRecord("#1", 1); bad(r, "$", "is not valid JSON"); return [r]; }
  if (isObj(data)) data = [data];
  if (!Array.isArray(data)) { const r = newRecord("#1", 1); bad(r, "$", "must be an array of tasks"); return [r]; }
  data.forEach((task, ti0) => {
    const ti = ti0 + 1;
    if (!isObj(task)) { const r = newRecord("#" + ti, null); bad(r, `[${ti - 1}]`, "task must be an object"); recs.push(r); return; }
    let tid = task.id;
    tid = typeof tid === "string" || isInt(tid) ? String(tid) : "#" + ti;
    const d = task.data;
    let ttext = null;
    if (isObj(d)) {
      if (typeof d.text === "string") ttext = d.text;
      else for (const v of Object.values(d)) if (typeof v === "string") { ttext = v; break; }
    }
    let groups = [];
    for (const [key, mark] of [["annotations", ""], ["predictions", "p"]]) {
      const arr = task[key];
      if (Array.isArray(arr)) arr.forEach((ann, k0) => {
        let aid = isObj(ann) ? ann.id : undefined;
        aid = typeof aid === "string" || isInt(aid) ? String(aid) : String(k0 + 1);
        groups.push([`${tid}:${mark}${aid}`, key, k0, ann]);
      });
    }
    if (!groups.length) groups = [[tid, null, null, null]];
    for (const [id, key, k, ann] of groups) {
      const rec = newRecord(id, null);
      rec.source = task;
      rec.task_index = ti - 1;
      if (ttext === null) bad(rec, "data.text", "is required and must be a string");
      else rec.text = ttext;
      if (ann !== null) {
        const res = isObj(ann) ? ann.result : undefined;
        if (!Array.isArray(res)) bad(rec, `${key}[${k}].result`, "must be an array");
        else res.forEach((r, ri) => {
          if (!isObj(r)) return;
          const v = r.value;
          if (!isObj(v) || !has(v, "start") || !has(v, "end")) return;
          let labels = null;
          for (const lk of ["labels", "hypertextlabels"]) if (Array.isArray(v[lk])) labels = v[lk];
          const p = `${key}[${k}].result[${ri}].value`;
          if (!isInt(v.start) || !isInt(v.end)) { bad(rec, p, "start and end must be integers"); return; }
          if (!labels || !labels.length || !labels.every((x) => typeof x === "string" && x)) { bad(rec, p, "labels must be a non-empty array of strings"); return; }
          for (const lab of labels) {
            const sp = { start: v.start, end: v.end, label: lab };
            if (typeof v.text === "string") sp.text = v.text;
            rec.spans.push(sp);
            rec.span_refs.push([key, [k, ri], "ls"]);
          }
        });
      }
      fill(rec, settings, {});
      recs.push(rec);
    }
  });
  return recs;
}

function parseSpacy(text, settings) {
  const recs = [];
  for (const [line, obj, err] of jsonLines(text)) {
    const rec = newRecord(rid(obj, line), line);
    rec.source = obj;
    if (err) bad(rec, "$", err);
    else if (Array.isArray(obj)) {
      if (obj.length >= 2 && typeof obj[0] === "string" && isObj(obj[1])) {
        rec.text = obj[0];
        spanListOffsets(rec, has(obj[1], "entities") ? obj[1].entities : [], "[1].entities");
      } else bad(rec, "$", 'must be [text, {"entities": [...]}]');
    } else if (isObj(obj)) {
      if (typeof obj.text !== "string") bad(rec, "text", "is required and must be a string");
      else rec.text = obj.text;
      if (has(obj, "entities")) spanListOffsets(rec, obj.entities, "entities");
      if (has(obj, "spans")) {
        const sps = obj.spans;
        if (!Array.isArray(sps)) bad(rec, "spans", "must be an array");
        else sps.forEach((it, k) => {
          const p = `spans[${k}]`;
          if (!isObj(it) || !isInt(it.start) || !isInt(it.end)) { bad(rec, p, "must have integer start and end"); return; }
          if (typeof it.label !== "string" || !it.label) { bad(rec, p, "label must be a non-empty string"); return; }
          const sp = { start: it.start, end: it.end, label: it.label };
          if (typeof it.text === "string") sp.text = it.text;
          rec.spans.push(sp);
          rec.span_refs.push(["spans", k, "dict"]);
        });
      }
      if (Array.isArray(obj.tokens)) {
        const toks = [];
        obj.tokens.forEach((t, k) => {
          if (isObj(t) && isInt(t.start) && isInt(t.end)) toks.push([t.start, t.end]);
          else bad(rec, `tokens[${k}]`, "must have integer start and end");
        });
        rec.tokens = toks;
      }
    } else bad(rec, "$", "must be an object or a list");
    fill(rec, settings, {});
    recs.push(rec);
  }
  return recs;
}

function fromTokens(rec, tokens, tags) {
  let pos = 0;
  const toks = [];
  for (const t of tokens) {
    const l = cpsOf(t).length;
    toks.push([pos, pos + l]);
    pos += l + 1;
  }
  rec.text = tokens.join(" ");
  rec.tokens = toks;
  rec.tags = [...tags];
  rec.from_tokens = true;
  rec.offset_unit = "codepoint";
}

function parseConll(text, settings) {
  const recs = [];
  let sent = [], startLine = null, n = 0;
  const flush = () => {
    if (sent.length) {
      n += 1;
      const rec = newRecord("S" + n, startLine);
      sent.forEach(([ln, cols]) => { if (cols.length < 2) bad(rec, `line ${ln}`, "needs a token and a tag"); });
      fromTokens(rec, sent.map(([, c]) => c[0]), sent.map(([, c]) => (c.length >= 2 ? c[c.length - 1] : "O")));
      fill(rec, settings, {});
      rec.offset_unit = "codepoint";
      recs.push(rec);
    }
    sent = [];
    startLine = null;
  };
  for (const [ln, line] of lines(text)) {
    if (blank(line)) { flush(); continue; }
    const cols = line.split("\t").join(" ").split(" ").filter((c) => c !== "");
    if (cols.length && cols[0] === "-DOCSTART-") { flush(); continue; }
    if (startLine === null) startLine = ln;
    sent.push([ln, cols]);
  }
  flush();
  return recs;
}

function parseHfTokens(text, settings) {
  const recs = [];
  const names = settings.tag_names;
  for (const [line, obj, err] of jsonLines(text)) {
    const rec = newRecord(rid(obj, line), line);
    rec.source = obj;
    if (err) bad(rec, "$", err);
    else if (!isObj(obj) || !Array.isArray(obj.tokens) || !Array.isArray(obj.ner_tags)) bad(rec, "$", "must have arrays tokens and ner_tags");
    else {
      const toks = obj.tokens, tags = obj.ner_tags;
      let ok = true;
      if (toks.length !== tags.length) { bad(rec, "ner_tags", "must have as many items as tokens"); ok = false; }
      if (!toks.every((t) => typeof t === "string")) { bad(rec, "tokens", "must be strings"); ok = false; }
      const out = [];
      tags.forEach((t, k) => {
        if (typeof t === "string") out.push(t);
        else if (isInt(t)) {
          if (!names) { bad(rec, `ner_tags[${k}]`, "is an integer but no tag_names were given"); ok = false; out.push("O"); }
          else if (!(t >= 0 && t < names.length)) { bad(rec, `ner_tags[${k}]`, "is outside tag_names"); ok = false; out.push("O"); }
          else out.push(names[t]);
        } else { bad(rec, `ner_tags[${k}]`, "must be a string or an integer"); ok = false; out.push("O"); }
      });
      if (ok) fromTokens(rec, toks, out);
    }
    fill(rec, settings, {});
    rec.offset_unit = "codepoint";
    recs.push(rec);
  }
  return recs;
}

const PARSERS = { canonical: parseCanonical, doccano: parseDoccano, label_studio: parseLabelStudio, spacy: parseSpacy, conll: parseConll, hf_tokens: parseHfTokens };

export function parse(text, fmt, settings) {
  if (!PARSERS[fmt]) throw new Error("unknown format: " + fmt);
  const recs = PARSERS[fmt](text, settings);
  for (const r of recs) if (r.scheme !== null) r.scheme = ALIASES[r.scheme] || r.scheme;
  return recs;
}

// ------------------------------------------------------------------ checks
const EDIT_PRIORITY = ["E008", "E012", "E004", "W102", "W101", "E007"];
const EDIT_CONF = { E008: "medium", E012: "high", E004: "medium", W102: "medium", W101: "high", E007: "low" };
const CONF_RANK = { high: 3, medium: 2, low: 1 };
const READ_ORDER = ["crlf_to_lf", "lf_to_crlf", "strip_bom", "add_bom", "NFC", "NFKC", "remove_tatweel", "remove_diacritics"];
const READ_CODE = { crlf_to_lf: ["E013", "offsets_lf"], lf_to_crlf: ["E013", "offsets_crlf"], strip_bom: ["E018", "offsets_without_bom"], add_bom: ["E018", "offsets_with_bom"], NFC: ["E011", "offsets_on_normalized"], NFKC: ["E011", "offsets_on_normalized"], remove_tatweel: ["E011", "offsets_on_normalized"], remove_diacritics: ["E011", "offsets_on_normalized"] };
const FORM_POLICIES = ["NFC", "NFKC", "remove_tatweel", "remove_diacritics"];
const RX_PROCLITIC = /^[وف]?[بكل]?$/u;
const RX_ART1 = /^([وف]?[بك]?)ال$/u;
const RX_ART2 = /^([وف]?ل)ل$/u;
const RX_CL1 = /^([وف]?[بك]?)ال(.*)$/u;
const RX_CL2 = /^([وف]?ل)ل(.*)$/u;
const len = (s) => cpsOf(s).length;

function F(code, kind = null, span = null, start = null, end = null, detail = {}) {
  return { code, kind, span_index: span, start, end, detail };
}
const edgeKind = (a, b, suffix = "") => (a && b ? "both" + suffix : (a ? "start" : "end") + suffix);

class Ctx {
  constructor(rec, fileBom) {
    this.rec = rec;
    this.cps = cpsOf(rec.text);
    this.n = this.cps.length;
    this.unit = rec.offset_unit;
    this.omap = new OffsetMap(this.cps);
    this.word = this.cps.map(isWord);
    this.fileBom = fileBom;
    this.policy = rec.clitic_policy || "unspecified";
    this.readings = new Map();
    this.tok = rec.tokens !== null ? [new Set(), new Set(), []] : null;
  }
  reading(name) {
    if (!this.readings.has(name)) this.readings.set(name, makeReading(this.cps, name, this.fileBom));
    return this.readings.get(name);
  }
  wordStart(p) { while (p > 0 && this.word[p - 1]) p--; return p; }
  wordEnd(p) { while (p < this.n && this.word[p]) p++; return p; }
  midWord(p) { return p > 0 && p < this.n && this.word[p - 1] && this.word[p]; }
  sl(a, b) { return join(this.cps.slice(a, b)); }
}

function lettersOf(cps, base = 0) {
  const out = [];
  cps.forEach((ch, i) => { if (isLetter(ch) && ch !== TATWEEL) out.push([ch, base + i]); });
  return out;
}

const RX_ART_SPLIT = /^([وف]?[بك]?)ا$/u;

function analyzePrefix(p, nxt = []) {
  const keep = [];
  p.forEach((ch, i) => { if (!isMark(ch)) keep.push([ch, i]); });
  while (keep.length && keep[keep.length - 1][0] === TATWEEL) keep.pop();
  if (!keep.length) return null;
  const base = keep.map((x) => x[0]).join("");
  if (!keep.every((x) => isArabicLetter(x[0]))) return null;
  if (RX_PROCLITIC.test(base)) return ["proclitic", null];
  const m = base.match(RX_ART1) || base.match(RX_ART2);
  if (m) return ["article", keep[len(m[1])][1]];
  const m2 = base.match(RX_ART_SPLIT);
  if (m2 && nxt[0] === "ل" && lettersOf(nxt).length >= 3) return ["article_split", keep[len(m2[1])][1]];
  return null;
}

const firstScript = (cps) => { for (const ch of cps) { const s = scriptOf(ch); if (s) return s; } return null; };
const lastScript = (cps) => { for (let i = cps.length - 1; i >= 0; i--) { const s = scriptOf(cps[i]); if (s) return s; } return null; };

function startClusterExclude(ctx, s) {
  const we = ctx.wordEnd(s);
  const lets = lettersOf(ctx.cps.slice(s, we), s);
  const ar = [];
  for (const x of lets) { if (isArabicLetter(x[0])) ar.push(x); else break; }
  const base = ar.map((x) => x[0]).join("");
  const rest = (k) => lets.length - k;
  let m = base.match(RX_CL1);
  if (m && m[1] && rest(len(m[1]) + 2) >= 2) return lets[len(m[1])][1];
  m = base.match(RX_CL2);
  if (m && rest(len(m[1]) + 1) >= 2) return lets[len(m[1])][1];
  if (ar.length < lets.length && isLatinLetter(lets[ar.length][0]) && base && RX_PROCLITIC.test(base)) return lets[ar.length][1];
  return null;
}

function content(ctx, s, e) {
  const t = ctx.cps;
  const out = [];
  let any = false;
  for (let k = s; k < e; k++) if (isAlnum(t[k])) { any = true; break; }
  if (!any) return [F("E002", "no_content")];
  let i = s;
  const leadCtrl = [];
  let leadWs = false;
  while (i < e && (isWs(t[i]) || isControl(t[i]))) { if (isControl(t[i])) leadCtrl.push(t[i]); else leadWs = true; i++; }
  let j = e;
  const trailCtrl = [];
  let trailWs = false;
  while (j > i && (isWs(t[j - 1]) || isControl(t[j - 1]))) { if (isControl(t[j - 1])) trailCtrl.push(t[j - 1]); else trailWs = true; j--; }
  if (leadCtrl.length || trailCtrl.length) {
    const seen = [];
    for (const ch of [...leadCtrl, ...trailCtrl.slice().reverse()]) if (!seen.includes(uplus(ch))) seen.push(uplus(ch));
    out.push(F("E012", edgeKind(leadCtrl.length > 0, trailCtrl.length > 0), null, null, null, { char: seen.join(", ") }));
  }
  if (leadWs || trailWs) out.push(F("W101", edgeKind(leadWs, trailWs)));
  const pStart = isPunct(t[i]) && !PUNCT_EXEMPT.has(t[i]);
  const last = t[j - 1];
  const pEnd = isPunct(last) && !PUNCT_EXEMPT.has(last) && !(last === "." && j - 2 >= i && isLatinLetter(t[j - 2]));
  if (pStart || pEnd) {
    const seen = [];
    if (pStart) seen.push(uplus(t[i]));
    if (pEnd && !seen.includes(uplus(last))) seen.push(uplus(last));
    out.push(F("W102", edgeKind(pStart, pEnd), null, null, null, { char: seen.join(", ") }));
  }
  const gStart = !ctx.omap.gbSet.has(s);
  const gEnd = !ctx.omap.gbSet.has(e);
  if (gStart || gEnd) out.push(F("E004", edgeKind(gStart, gEnd)));
  let wStart = false, wEnd = false, tokStart = false, tokEnd = false, mixStart = false, mixEnd = false;
  if (!gStart && i === s) {
    const tokCut = ctx.tok !== null && !ctx.tok[0].has(s);
    if (tokCut) tokStart = true;
    else if (ctx.midWord(s)) {
      const ws = ctx.wordStart(s), we = ctx.wordEnd(s);
      const kind = analyzePrefix(t.slice(ws, s), t.slice(s, we));
      if (kind && kind[0] === "article_split" && (ctx.policy === "include" || ctx.policy === "exclude")) {
        out.push(F("E008", "article_split", null, null, null, { _start: ctx.policy === "include" ? ws : ws + kind[1] }));
      } else if (kind && kind[0] !== "article_split" && lettersOf(t.slice(s, we)).length >= 2) {
        if (ctx.policy === "include") out.push(F("E008", "clitic_excluded", null, null, null, { _start: ws }));
        else if (ctx.policy === "exclude") { if (kind[0] === "article") out.push(F("E008", "article_excluded", null, null, null, { _start: ws + kind[1] })); }
        else out.push(F("I204"));
      } else if (ctx.tok === null) {
        const a = lastScript(t.slice(ws, s)), b = firstScript(t.slice(s, we));
        if (a && b && a !== b) mixStart = true; else wStart = true;
      }
    } else if (ctx.policy === "exclude") {
      const q = startClusterExclude(ctx, s);
      if (q !== null) out.push(F("E008", "clitic_included", null, null, null, { _start: q }));
    }
  }
  if (!gEnd && j === e) {
    if (ctx.tok !== null) { if (!ctx.tok[1].has(e)) tokEnd = true; }
    else if (ctx.midWord(e)) {
      const ws = ctx.wordStart(e), we = ctx.wordEnd(e);
      const a = lastScript(t.slice(ws, e)), b = firstScript(t.slice(e, we));
      if (a && b && a !== b) mixEnd = true; else wEnd = true;
    }
  }
  if (tokStart || tokEnd) out.push(F("E007", edgeKind(tokStart, tokEnd, "_token")));
  else if (wStart || wEnd) out.push(F("E007", edgeKind(wStart, wEnd)));
  if (mixStart || mixEnd) out.push(F("E016", edgeKind(mixStart, mixEnd)));
  return out;
}

const isClean = (ctx, s, e) => content(ctx, s, e).every((f) => f.code[0] === "I");

function spanTextForm(sl, st) {
  for (const p of FORM_POLICIES) if (applyPolicy(sl, p) === applyPolicy(st, p)) return ["E011", p];
  if (applyPolicy(sl, "crlf_to_lf") === applyPolicy(st, "crlf_to_lf")) return ["E013", "crlf_to_lf"];
  return null;
}

function occurrences(hay, needle) {
  const out = [];
  const m = needle.length;
  if (!m) return out;
  for (let i = 0; i + m <= hay.length; i++) {
    let ok = true;
    for (let k = 0; k < m; k++) if (hay[i + k] !== needle[k]) { ok = false; break; }
    if (ok) out.push(i);
  }
  return out;
}

const sameRange = (a, b) => a !== null && b !== null && a[0] === b[0] && a[1] === b[1];

function diagnose(ctx, sp, sd, ed, declared, textBased, hard) {
  const succ = [];
  const tryUnit = (u) => {
    if (u === ctx.unit) return;
    if (!textBased && (u === "utf8_byte" || u === "grapheme") && !hard) return;
    const [s2, e1] = ctx.omap.toCp(sd, u);
    const [e2, e2r] = ctx.omap.toCp(ed, u);
    if (e1 || e2r || s2 >= e2 || sameRange([s2, e2], declared)) return;
    const ok = textBased ? ctx.sl(s2, e2) === sp.text : isClean(ctx, s2, e2);
    if (ok) succ.push(["E014", null, "unit_found", u, [s2, e2]]);
  };
  for (const u of ["codepoint", "utf16", "utf8_byte"]) tryUnit(u);
  for (const name of READ_ORDER) {
    const r = ctx.reading(name);
    if (r === null) continue;
    const [sT, er1] = r.omap.toCp(sd, ctx.unit);
    const [eT, er2] = r.omap.toCp(ed, ctx.unit);
    if (er1 || er2 || sT >= eT) continue;
    const s2 = r.startMap[sT], e2 = r.endMap[eT];
    if (s2 === null || e2 === null || s2 >= e2 || sameRange([s2, e2], declared)) continue;
    const ok = textBased ? (join(r.cps.slice(sT, eT)) === sp.text || ctx.sl(s2, e2) === sp.text) : isClean(ctx, s2, e2);
    if (ok) { const [code, kind] = READ_CODE[name]; succ.push([code, kind, "policy", name, [s2, e2]]); }
  }
  tryUnit("grapheme");
  if (!succ.length && textBased) {
    for (const name of [null, ...FORM_POLICIES]) {
      let hits = [];
      if (name === null) {
        const nd = cpsOf(sp.text);
        hits = occurrences(ctx.cps, nd).map((p) => [p, p + nd.length]);
      } else {
        const target = applyPolicy(sp.text, name);
        if (target === sp.text) continue;
        const tc = cpsOf(target);
        const r = ctx.reading(name);
        if (r === null) hits = occurrences(ctx.cps, tc).map((p) => [p, p + tc.length]);
        else for (const p of occurrences(r.cps, tc)) {
          const a = r.startMap[p], b = r.endMap[p + tc.length];
          if (a !== null && b !== null && a < b) hits.push([a, b]);
        }
      }
      if (!hits.length) continue;
      if (hits.length > 1) return ["none", [], null, null, null];
      if (name === null) return ["ok", [], hits[0], "low", "E003"];
      return ["ok", [F("E011", "relocated", null, null, null, { policy: name })], hits[0], "medium", "E011"];
    }
    return ["none", [], null, null, null];
  }
  if (!succ.length) return ["none", [], null, null, null];
  const ranges = [];
  for (const x of succ) if (!ranges.some((r) => sameRange(r, x[4]))) ranges.push(x[4]);
  if (ranges.length === 1) {
    const [code, kind, key, val] = succ[0];
    const also = succ.slice(1).map((x) => x[3]);
    const f = key === "unit_found" ? F(code, kind, null, null, null, { unit_found: val, unit: ctx.unit, also_fits: also }) : F(code, kind, null, null, null, { policy: val, also_fits: also });
    return ["ok", [f], ranges[0], textBased ? "high" : "medium", code];
  }
  const byCode = new Map();
  for (const [code, , , val] of succ) { if (!byCode.has(code)) byCode.set(code, []); byCode.get(code).push(val); }
  const findings = [];
  for (const [code, vals] of byCode) {
    if (code === "E014") findings.push(F(code, "ambiguous", null, null, null, { unit_found: vals.join(", "), unit: ctx.unit }));
    else findings.push(F(code, "ambiguous", null, null, null, { policy: vals.join(", ") }));
  }
  return ["ambiguous", findings, null, null, null];
}

function structuralRepair(ctx, s, e, sym) {
  const t = ctx.cps;
  const codes = {};
  for (const f of sym) codes[f.code] = f;
  if (codes.E002) return null;
  let s2 = s, e2 = e;
  const applied = [];
  const e004 = codes.E004, e008 = codes.E008;
  if (e008) { s2 = e008.detail._start; applied.push("E008"); }
  else if (e004 && (e004.kind === "start" || e004.kind === "both")) {
    const [cs, ce] = ctx.omap.clusterOf(s);
    s2 = ce >= ctx.n || !ctx.word[ce] ? ce : cs;
    applied.push("E004");
  }
  if (e004 && (e004.kind === "end" || e004.kind === "both")) {
    const [, ce] = ctx.omap.clusterOf(e);
    e2 = ce;
    applied.push("E004");
  }
  const trimCode = (ch) => (isControl(ch) ? "E012" : isWs(ch) ? "W101" : null);
  while (s2 < e2) {
    const ch = t[s2];
    const c = trimCode(ch) || (isPunct(ch) && !PUNCT_EXEMPT.has(ch) ? "W102" : null);
    if (c === null) break;
    applied.push(c);
    s2++;
  }
  while (e2 > s2) {
    const ch = t[e2 - 1];
    let c = trimCode(ch);
    if (c === null && isPunct(ch) && !PUNCT_EXEMPT.has(ch) && !(ch === "." && e2 - 2 >= s2 && isLatinLetter(t[e2 - 2]))) c = "W102";
    if (c === null) break;
    applied.push(c);
    e2--;
  }
  if (s2 >= e2) return null;
  if (ctx.tok !== null) {
    const [starts, ends] = ctx.tok;
    if (!starts.has(s2)) { const c = [...starts].filter((x) => x <= s2); if (c.length) { s2 = Math.max(...c); applied.push("E007"); } }
    if (!ends.has(e2)) { const c = [...ends].filter((x) => x >= e2); if (c.length) { e2 = Math.min(...c); applied.push("E007"); } }
  } else {
    if (ctx.midWord(s2)) {
      const ws = ctx.wordStart(s2), we = ctx.wordEnd(s2);
      const kind = analyzePrefix(t.slice(ws, s2), t.slice(s2, we));
      const a = lastScript(t.slice(ws, s2)), b = firstScript(t.slice(s2, we));
      const mixed = a && b && a !== b;
      const acceptable = kind !== null && kind[0] !== "article_split" && lettersOf(t.slice(s2, we)).length >= 2 && (ctx.policy === "unspecified" || (ctx.policy === "exclude" && kind[0] === "proclitic"));
      if (!acceptable && !mixed) { s2 = ws; applied.push("E007"); }
    }
    if (ctx.midWord(e2)) {
      const ws = ctx.wordStart(e2), we = ctx.wordEnd(e2);
      const a = lastScript(t.slice(ws, e2)), b = firstScript(t.slice(e2, we));
      const mixed = a && b && a !== b;
      if (!mixed) { e2 = we; applied.push("E007"); }
    }
  }
  if ((s2 === s && e2 === e) || !applied.length) return null;
  const reasons = EDIT_PRIORITY.filter((c) => applied.includes(c));
  let conf = null;
  for (const c of reasons) { const cc = EDIT_CONF[c]; if (conf === null || CONF_RANK[cc] < CONF_RANK[conf]) conf = cc; }
  return [s2, e2, reasons[0], reasons, conf];
}

function publicF(f) {
  const d = {};
  for (const [k, v] of Object.entries(f.detail)) if (!k.startsWith("_")) d[k] = v;
  return { ...f, detail: d };
}
const at = (f, i, sd, ed) => ({ ...f, span_index: i, start: sd, end: ed });

function rep(ctx, i, sp, old, nw, reason, reasons, conf) {
  return { record_id: ctx.rec.id, span_index: i, label: sp.label, old: [...old], new: [...nw], unit: ctx.unit, reason_code: reason, reason_codes: reasons, confidence: conf };
}
function cpRep(ctx, i, sp, old, newCp, reason, reasons, conf) {
  if (newCp === null) return null;
  const a = ctx.omap.fromCp(newCp[0], ctx.unit), b = ctx.omap.fromCp(newCp[1], ctx.unit);
  if (a === null || b === null) return null;
  return rep(ctx, i, sp, old, [a, b], reason, reasons, conf);
}

function checkSpan(ctx, i, sp) {
  const out = [];
  const sd = sp.start, ed = sp.end, unit = ctx.unit;
  if (ctx.rec.label_set !== null && !ctx.rec.label_set.includes(sp.label)) out.push(F("E010", null, i, sd, ed, { label: sp.label }));
  const [s, serr] = ctx.omap.toCp(sd, unit);
  const [e, eerr] = ctx.omap.toCp(ed, unit);
  const rng = [serr === "range", eerr === "range"], mid = [serr === "mid", eerr === "mid"];
  const anyR = rng[0] || rng[1], anyM = mid[0] || mid[1];
  if (anyR) out.push(F("E001", edgeKind(rng[0], rng[1]), i, sd, ed, { limit: ctx.omap.total(unit), unit }));
  if (anyM) out.push(F("E015", edgeKind(mid[0], mid[1]), i, sd, ed, { unit }));
  if (sd === ed) { out.push(F("E002", "zero_length", i, sd, ed)); return [out, null, null]; }
  if (sd > ed) {
    out.push(F("E002", "reversed", i, sd, ed));
    let r = null;
    if (!anyR && !anyM) {
      const a = ctx.omap.toCp(ed, unit)[0], b = ctx.omap.toCp(sd, unit)[0];
      let ok = false;
      for (let k = a; k < b; k++) if (isAlnum(ctx.cps[k])) { ok = true; break; }
      if (ok) r = rep(ctx, i, sp, [sd, ed], [ed, sd], "E002", ["E002"], "low");
    }
    return [out, r, null];
  }
  const textGiven = has(sp, "text");
  if (anyR || anyM) {
    const [st, fs, nw, conf, reason] = diagnose(ctx, sp, sd, ed, null, textGiven, true);
    for (const f of fs) out.push(at(f, i, sd, ed));
    return [out, st === "ok" ? cpRep(ctx, i, sp, [sd, ed], nw, reason, [reason], conf) : null, null];
  }
  const sl = ctx.sl(s, e);
  const sym = content(ctx, s, e);
  const mismatch = textGiven && sp.text !== sl;
  if (mismatch) out.push(F("E003", null, i, sd, ed));
  let status = "none", dfs = [], nw = null, conf = null, reason = null;
  if (mismatch) {
    const form = spanTextForm(sl, sp.text);
    const edge = form ? null : edgeForm(sl, sp.text);
    if (form) out.push(F(form[0], "span_text_form", i, sd, ed, { policy: form[1] }));
    else if (edge !== null) for (const f of edge) out.push(at(f, i, sd, ed));
    else [status, dfs, nw, conf, reason] = diagnose(ctx, sp, sd, ed, [s, e], true, false);
  } else if (!textGiven && sym.some((f) => f.code[0] === "E" || f.code[0] === "W")) {
    [status, dfs, nw, conf, reason] = diagnose(ctx, sp, sd, ed, [s, e], false, false);
  }
  for (const f of dfs) out.push(at(f, i, sd, ed));
  if (status === "ok" && reason !== "E003") return [out, cpRep(ctx, i, sp, [sd, ed], nw, reason, [reason], conf), [s, e]];
  for (const f of sym) out.push(at(publicF(f), i, sd, ed));
  if (status === "ambiguous") return [out, null, [s, e]];
  let r = null;
  const sr = structuralRepair(ctx, s, e, sym);
  if (sr !== null) r = cpRep(ctx, i, sp, [sd, ed], [sr[0], sr[1]], sr[2], sr[3], sr[4]);
  else if (status === "ok") r = cpRep(ctx, i, sp, [sd, ed], nw, reason, [reason], conf);
  return [out, r, [s, e]];
}

function edgeCode(ch) {
  if (isControl(ch)) return "E012";
  if (isWs(ch)) return "W101";
  if (isPunct(ch) && !PUNCT_EXEMPT.has(ch)) return "W102";
  return null;
}

function trimEdges(str) {
  const s = cpsOf(str);
  let a = 0, b = s.length;
  while (a < b && edgeCode(s[a])) a++;
  while (b > a && edgeCode(s[b - 1]) && !(s[b - 1] === "." && b - 2 >= a && isLatinLetter(s[b - 2]))) b--;
  return [join(s.slice(a, b)), s.slice(0, a), s.slice(b)];
}

function edgeForm(sl, st) {
  const [c1] = trimEdges(sl);
  const [c2, lead, trail] = trimEdges(st);
  if (!c1 || c1 !== c2) return null;
  const out = [];
  for (const code of ["E012", "W101", "W102"]) {
    const chars = [...lead, ...trail].filter((ch) => edgeCode(ch) === code);
    if (chars.length) {
      const seen = [];
      for (const ch of chars) if (!seen.includes(uplus(ch))) seen.push(uplus(ch));
      out.push(F(code, "span_text", null, null, null, { char: seen.join(", ") }));
    }
  }
  return out;
}

function inferScheme(tags) {
  const pre = new Set(tags.filter((t) => typeof t === "string" && parseTag(t) && t !== "O").map((t) => t[0]));
  if (pre.has("L") || pre.has("U")) return "BILUO";
  if (pre.has("E") || pre.has("S")) return "BIOES";
  return "IOB2";
}

function unitHint(rec, fileBom, ctx = null) {
  if (ctx === null) ctx = new Ctx(rec, fileBom);
  const counts = {};
  let n = 0;
  for (const sp of rec.spans) {
    if (sp.start >= sp.end) continue;
    n++;
    for (const u of UNITS) {
      const [a, e1] = ctx.omap.toCp(sp.start, u);
      const [b, e2] = ctx.omap.toCp(sp.end, u);
      if (e1 || e2 || a >= b) continue;
      const ok = has(sp, "text") ? ctx.sl(a, b) === sp.text : isClean(ctx, a, b);
      if (ok) counts[u] = (counts[u] || 0) + 1;
    }
  }
  const order = UNITS.filter((u) => counts[u]).sort((x, y) => (counts[y] - counts[x]) || (UNITS.indexOf(x) - UNITS.indexOf(y)));
  let en, ar;
  if (order.length) {
    en = "Offsets fit " + order.map((u) => `${u} for ${counts[u]} of ${n} spans`).join("; ") + ".";
    ar = "تتطابق المواضع مع " + order.map((u) => `${u} في ${counts[u]} من ${n}`).join("؛ ") + ".";
  } else {
    en = "No unit makes the offsets fit.";
    ar = "لا توجد وحدة تجعل المواضع متطابقة.";
  }
  const c2 = {};
  for (const u of UNITS) c2[u] = counts[u] || 0;
  return { hint: en, hint_ar: ar, counts: c2, spans: n, _best: order.length ? order[0] : null, _counts: counts };
}

function checkRecord(rec, fileBom) {
  let findings = [];
  const repairs = [], conv = [];
  for (const [path, problem] of rec.problems) findings.push(F("E020", null, null, null, null, { path, problem }));
  const text = rec.text;
  if (/[\uD800-\uDFFF]/u.test(text)) findings.push(F("E020", null, null, null, null, { path: "text", problem: "contains an unpaired surrogate" }));
  if (rec.offset_unit === null) {
    findings.push(publicF(F("E019", null, null, null, null, unitHint(rec, fileBom))));
    return [findings, repairs, conv, 0];
  }
  if (findings.some((f) => f.code === "E020")) return [findings, repairs, conv, 0];
  const ctx = new Ctx(rec, fileBom);
  if (rec.tokens_cp !== null) {
    ctx.tok = [new Set(rec.tokens_cp.map((x) => x[0])), new Set(rec.tokens_cp.map((x) => x[1])), rec.tokens_cp.map((x) => [...x])];
  } else if (rec.tokens !== null) {
    const st = new Set(), en = new Set(), pairs = [];
    rec.tokens.forEach(([a, b], k) => {
      const [ca, e1] = ctx.omap.toCp(a, ctx.unit);
      const [cb, e2] = ctx.omap.toCp(b, ctx.unit);
      if (e1 || e2 || ca > cb) { findings.push(F("E020", null, null, null, null, { path: `tokens[${k}]`, problem: "offsets do not fit the text" })); return; }
      st.add(ca); en.add(cb); pairs.push([ca, cb]);
    });
    ctx.tok = [st, en, pairs];
  }
  if (ctx.cps[0] === BOM) findings.push(F("E018", "text"));
  const nd = rec.normalization_declared || "none";
  if (["NFC", "NFKC", "NFD", "NFKD"].includes(nd) && text.normalize(nd) !== text) findings.push(F("E011", "declared_form", null, null, null, { policy: nd }));
  const astral = ctx.cps.filter((ch) => ch.codePointAt(0) > 0xffff).length;
  if (astral) findings.push(F("I201", null, null, null, null, { n: astral }));
  const forms = ["NFC", "NFKC"].filter((f) => len(text.normalize(f)) !== ctx.n);
  if (forms.length) findings.push(F("I202", null, null, null, null, { forms: forms.join(" and ") }));
  if (rec.tags !== null) {
    let scheme = rec.scheme;
    if (scheme === null) { scheme = inferScheme(rec.tags); findings.push(F("I205", null, null, null, null, { scheme })); }
    for (const [idx, kind, tag, prev] of checkTags(rec.tags, scheme)) findings.push(F("E009", kind, null, null, null, { token: idx, tag: String(tag), prev: prev !== null ? String(prev) : "", scheme }));
    if (rec.from_tokens) for (const [a, b, lab] of tagsToEntities(rec.tags, scheme)) rec.spans.push({ start: rec.tokens[a][0], end: rec.tokens[b][1], label: lab });
  }
  const ranges = new Map();
  rec.spans.forEach((sp, i) => {
    const [fs, r, cp] = checkSpan(ctx, i, sp);
    findings.push(...fs);
    if (r !== null && !rec.from_tokens) repairs.push(r);
    if (cp !== null) { ranges.set(i, cp); conv.push({ span_index: i, ...ctx.omap.convert(cp[0], cp[1]) }); }
  });
  const idx = [...ranges.keys()].sort((a, b) => a - b);
  for (let x = 0; x < idx.length; x++) for (let y = x + 1; y < idx.length; y++) {
    const i = idx[x], j = idx[y];
    const a = ranges.get(i), b = ranges.get(j);
    const si = rec.spans[i], sj = rec.spans[j];
    if (a[0] === b[0] && a[1] === b[1]) {
      if (si.label === sj.label) findings.push(F("E005", "duplicate", j, sj.start, sj.end, { other: i }));
      else if (rec.nested_policy !== "allow") findings.push(F("E006", "same_extent", j, sj.start, sj.end, { other: i }));
    } else if ((a[0] < b[0] && b[0] < a[1] && a[1] < b[1]) || (b[0] < a[0] && a[0] < b[1] && b[1] < a[1])) {
      findings.push(F("E005", "crossing", j, sj.start, sj.end, { other: i }));
    } else if (rec.nested_policy !== "allow" && ((a[0] <= b[0] && b[1] <= a[1]) || (b[0] <= a[0] && a[1] <= b[1]))) {
      const [inner, outer] = a[0] <= b[0] && b[1] <= a[1] ? [j, i] : [i, j];
      findings.push(F("E006", "nested", inner, rec.spans[inner].start, rec.spans[inner].end, { other: outer }));
    }
  }
  const badF = findings.filter((f) => ["E001", "E003", "E014", "E015"].includes(f.code));
  if (badF.length && !rec.from_tokens) {
    const hint = unitHint(rec, fileBom, ctx);
    const best = hint._best;
    if (best && best !== rec.offset_unit && hint._counts[best] > (hint._counts[rec.offset_unit] || 0)) findings.push(F("I203", null, null, null, null, hint));
  }
  findings = findings.map(publicF);
  const badSpans = new Set(findings.filter((f) => f.span_index !== null && (f.code[0] === "E" || f.code[0] === "W")).map((f) => f.span_index));
  let valid = 0;
  for (let i = 0; i < rec.spans.length; i++) if (!badSpans.has(i)) valid++;
  return [findings, repairs, conv, valid];
}

// ------------------------------------------------------------------ report
const POLICY_NAMES = {
  NFC: ["NFC normalisation", "تطبيع NFC"], NFKC: ["NFKC normalisation", "تطبيع NFKC"], NFD: ["NFD normalisation", "تطبيع NFD"], NFKD: ["NFKD normalisation", "تطبيع NFKD"],
  remove_tatweel: ["tatweel removal", "حذف التطويل"], remove_diacritics: ["diacritic removal", "حذف التشكيل"],
  crlf_to_lf: ["CRLF to LF conversion", "تحويل CRLF إلى LF"], lf_to_crlf: ["LF to CRLF conversion", "تحويل LF إلى CRLF"],
  strip_bom: ["removing U+FEFF", "حذف U+FEFF"], add_bom: ["adding a byte order mark", "إضافة علامة ترتيب البايتات"],
};
const SETTING_KEYS = ["format", "offset_unit", "scheme", "nested_policy", "clitic_policy", "label_set", "normalization_declared", "tag_names"];

function policyLabel(v, lang) {
  const k = lang === "en" ? 0 : 1;
  return String(v).split(",").map((p) => (POLICY_NAMES[p.trim()] || [p.trim(), p.trim()])[k]).join(lang === "en" ? ", " : "، ");
}

function pyStr(v) {
  if (v === null) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (Array.isArray(v)) return "[" + v.map((x) => (typeof x === "string" ? "'" + x + "'" : pyStr(x))).join(", ") + "]";
  return String(v);
}

export function render(code, kind, values, lang) {
  const msgs = CODES[code].messages;
  const tmpl = (msgs[kind] || msgs.default || Object.values(msgs)[0])[lang];
  let out = tmpl;
  for (const [k, v0] of Object.entries(values)) {
    const v = k === "policy" ? policyLabel(v0, lang) : pyStr(v0);
    out = out.split("{" + k + "}").join(v);
  }
  return out;
}

function values(f) {
  const v = { ...f.detail };
  v.span = f.span_index;
  v.start = f.start;
  v.end = f.end;
  if (has(f.detail, "token")) v.token = f.detail.token + 1;
  return v;
}

function finish(f) {
  const vals = values(f);
  return { code: f.code, severity: CODES[f.code].severity, span_index: f.span_index, start: f.start, end: f.end, kind: f.kind, detail: f.detail,
    message_en: render(f.code, f.kind, vals, "en"), message_ar: render(f.code, f.kind, vals, "ar") };
}

function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
function sortKey(a, b) {
  const ai = a.span_index !== null, bi = b.span_index !== null;
  if (ai !== bi) return ai ? 1 : -1;
  return ((a.span_index ?? -1) - (b.span_index ?? -1)) || cmp(a.code, b.code) || cmp(a.kind || "", b.kind || "");
}

export function canonicalJson(v) {
  if (v === null || typeof v !== "object") return JSON.stringify(v);
  if (Array.isArray(v)) return "[" + v.map(canonicalJson).join(",") + "]";
  return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canonicalJson(v[k])).join(",") + "}";
}

// SHA-256 (FIPS 180-4), synchronous, for settings_hash and the input digest.
const K = new Uint32Array([0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);
export function sha256(bytes) {
  const l = bytes.length;
  const nb = (((l + 9) + 63) >> 6) << 6;
  const m = new Uint8Array(nb);
  m.set(bytes);
  m[l] = 0x80;
  const bits = l * 8;
  const dv = new DataView(m.buffer);
  dv.setUint32(nb - 4, bits >>> 0);
  dv.setUint32(nb - 8, Math.floor(bits / 0x100000000));
  const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
  const W = new Uint32Array(64);
  const rotr = (x, n) => (x >>> n) | (x << (32 - n));
  for (let off = 0; off < nb; off += 64) {
    for (let t = 0; t < 16; t++) W[t] = dv.getUint32(off + t * 4);
    for (let t = 16; t < 64; t++) {
      const s0 = rotr(W[t - 15], 7) ^ rotr(W[t - 15], 18) ^ (W[t - 15] >>> 3);
      const s1 = rotr(W[t - 2], 17) ^ rotr(W[t - 2], 19) ^ (W[t - 2] >>> 10);
      W[t] = (W[t - 16] + s0 + W[t - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = H;
    for (let t = 0; t < 64; t++) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (h + S1 + ch + K[t] + W[t]) >>> 0;
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const mj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + mj) >>> 0;
      h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0; H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
    H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0; H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
  }
  return Array.from(H).map((x) => x.toString(16).padStart(8, "0")).join("");
}

export function settingsHash(settings) {
  const o = {};
  for (const k of SETTING_KEYS) o[k] = settings[k] ?? null;
  return sha256(new TextEncoder().encode(canonicalJson(o)));
}

// Strict UTF-8 decoding with the position of the first invalid byte (as Python reports it).
export function decode(data) {
  const ff = [];
  const bom = data.length >= 3 && data[0] === 0xef && data[1] === 0xbb && data[2] === 0xbf;
  const body = bom ? data.subarray(3) : data;
  if (bom) ff.push(F("E018", "file"));
  let i = 0;
  const n = body.length;
  while (i < n) {
    const b = body[i];
    let need = 0, lo = 0x80, hi = 0xbf;
    if (b < 0x80) { i++; continue; }
    else if (b >= 0xc2 && b <= 0xdf) need = 1;
    else if (b === 0xe0) { need = 2; lo = 0xa0; }
    else if ((b >= 0xe1 && b <= 0xec) || b === 0xee || b === 0xef) need = 2;
    else if (b === 0xed) { need = 2; hi = 0x9f; }
    else if (b === 0xf0) { need = 3; lo = 0x90; }
    else if (b >= 0xf1 && b <= 0xf3) need = 3;
    else if (b === 0xf4) { need = 3; hi = 0x8f; }
    else { ff.push(F("E017", null, null, null, null, { byte: i + (bom ? 3 : 0) })); return [null, ff, bom]; }
    for (let k = 1; k <= need; k++) {
      const c = body[i + k];
      const l2 = k === 1 ? lo : 0x80, h2 = k === 1 ? hi : 0xbf;
      if (c === undefined || c < l2 || c > h2) { ff.push(F("E017", null, null, null, null, { byte: i + (bom ? 3 : 0) })); return [null, ff, bom]; }
    }
    i += need + 1;
  }
  return [new TextDecoder("utf-8", { ignoreBOM: true }).decode(body), ff, bom];
}

export function validate(data, settings0 = {}, engine = {}) {
  const settings = { ...settings0 };
  if (typeof data === "string") data = new TextEncoder().encode(data);
  let fmt = settings.format || "auto";
  const [text, fileFindings, bom] = decode(data);
  if (text !== null && fmt === "auto") fmt = detectFormat(text);
  settings.format = fmt;
  if (!FORMATS.includes(fmt) && fmt !== "auto") throw new Error("unknown format: " + fmt);
  let records = [];
  const outRecords = [], repairs = [];
  if (bom) repairs.push({ record_id: null, span_index: null, old: null, new: null, reason_code: "E018", confidence: "high", action: "remove_bom" });
  if (text !== null) records = parse(text, fmt, settings);
  let nSpans = 0, nValid = 0;
  for (const rec of records) {
    const [fs, reps, conv, valid] = checkRecord(rec, bom);
    fs.sort(sortKey);
    repairs.push(...reps);
    nSpans += rec.spans.length;
    nValid += valid;
    outRecords.push({ id: rec.id, line: rec.line, text: rec.text, offset_unit: rec.offset_unit, normalization_declared: rec.normalization_declared,
      findings: fs.map(finish), span_count: rec.spans.length, valid_span_count: valid, spans: rec.spans.map((s) => ({ ...s })), conversion_map: conv });
  }
  const all = [...fileFindings.map(finish), ...outRecords.flatMap((r) => r.findings)];
  const byCode = {}, bySev = { error: 0, warning: 0, info: 0 };
  for (const f of all) { byCode[f.code] = (byCode[f.code] || 0) + 1; bySev[f.severity]++; }
  const sortedCodes = {};
  for (const k of Object.keys(byCode).sort()) sortedCodes[k] = byCode[k];
  const st = {};
  for (const k of SETTING_KEYS) st[k] = settings[k] ?? null;
  const report = {
    tool: "arabic-ner-validator", validator_version: VERSION, report_version: 1,
    engine: { language: "javascript", unicode_normalization: engine.unicode || null, grapheme_segmentation: "Intl.Segmenter" },
    settings: st, settings_hash: settingsHash(settings),
    input: { format: fmt, bytes: data.length, sha256: sha256(data), records: records.length },
    summary: { records: records.length, records_with_errors: outRecords.filter((r) => r.findings.some((f) => f.severity === "error")).length,
      spans: nSpans, valid_spans: nValid, by_severity: bySev, by_code: sortedCodes },
    file_findings: fileFindings.map(finish), records: outRecords,
    suggested_export: repairs.length ? { audit_diff: repairs } : null,
  };
  return { report, records, repairs };
}

export function shareReport(report) {
  const out = {};
  for (const k of ["tool", "validator_version", "report_version", "engine", "settings_hash", "summary"]) out[k] = report[k];
  out.share = true;
  const s = { ...report.settings };
  s.label_set = s.label_set == null ? null : s.label_set.length;
  s.tag_names = s.tag_names == null ? null : s.tag_names.length;
  out.settings = s;
  out.input = { format: report.input.format, bytes: report.input.bytes, records: report.input.records };
  const strip = (f) => ({ code: f.code, severity: f.severity, span_index: f.span_index, start: f.start, end: f.end, kind: f.kind });
  out.file_findings = report.file_findings.map(strip);
  out.records = report.records.map((r) => ({ id: r.id, line: r.line, offset_unit: r.offset_unit, span_count: r.span_count, valid_span_count: r.valid_span_count, findings: r.findings.map(strip), conversion_map: r.conversion_map }));
  const se = report.suggested_export;
  out.suggested_export = se === null ? null : { audit_diff: se.audit_diff.map((d) => { const o = { ...d }; delete o.label; return o; }) };
  return out;
}

function csvCell(v) {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n\r]/.test(s) ? '"' + s.split('"').join('""') + '"' : s;
}

export function csvReport(report) {
  const rows = [["record_id", "line", "span_index", "code", "severity", "kind", "start", "end", "message_en"]];
  for (const f of report.file_findings) rows.push(["", "", "", f.code, f.severity, f.kind || "", "", "", f.message_en]);
  for (const r of report.records) for (const f of r.findings) rows.push([r.id, r.line ?? "", f.span_index ?? "", f.code, f.severity, f.kind || "", f.start ?? "", f.end ?? "", f.message_en]);
  return rows.map((r) => r.map(csvCell).join(",")).join("\n") + "\n";
}
