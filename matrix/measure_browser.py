#!/usr/bin/env python3
"""Run matrix/measure_js.js in headless Chromium (Playwright) on the probes; writes
matrix/evidence/chromium_measurements.json. The page is served from 127.0.0.1 and makes no other request."""
import functools
import http.server
import json
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = """<!doctype html><meta charset="utf-8"><script type="module">
import { measure } from "./measure_js.js";
const probes = await (await fetch("./evidence/probes.json")).json();
window.__result = { userAgent: navigator.userAgent, probes: measure(probes) };
</script>"""


def main():
    with open(os.path.join(HERE, "_measure.html"), "w", encoding="utf-8") as fh:
        fh.write(PAGE)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=HERE)
    handler.log_message = lambda *a, **k: None
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page()
            page.goto("http://127.0.0.1:%d/_measure.html" % httpd.server_address[1])
            page.wait_for_function("window.__result !== undefined")
            res = page.evaluate("window.__result")
            res["browser"] = "chromium " + b.version
            b.close()
    finally:
        httpd.shutdown()
        os.remove(os.path.join(HERE, "_measure.html"))
    with open(os.path.join(HERE, "evidence", "chromium_measurements.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print("ok", res["browser"])


if __name__ == "__main__":
    main()
