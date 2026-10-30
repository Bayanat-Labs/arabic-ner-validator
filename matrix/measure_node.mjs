import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { measure } from "./measure_js.js";
const here = path.dirname(fileURLToPath(import.meta.url));
const probes = JSON.parse(fs.readFileSync(path.join(here, "evidence", "probes.json"), "utf8"));
const out = { runtime: "node " + process.versions.node, v8: process.versions.v8, icu: process.versions.icu, unicode: process.versions.unicode, probes: measure(probes) };
fs.writeFileSync(path.join(here, "evidence", "node_measurements.json"), JSON.stringify(out, null, 1) + "\n");
console.log("ok", out.probes.length);
