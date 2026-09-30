"""Single place where outbound HTTP happens, so the browser User-Agent that
gets us past Cloudflare can never be forgotten at a call site."""
import gzip
import json
import urllib.error
import urllib.request

import config


def get_json(url, timeout=None):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": config.USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip",
            "Referer": config.BASE + "/",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout or config.HTTP_TIMEOUT) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))
