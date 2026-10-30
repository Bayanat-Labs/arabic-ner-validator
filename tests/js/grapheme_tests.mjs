// Intl.Segmenter on the derived GraphemeBreakTest cases; prints {version: {cases, pass}} as JSON.
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
const here = path.dirname(fileURLToPath(import.meta.url));
const out = { runtime: "node " + process.versions.node, icu: process.versions.icu, unicode: process.versions.unicode };
for (const v of ["16.0.0", "17.0.0"]) {
  const d = JSON.parse(fs.readFileSync(path.join(here, "..", "data", `grapheme_break_${v}.json`), "utf8"));
  const seg = new Intl.Segmenter("und", { granularity: "grapheme" });
  let ok = 0;
  for (const [cps, b] of d.cases) {
    const got = [0];
    let pos = 0;
    for (const g of seg.segment(String.fromCodePoint(...cps))) { pos += Array.from(g.segment).length; got.push(pos); }
    if (JSON.stringify(got) === JSON.stringify(b)) ok++;
  }
  out[v] = { cases: d.cases.length, pass: ok };
}
console.log(JSON.stringify(out));
