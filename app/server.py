"""HTTP surface.

  GET /            full browser (cover shelf, search, filters, detail panel)
  GET /?compact=1  dashboard widget rendering of the same data
  GET /api/data    the normalised snapshot
  GET /api/stats   small summary, so Glance's custom-api has a URL to poll
  GET /healthz     container healthcheck
"""
import gzip
import json
import mimetypes
import os
import posixpath
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import config
import scheduler

PUBLIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")


class Handler(BaseHTTPRequestHandler):
    server_version = "debug-glance-widget"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # the scheduler's lines are the useful ones; access logs are noise

    def _send(self, code, body, ctype, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        headers = dict(extra or {})
        # The full snapshot is ~530KB of very repetitive JSON; gzip takes it
        # under 100KB, which matters because the dashboard iframe refetches it
        # on every visit.
        if (len(body) > 1024
                and "gzip" in self.headers.get("Accept-Encoding", "")
                and "Content-Encoding" not in headers):
            body = gzip.compress(body, 6)
            headers["Content-Encoding"] = "gzip"
            headers["Vary"] = "Accept-Encoding"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json; charset=utf-8",
                   {"Cache-Control": "no-store"})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/healthz":
            return self._send(200, "ok", "text/plain; charset=utf-8")

        if path == "/api/data":
            data, updated, errors = scheduler.snapshot()
            return self._json(200, {
                "issues": data["issues"],
                "items": data["items"],
                "meta": data["meta"],
                "updated_at": updated,
                "errors": errors,
            })

        if path == "/api/stats":
            # Glance's custom-api widget needs a url to poll even when the
            # template only embeds an iframe; this is the cheapest valid one.
            data, updated, errors = scheduler.snapshot()
            issues = data["issues"]
            latest = next((i for i in reversed(issues) if i["has_contents"]), None)
            return self._json(200, {
                "status": "ok" if data["items"] else "empty",
                "issues": len(issues),
                "items": len(data["items"]),
                "latest_issue": (latest or {}).get("number"),
                "newest_announced": issues[-1]["number"] if issues else None,
                "with_art": sum(1 for i in data["items"] if i.get("steam")),
                "updated_at": updated,
                "errors": errors,
            })

        if path in ("/", "/index.html"):
            return self._static("index.html", cache_seconds=0)

        return self._static(path.lstrip("/"))

    def _static(self, rel, cache_seconds=300):
        # Normalise first: a request for /../config.py must not escape public/.
        rel = posixpath.normpath("/" + rel).lstrip("/")
        full = os.path.join(PUBLIC, rel)
        if not os.path.abspath(full).startswith(PUBLIC + os.sep):
            return self._send(404, "not found", "text/plain; charset=utf-8")
        try:
            with open(full, "rb") as f:
                body = f.read()
        except OSError:
            return self._send(404, "not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        cc = "public, max-age=%d" % cache_seconds if cache_seconds else "no-cache"
        self._send(200, body, ctype, {"Cache-Control": cc})


def main():
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    scheduler.start()
    srv = ThreadingHTTPServer(("0.0.0.0", config.PORT), Handler)
    print("[server] listening on :%d" % config.PORT, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
