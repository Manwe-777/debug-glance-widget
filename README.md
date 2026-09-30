# Debug → Glance widget

A dependency-free HTTP server that turns [Debug magazine](https://www.teamdebug.com)'s
public JSON feeds into a browsable, image-led view of what is actually inside
each issue — so you can spot a game worth reading about without reading the
whole magazine.

It serves two renderings of the same data:

- **`/?compact=1`** — a dashboard widget: a shelf of issue covers and the
  newest indexed issue's reviews, ranked by score.
- **`/`** — the full browser: cover shelf, search, kind/score filters, a card
  grid with cover art, and a detail panel per item.

Stdlib-only Python. No `pip install`, no framework, no credentials.

---

## What the feeds actually contain

Worth knowing before you trust the widget, because the feeds are less complete
than their schemas suggest.

| feed | entries | issues covered |
|---|---|---|
| `reviews.json` | 349 | 1–17 |
| `previews.json` | 326 | 1–17 |
| `interviews.json` | 9 | 1 and 4 only |
| `features.json` | 2 | issue 1 only |
| `issues.json` | 20 issues | 1–20, all with cover art |

Three things follow from that:

- **The contents lag the magazine by about a month.** Debug is at issue 20;
  the content feeds stop at 17. Newer issues arrive as cover-and-date stubs
  and gain contents weeks later. The shelf dims those and labels them
  *not indexed*, and compact mode says so explicitly. This widget is a
  "what did I miss" browser, not a new-issue alert.
- **Reviews carry a summary; previews essentially do not.** All 349 reviews
  have one. 4 of 326 previews do. A preview card is therefore title, studio,
  platforms and page number, and the detail panel says why it stops there.
- **There is no artwork and no PDF in any feed.** `steam_id` and
  `moreinfo_url` are declared in every `field_definitions` block and are null
  for all 675 entries. The only official images are issue covers; the only
  canonical link per item is the issue page.

The per-issue contents indexes (`/indexes/issues/NNN.json`) are richer still —
76 entries for issue 12, with prices and per-item summaries — but only issue
12 actually exists, so this widget does not depend on them.

## Two upstream quirks it works around

**Cloudflare.** `teamdebug.com` 403s a default `urllib`/`curl` User-Agent. A
normal browser UA is the entire fix — no cookie, no FlareSolverr. It is set in
`config.py` and applied in one place (`fetch.py`) so no call site can forget it.

**Cover weight.** The published covers are 1240×1754 and ~577KB each; a shelf
of 20 would be 11MB. The origin ignores resize parameters, but Jetpack's image
CDN fronts the site and honours `?w=`, which brings a cover to 38KB. Thumbnails
therefore go through `i0.wp.com`.

## Cover art

The feeds have none, so art is resolved against Steam's public `storesearch`
endpoint and cached permanently.

**Matching is exact, not fuzzy.** A candidate counts only if its name equals
the Debug title once both are normalised (case, punctuation and `&`/`and`
folded). Across 40 titles from issues 15–17 that resolves 92%, and every match
was exact — so a similarity threshold would add nothing and start pairing
indie games with the wrong store page. A miss renders the issue cover instead,
which is never wrong.

**Image URLs are verified, not constructed.** The old flat CDN path
(`/steam/apps/<id>/header.jpg`) is the nicest asset at 460×215, but it is
missing for roughly half of these appids — newer apps live under
`store_item_assets/` with a per-asset hash in the path, where only the exact
capsule the search returned resolves and `header.jpg` 404s. So the resolver
checks the legacy header with a `HEAD` and falls back to the search result's
own `tiny_image`, storing whichever works. The front end additionally degrades
to the cover treatment if a stored URL ever dies.

Set `STEAM_ENABLED=0` to skip all of this and run on magazine covers alone.

## Running it

```bash
git clone <this-repo-url> debug-glance-widget
cd debug-glance-widget
docker compose up -d --build
```

That is the whole setup — there is nothing to configure. It listens on
**`8092`**; `cp .env.example .env` if you want to change the port or the
refresh interval.

First start fetches the feeds (~3s) and serves immediately, then backfills
cover art in the background at roughly one title every 1.2s. Art appears as it
resolves; the cache is on a volume, so this happens once and survives restarts.

## Adding it to Glance

Both entries point at the same container. Glance renders `custom-api`
templates server-side and needs a `url` to poll even when the template is just
an iframe, which is what `/api/stats` is for.

Widget, in the Dashboard's `full` column under Reddit:

```yaml
- type: custom-api
  title: Debug
  url: http://<your-server>:8092/api/stats
  cache: 30s
  template: |
    <iframe src="http://<your-server>:8092/?compact=1" width="100%" height="390px"
            frameborder="0" style="display: block;"></iframe>
```

Full page:

```yaml
- name: Debug
  columns:
    - size: full
      widgets:
        - type: custom-api
          title: Debug
          url: http://<your-server>:8092/api/stats
          cache: 30s
          template: |
            <iframe src="http://<your-server>:8092" width="100%" height="1300px"
                    frameborder="0" style="display: block;"></iframe>
```

The widget inherits Glance's active theme — light, dark and custom presets —
through the same `postMessage` contract the bookmarks and reddit widgets use,
so `glance-theme-broadcast.js` must be in your `document.head`.

## Endpoints

| path | purpose |
|---|---|
| `/` | full browser |
| `/?compact=1` | dashboard widget |
| `/?issue=17` | full browser filtered to one issue |
| `/api/data` | the normalised snapshot (gzipped, ~83KB) |
| `/api/stats` | counts and freshness, for Glance to poll |
| `/healthz` | container healthcheck |

## Configuration

| variable | default | meaning |
|---|---|---|
| `WIDGET_PORT` | `8092` | host port |
| `REFRESH_HOURS` | `12` | feed refresh interval |
| `STEAM_ENABLED` | `1` | resolve Steam cover art |
| `STEAM_DELAY` | `1.2` | seconds between Steam calls |
| `STEAM_MISS_TTL_DAYS` | `30` | before retrying a title Steam could not find |

## How it is put together

```
app/
  config.py      env parsing; every value has a working default
  fetch.py       the only place outbound HTTP happens
  cache.py       atomic disk-backed JSON
  feeds.py       fetch the five feeds, flatten to one item list
  steam.py       title -> verified art URL, exact matching only
  scheduler.py   background refresh; requests never trigger a fetch
  server.py      routes and static files
  public/        index.html, styles.css, script.js
```

The widget never fetches on a request: Glance can poll as often as it likes and
always reads an in-memory snapshot. On boot that snapshot comes off disk before
the first network call, so a restart is invisible even if teamdebug.com is slow.
A feed that fails keeps its previous cached copy rather than emptying the view.
