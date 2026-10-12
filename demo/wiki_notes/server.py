"""Serve the notes demo. Run from the repo root:

    python3.12 demo/wiki_notes/server.py
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from demo.wiki_notes.pipeline import decide, load_samples, read_state, save  # noqa: E402

PAGE = Path(__file__).resolve().parent / "page.html"
PORT = 8091


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        sys.stderr.write("%s %s\n" % (self.address_string(), format % args))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: object) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if self.path == "/api/inbox":
            self._json(200, {"texts": load_samples()})
            return
        if self.path == "/api/state":
            state = read_state()
            self._json(200, state or {"ready": False, "messages": [], "claims": [], "links": [], "places": [], "topics": [], "scored": [], "reviews": []})
            return
        self._json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        if self.path == "/api/run":
            self._json(200, save())
            return
        if self.path == "/api/decision":
            try:
                body = json.loads(raw.decode() or "{}")
            except json.JSONDecodeError:
                self._json(400, {"error": "Send approved: true or false."})
                return
            if not isinstance(body.get("approved"), bool) or not isinstance(body.get("id"), str):
                self._json(400, {"error": "Send approved: true or false."})
                return
            try:
                self._json(200, decide(body["id"], body["approved"]))
            except ValueError as error:
                self._json(400, {"error": str(error)})
            return
        self._json(404, {"error": "Not found"})


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"wiki notes demo on http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
