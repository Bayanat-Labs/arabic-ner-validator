// Measures JavaScript String indices and Intl.Segmenter grapheme clusters on the probes.
// Runs in Node (node matrix/measure_js.mjs) and in a browser page (see matrix/measure_browser.py).
export function measure(probes) {
  const seg = new Intl.Segmenter("und", { granularity: "grapheme" });
  return probes.map((p) => {
    const t = p.text;
    const start = t.indexOf(p.target);
    const end = start + p.target.length;
    const bounds = [0];
    let pos = 0;
    for (const g of seg.segment(t)) { pos += g.segment.length; bounds.push(pos); }
    return {
      probe_id: p.probe_id,
      js_string: { start, end, length: t.length },
      code_points_before_start: Array.from(t.slice(0, start)).length,
      intl_segmenter: { start: bounds.indexOf(start), end: bounds.indexOf(end), length: bounds.length - 1 },
      normalised_length: { NFC: Array.from(t.normalize("NFC")).length, NFKC: Array.from(t.normalize("NFKC")).length },
    };
  });
}
