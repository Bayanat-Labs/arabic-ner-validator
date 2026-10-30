// Runs the validator off the main thread. Receives {bytes, settings}, returns {ok, report}.
import { validate } from "./validator.js";

self.onmessage = (e) => {
  try {
    const { report } = validate(new Uint8Array(e.data.bytes), e.data.settings);
    self.postMessage({ ok: true, report });
  } catch (err) {
    self.postMessage({ ok: false, error: String((err && err.message) || err) });
  }
};
