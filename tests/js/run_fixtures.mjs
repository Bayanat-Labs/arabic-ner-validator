// Run the browser port on fixture files and print one JSON report per fixture (JSON Lines).
//   node tests/js/run_fixtures.mjs fixtures/dev/fixtures.jsonl [more.jsonl ...]
import fs from "fs";
import { validate } from "../../web/validator.js";

for (const path of process.argv.slice(2)) {
  for (const line of fs.readFileSync(path, "utf8").split("\n")) {
    if (!line.trim()) continue;
    const fx = JSON.parse(line);
    const settings = { ...(fx.options || {}), format: fx.format };
    const { report, repairs } = validate(new TextEncoder().encode(fx.input_payload), settings, { unicode: process.versions.unicode });
    process.stdout.write(JSON.stringify({ fixture_id: fx.fixture_id, report, repairs }) + "\n");
  }
}
