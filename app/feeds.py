"""Fetch the five Debug feeds and flatten them into one list of items.

Shape notes that the feeds themselves do not make obvious:

  * reviews and previews cover issues 1-17; interviews exist only for issues
    1 and 4, features only for issue 1. The magazine is at issue 20, so the
    newest issues arrive here as cover-art stubs and gain contents weeks later.
  * `steam_id` and `moreinfo_url` are declared in every field_definitions
    block but are null for all 675 entries, so cover art has to be resolved
    elsewhere (steam.py).
  * reviews carry a summary for all 349 entries; previews carry one for 4 of
    326. A preview card is therefore title + studio + platforms and nothing
    more, which is why the UI does not reserve space for preview summaries.
"""
import re

import cache
import config
import fetch

# Jetpack's image CDN fronts teamdebug.com and honours ?w=, which the origin
# ignores: a cover drops from 577KB to 38KB. A shelf of 20 origin covers is
# 11MB, which is not something a dashboard widget gets to do.
PHOTON = "https://i0.wp.com/"


def _thumb(url, width=300):
    if not url:
        return None
    return PHOTON + url.split("://", 1)[-1] + "?w=%d" % width


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [x for x in v if x]
    return [v]


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _issue_url(raw, number):
    # issue_url is the debu.gg shortener; the purchase page is the canonical
    # place to check availability, so prefer it when we have the number.
    if number:
        return "%s/issue/%d" % (config.BASE, number)
    return raw


def _base_item(kind, raw, title, summary, byline, date):
    number = raw.get("issue")
    return {
        "uid": raw.get("id") or "%s-%s-%s" % (kind, number, _slug(title)),
        "kind": kind,
        "title": title,
        "issue": number,
        "issue_title": raw.get("issue_title"),
        "issue_url": _issue_url(raw.get("issue_url"), number),
        "page": raw.get("page"),
        "section": raw.get("section"),
        "summary": summary,
        "byline": byline,
        "date": date,
        "developer": _as_list(raw.get("developer")),
        "publisher": _as_list(raw.get("publisher")),
        "platforms": [],
        "score": None,
        "scale": None,
        "score_label": None,
        "normalised": None,
        "steam": None,
    }


def _reviews(d):
    out = []
    for r in d.get("reviews", []):
        it = _base_item(
            "review", r, r.get("title"), r.get("review_summary"),
            r.get("reviewer"), r.get("review_date"),
        )
        # platform_reviewed is the single format Debug tested, not the game's
        # full platform list -- previews are the ones that carry a real list.
        it["platforms"] = _as_list(r.get("platform_reviewed"))
        it["score"] = r.get("score")
        it["scale"] = r.get("scale")
        it["score_label"] = r.get("score_label")
        it["normalised"] = r.get("normalised_score")
        it["release_date"] = r.get("release_date")
        out.append(it)
    return out


def _previews(d):
    out = []
    for p in d.get("previews", []):
        it = _base_item(
            "preview", p, p.get("title"), p.get("preview_summary"),
            p.get("writer"), None,
        )
        it["platforms"] = _as_list(p.get("platforms"))
        it["has_qa"] = bool(p.get("has_qa"))
        out.append(it)
    return out


def _interviews(d):
    out = []
    for v in d.get("interviews", []):
        who = ", ".join(_as_list(v.get("interviewee"))) or "Interview"
        it = _base_item(
            "interview", v, who, v.get("summary"),
            ", ".join(_as_list(v.get("interviewer"))), v.get("interview_date"),
        )
        it["related_games"] = _as_list(v.get("related_games"))
        out.append(it)
    return out


def _features(d):
    out = []
    for f in d.get("features", []):
        it = _base_item(
            "feature", f, f.get("title"), f.get("summary"),
            ", ".join(_as_list(f.get("writer"))), f.get("feature_date"),
        )
        it["related_games"] = _as_list(f.get("related_games"))
        out.append(it)
    return out


def _issues(d):
    out = []
    for i in d.get("issues", []):
        urls = i.get("cover_image_urls") or {}
        lo = urls.get("150dpi")
        out.append({
            "number": i.get("issue_number"),
            "id": i.get("issue_id"),
            "title": i.get("title"),
            "date": i.get("publication_date"),
            "pages": i.get("page_count"),
            "purchase_url": i.get("purchase_url"),
            "cover_title": (i.get("cover") or {}).get("title"),
            "cover_thumb": _thumb(lo, 300),
            "cover_large": _thumb(lo, 900),
            "cover_origin": lo,
            # `stub` means Debug has announced the issue and published its
            # cover but has not indexed what is inside it yet.
            "indexed": i.get("status") == "fully_indexed",
        })
    out.sort(key=lambda x: x["number"] or 0)
    return out


PARSERS = {
    "reviews": _reviews,
    "previews": _previews,
    "interviews": _interviews,
    "features": _features,
}


def refresh():
    """Fetch all five feeds. A feed that fails keeps its previous cached copy
    rather than emptying the widget."""
    prev = cache.load("feeds", {}) or {}
    raw = dict(prev)
    errors = {}
    for name, path in config.FEEDS.items():
        try:
            raw[name] = fetch.get_json(config.BASE + path)
        except Exception as e:
            errors[name] = str(e)
            print("[feeds] %s failed: %s" % (name, e), flush=True)
    if raw:
        cache.save("feeds", raw)
    return build(raw), errors, raw


def build(raw):
    items = []
    for name, parser in PARSERS.items():
        if name in raw:
            try:
                items.extend(parser(raw[name]))
            except Exception as e:
                print("[feeds] parse %s failed: %s" % (name, e), flush=True)

    issues = _issues(raw.get("issues", {}))
    by_number = {i["number"]: i for i in issues}

    # An item's own date field is empty for previews, so fall back to the
    # issue's publication date -- that is what "newest" has to mean here.
    for it in items:
        iss = by_number.get(it["issue"])
        if iss:
            it["issue_date"] = iss["date"]
            it["cover_thumb"] = iss["cover_thumb"]
            if not it.get("date"):
                it["date"] = iss["date"]

    counts = {}
    for it in items:
        c = counts.setdefault(it["issue"], {})
        c[it["kind"]] = c.get(it["kind"], 0) + 1
    for i in issues:
        i["counts"] = counts.get(i["number"], {})
        i["has_contents"] = bool(i["counts"])

    items.sort(key=lambda x: (x["issue"] or 0, x["page"] or 0), reverse=True)
    return {
        "issues": issues,
        "items": items,
        "meta": {
            "publication": (raw.get("issues", {}) or {}).get("publication", {}),
            "feed_updated": {
                k: (raw.get(k, {}) or {}).get("last_updated")
                for k in config.FEEDS
            },
        },
    }
