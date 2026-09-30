"""Resolve a game title to a Steam appid, for cover art only.

Matching is deliberately strict: a candidate counts only if its name is
EQUAL to the Debug title once both are normalised. Measured against 40 real
titles from issues 15-17, that resolves 92% of them and every single match
was exact -- so loosening to a similarity threshold would buy nothing and
start pairing indie games with the wrong store page. A miss renders the
magazine cover instead, which is never wrong.
"""
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import cache
import config
import fetch

SEARCH = "https://store.steampowered.com/api/storesearch/?"
STORE = "https://store.steampowered.com/app/%d/"

# The legacy flat CDN path. It is the nicest asset (460x215, ~50KB) but it is
# NOT populated for every app -- measured across issue 17, roughly half of the
# resolved appids 404 here. So it is checked, never assumed.
LEGACY_HEADER = "https://cdn.cloudflare.steamstatic.com/steam/apps/%d/header.jpg"

# Searching "Teeto" happily returns "Teeto Soundtrack" first. These are
# never what a review of a game refers to, unless the Debug title says so.
NOISE = (
    "soundtrack", "ost", " demo", "artbook", "art book", "dlc", "season pass",
    "expansion", "bundle", "upgrade", "edition upgrade", "digital deluxe",
)

_MISS = "__miss__"


def normalise(s):
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[‘’'`´]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _candidates(term):
    url = SEARCH + urllib.parse.urlencode({"term": term, "l": "en", "cc": "us"})
    return fetch.get_json(url, timeout=20).get("items", [])


def _exists(url):
    req = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.status == 200
    except Exception:
        return False


def _image_for(appid, tiny):
    """Pick an image URL that is known to resolve.

    Newer apps live under store_item_assets/ with a per-asset hash in the
    path, so only the exact capsule the search returned can be constructed --
    header.jpg and the larger capsules 404 in that directory. tiny_image is
    therefore the only universally valid asset, and the bigger legacy header
    is an upgrade to be checked for, not the default.
    """
    legacy = LEGACY_HEADER % appid
    if _exists(legacy):
        return legacy
    return tiny or None


def resolve(title):
    """Return {"appid": int, "image": url} or None. Raises on transport
    failure so the caller can stop the run rather than burning the whole
    backlog into false misses."""
    want = normalise(title)
    if not want:
        return None
    noisy_query = any(n.strip() in title.lower() for n in NOISE)
    best = None
    for it in _candidates(title):
        if it.get("type") != "app" or not it.get("id"):
            continue
        name = it.get("name") or ""
        if not noisy_query and any(n in name.lower() for n in NOISE):
            continue
        if normalise(name) != want:
            continue
        # Prefer the lowest appid: the base game predates its editions.
        if best is None or it["id"] < best["id"]:
            best = it
    if not best:
        return None
    return {"appid": best["id"], "image": _image_for(best["id"], best.get("tiny_image"))}


def art(appid, image):
    return {
        "appid": appid,
        "header": image,
        "store": STORE % appid,
    }


def backfill(items, budget=None, on_progress=None):
    """Resolve art for review/preview items, newest issue first.

    Only reviews and previews get art: an interview's title is a person and a
    feature's is an article headline, so neither has a store page.

    This reads `items` but never writes to them: a published snapshot is
    served by other threads, and adding a key to a dict that json.dumps is
    walking raises. Results land in the cache, and `on_progress` lets the
    caller rebuild and republish a fresh snapshot instead.
    """
    if not config.STEAM_ENABLED:
        return 0

    db = cache.load("steam", {}) or {}
    now = time.time()
    resolved = 0
    pending = []

    for it in items:
        if it["kind"] not in ("review", "preview"):
            continue
        key = normalise(it["title"])
        if not key:
            continue
        rec = db.get(key)
        if isinstance(rec, dict):
            if rec.get("image"):
                continue
            if rec.get("appid"):
                # Matched before, but without a usable image URL -- an entry
                # written before image verification existed. Re-resolve it
                # now rather than waiting out the miss TTL.
                pass
            else:
                # A genuine miss, which expires: previews often run months
                # before a game has a store page at all.
                age_days = (now - rec.get("at", 0)) / 86400.0
                if age_days < config.STEAM_MISS_TTL_DAYS:
                    continue
        pending.append((key, it))

    if not pending:
        return 0

    # De-duplicate: the same game is routinely previewed and then reviewed.
    seen = {}
    for key, it in pending:
        seen.setdefault(key, []).append(it)

    todo = list(seen.items())
    if budget:
        todo = todo[:budget]
    print("[steam] resolving %d new titles" % len(todo), flush=True)

    # Persist as we go. A full backfill is ~12 minutes, and saving only at the
    # end means any restart inside that window throws the whole run away and
    # re-queries Steam from scratch.
    since_save = 0

    for key, group in todo:
        title = group[0]["title"]
        try:
            hit = resolve(title)
        except Exception as e:
            print("[steam] aborting run at %r: %s" % (title, e), flush=True)
            break
        if hit and hit.get("image"):
            db[key] = dict(hit, at=now, title=title)
            resolved += 1
        else:
            db[key] = {"appid": None, "image": None, "at": now, "title": title}

        since_save += 1
        if since_save >= 25:
            cache.save("steam", db)
            since_save = 0
            if on_progress:
                on_progress()
        time.sleep(config.STEAM_DELAY)

    cache.save("steam", db)
    if on_progress:
        on_progress()
    print("[steam] resolved %d/%d" % (resolved, len(todo)), flush=True)
    return resolved


def apply_known(items):
    """Attach art from the cache without any network access."""
    db = cache.load("steam", {}) or {}
    for it in items:
        if it["kind"] not in ("review", "preview"):
            continue
        rec = db.get(normalise(it["title"]))
        if isinstance(rec, dict) and rec.get("appid") and rec.get("image"):
            it["steam"] = art(rec["appid"], rec["image"])
