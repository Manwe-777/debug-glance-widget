"""Disk-backed JSON cache.

The point is that a restart costs nothing: the feeds and the resolved Steam
appids come back off disk, so the widget serves instantly and neither
teamdebug.com nor Steam sees a burst of traffic on every `docker compose up`.
"""
import json
import os
import tempfile
import threading

import config

_lock = threading.Lock()


def _path(name):
    return os.path.join(config.CACHE_DIR, name + ".json")


def load(name, default=None):
    try:
        with open(_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save(name, data):
    """Atomic write -- a crash mid-save must not leave a truncated file that
    poisons the cache for every later start."""
    with _lock:
        try:
            os.makedirs(config.CACHE_DIR, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=config.CACHE_DIR, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, separators=(",", ":"))
                os.replace(tmp, _path(name))
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except OSError as e:
            print("[cache] write failed for %s: %s" % (name, e), flush=True)
