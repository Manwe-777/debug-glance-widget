"""Runtime configuration. Every value has a working default: the widget runs
with no .env at all, because none of the Debug feeds need credentials."""
import os


def _int(name, default):
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _float(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _bool(name, default=True):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off", "")


PORT = _int("PORT", 8080)
CACHE_DIR = os.environ.get("CACHE_DIR", "/data")
HTTP_TIMEOUT = _int("HTTP_TIMEOUT", 30)

BASE = "https://www.teamdebug.com"

# teamdebug.com sits behind Cloudflare, which 403s a default urllib/curl
# User-Agent. A normal browser UA is the whole bypass -- no cookie, no
# FlareSolverr. Keep this looking like a browser or every fetch fails.
USER_AGENT = os.environ.get("USER_AGENT") or (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

# Debug ships an issue roughly monthly and backfills its contents into the
# feeds weeks after that, so polling faster than twice a day buys nothing.
REFRESH_HOURS = _int("REFRESH_HOURS", 12)

# Steam cover art. Titles are matched EXACTLY after normalisation (see
# steam.py); a near-miss resolves to nothing rather than to the wrong game.
STEAM_ENABLED = _bool("STEAM_ENABLED", True)
# Steam's storesearch endpoint is unauthenticated and undocumented. Space the
# requests so a first-run backfill of ~670 titles never resembles a scrape.
STEAM_DELAY = _float("STEAM_DELAY", 1.2)
# How long before a title that Steam could not find is retried. Games are
# often covered in previews months before they get a store page.
STEAM_MISS_TTL_DAYS = _int("STEAM_MISS_TTL_DAYS", 30)

FEEDS = {
    "reviews": "/feeds/reviews.json",
    "previews": "/feeds/previews.json",
    "interviews": "/feeds/interviews.json",
    "features": "/feeds/features.json",
    "issues": "/feeds/issues.json",
}
