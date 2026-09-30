"""Background refresh.

The widget never fetches on a request. Glance can poll as often as it likes;
it always reads the in-memory snapshot, which this thread replaces.
"""
import threading
import time

import cache
import config
import feeds
import steam

_state = {
    "data": {"issues": [], "items": [], "meta": {}},
    "updated_at": None,
    "errors": {},
    "steam_pending": None,
}
_lock = threading.Lock()


def snapshot():
    with _lock:
        return _state["data"], _state["updated_at"], _state["errors"]


def _publish(data, errors=None):
    with _lock:
        _state["data"] = data
        _state["updated_at"] = time.time()
        if errors is not None:
            _state["errors"] = errors


def _boot():
    """Serve whatever is on disk before the first network call, so a restart
    is invisible even if teamdebug.com is slow or down."""
    raw = cache.load("feeds")
    if not raw:
        return False
    data = feeds.build(raw)
    steam.apply_known(data["items"])
    _publish(data)
    print("[boot] served %d items from cache" % len(data["items"]), flush=True)
    return True


def _cycle(first):
    data, errors, raw = feeds.refresh()
    steam.apply_known(data["items"])
    _publish(data, errors)

    def republish():
        """Build a NEW snapshot and swap it in. Never mutate a published one:
        request threads may be serialising it."""
        fresh = feeds.build(raw)
        steam.apply_known(fresh["items"])
        _publish(fresh, errors)

    # Art resolution is slow by design (~1.2s/title), so the text is published
    # first and covers fill in as they resolve. The first run has ~670 titles;
    # cap it so a cold start is not a 15-minute crawl, and let later cycles
    # finish the tail.
    steam.backfill(data["items"], budget=150 if first else None,
                   on_progress=republish)


def run():
    first = not _boot()
    while True:
        try:
            _cycle(first)
            first = False
        except Exception as e:
            print("[scheduler] cycle failed: %s" % e, flush=True)
        time.sleep(max(1, config.REFRESH_HOURS) * 3600)


def start():
    t = threading.Thread(target=run, name="refresh", daemon=True)
    t.start()
    return t
