(function () {
  'use strict';

  var qs = new URLSearchParams(location.search);
  var COMPACT = qs.get('compact') === '1';
  var root = document.getElementById('root');
  var detail = document.getElementById('detail');

  var DATA = { issues: [], items: [], meta: {} };
  var state = {
    issue: qs.get('issue') ? parseInt(qs.get('issue'), 10) : null,
    kind: qs.get('kind') || 'all',
    q: '',
    minScore: 0
  };

  var KINDS = [
    { key: 'all', label: 'All' },
    { key: 'review', label: 'Reviews' },
    { key: 'preview', label: 'Previews' },
    { key: 'interview', label: 'Interviews' },
    { key: 'feature', label: 'Features' }
  ];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function el(html) {
    var t = document.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  // Debug scores out of 5 and uses the full scale, so the ramp is tuned to
  // that: 3/5 is a fair game, not a bad one.
  function scoreClass(norm) {
    if (norm == null) return '';
    if (norm >= 90) return 's-high';
    if (norm >= 75) return 's-good';
    if (norm >= 55) return 's-mid';
    return 's-low';
  }
  function scoreVar(norm) {
    if (norm >= 90) return 'var(--score-high)';
    if (norm >= 75) return 'var(--score-good)';
    if (norm >= 55) return 'var(--score-mid)';
    return 'var(--score-low)';
  }

  function studio(it) {
    var d = (it.developer || []).join(', ');
    var p = (it.publisher || []).join(', ');
    return d || p || '';
  }

  function fmtDate(s) {
    if (!s) return '';
    var d = new Date(s + (s.length === 10 ? 'T00:00:00' : ''));
    if (isNaN(d)) return s;
    return d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
  }

  function fullUrl(params) {
    var u = new URL(location.href);
    u.searchParams.delete('compact');
    Object.keys(params || {}).forEach(function (k) {
      if (params[k] == null) u.searchParams.delete(k);
      else u.searchParams.set(k, params[k]);
    });
    return u.toString();
  }

  /* ── filtering ─────────────────────────────────────────────── */

  function filtered() {
    var q = state.q.trim().toLowerCase();
    return DATA.items.filter(function (it) {
      if (state.issue && it.issue !== state.issue) return false;
      if (state.kind !== 'all' && it.kind !== state.kind) return false;
      if (state.minScore && (it.normalised == null || it.normalised < state.minScore)) return false;
      if (!q) return true;
      var hay = [it.title, studio(it), it.summary, it.byline,
                 (it.related_games || []).join(' ')].join(' ').toLowerCase();
      return hay.indexOf(q) !== -1;
    });
  }

  /* ── rendering ─────────────────────────────────────────────── */

  function shelfHtml() {
    var covers = DATA.issues.slice().reverse().map(function (i) {
      var cls = 'cover' + (i.has_contents ? '' : ' is-stub') +
                (state.issue === i.number ? ' is-active' : '');
      return '<div class="' + cls + '" data-issue="' + i.number + '" ' +
        'title="' + esc(i.title + (i.cover_title ? ' — ' + i.cover_title : '')) + '">' +
        (i.cover_thumb ? '<img loading="lazy" src="' + esc(i.cover_thumb) + '" alt="' + esc(i.title) + '">' : '') +
        '<div class="cover-meta"><div class="cover-num">#' + i.number + '</div>' +
        '<div class="cover-sub">' + esc(fmtDate(i.date)) + '</div></div></div>';
    }).join('');
    return '<div class="shelf-wrap"><div class="shelf">' + covers + '</div></div>';
  }

  function controlsHtml() {
    var chips = KINDS.map(function (k) {
      var n = k.key === 'all' ? null : DATA.items.filter(function (i) { return i.kind === k.key; }).length;
      if (n === 0) return '';
      return '<button class="chip' + (state.kind === k.key ? ' is-on' : '') +
        '" data-kind="' + k.key + '">' + k.label + '</button>';
    }).join('');
    var scoreChip = '<button class="chip' + (state.minScore ? ' is-on' : '') +
      '" data-score="' + (state.minScore ? 0 : 80) + '">8+ only</button>';
    var clear = (state.issue || state.kind !== 'all' || state.q || state.minScore)
      ? '<button class="chip chip-clear" data-clear="1">Clear</button>' : '';
    return '<div class="controls">' +
      '<input class="search" id="q" type="search" placeholder="Search games, studios, writers…" value="' + esc(state.q) + '">' +
      '<div class="chips">' + chips + scoreChip + clear + '</div>' +
      '<span class="count" id="count"></span></div>';
  }

  function cardHtml(it) {
    // alt is deliberately empty on art: a 404 must not paint the game title
    // across the card as alt text. data-fallback lets onerror swap the whole
    // art block over to the cover treatment instead.
    var art, cls = 'card-art';
    var fallback = (it.cover_thumb ? '<img loading="lazy" src="' + esc(it.cover_thumb) + '" alt="">' : '') +
                   '<div class="card-fallback-title">' + esc(it.title) + '</div>';
    if (it.steam && it.steam.header) {
      art = '<img loading="lazy" alt="" src="' + esc(it.steam.header) + '" ' +
            'onerror="window.__artFail&amp;&amp;window.__artFail(this)">';
    } else {
      cls += ' is-fallback';
      art = fallback;
    }
    var badge = it.score_label
      ? '<span class="badge ' + scoreClass(it.normalised) + '">' + esc(it.score_label) + '</span>' : '';
    var st = studio(it);
    var summary = it.summary ? '<div class="card-summary">' + esc(it.summary) + '</div>' : '';
    return '<button class="card" data-uid="' + esc(it.uid) + '">' +
      '<div class="' + cls + '" data-fallback="' + esc(encodeURIComponent(fallback)) + '">' +
        '<span class="kind">' + esc(it.kind) + '</span>' + art + badge + '</div>' +
      '<div class="card-body">' +
        '<div class="card-title">' + esc(it.title) + '</div>' +
        (st ? '<div class="card-studio">' + esc(st) + '</div>' : '') +
        summary +
        '<div class="card-foot"><span>Issue ' + it.issue + '</span>' +
          (it.page ? '<span class="dot">·</span><span>p' + it.page + '</span>' : '') +
          (it.platforms && it.platforms.length ? '<span class="dot">·</span><span>' + esc(it.platforms.slice(0, 3).join(', ')) + '</span>' : '') +
        '</div>' +
      '</div></button>';
  }

  function renderFull() {
    var list = filtered();
    root.innerHTML = shelfHtml() + controlsHtml() +
      (list.length
        ? '<div class="grid">' + list.map(cardHtml).join('') + '</div>'
        : '<div class="empty">Nothing matches that.</div>');
    var c = document.getElementById('count');
    if (c) c.textContent = list.length + ' item' + (list.length === 1 ? '' : 's');
    var q = document.getElementById('q');
    if (q) {
      q.addEventListener('input', debounce(function () {
        state.q = q.value;
        renderFull();
        var n = document.getElementById('q');
        if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); }
      }, 180));
    }
  }

  function renderCompact() {
    // Newest issue that actually has contents -- the newest announced issue
    // is usually a cover-only stub.
    var latest = null;
    for (var i = DATA.issues.length - 1; i >= 0; i--) {
      if (DATA.issues[i].has_contents) { latest = DATA.issues[i]; break; }
    }
    if (!latest) {
      root.innerHTML = shelfHtml() + '<div class="empty">No indexed issues yet.</div>';
      bindShelf();
      return;
    }

    var rows = DATA.items
      .filter(function (it) { return it.issue === latest.number && it.kind === 'review'; })
      .sort(function (a, b) { return (b.normalised || 0) - (a.normalised || 0); })
      .slice(0, 7);

    var newest = DATA.issues[DATA.issues.length - 1];
    var behind = newest && newest.number > latest.number
      ? '<div class="stale">#' + newest.number + ' is out — contents not indexed yet</div>' : '';

    root.innerHTML = shelfHtml() +
      '<div class="c-head"><span class="c-title">Issue ' + latest.number + '</span>' +
      '<span class="c-sub">' + esc(fmtDate(latest.date)) +
      (latest.counts.review ? ' · ' + latest.counts.review + ' reviews' : '') + '</span>' +
      '<a class="c-more" href="' + esc(fullUrl({ issue: latest.number })) + '" target="_blank" rel="noopener">browse all →</a></div>' +
      '<div class="c-list">' + rows.map(function (it) {
        return '<a class="c-row" href="' + esc(fullUrl({ issue: it.issue, item: it.uid })) + '" target="_blank" rel="noopener">' +
          (it.score_label
            ? '<span class="c-score" style="background:' + scoreVar(it.normalised) + '">' + esc(it.score_label.split('/')[0]) + '</span>'
            : '<span class="c-score" style="background:var(--color-separator)">–</span>') +
          (it.steam && it.steam.header
            ? '<img class="c-thumb" loading="lazy" alt="" src="' + esc(it.steam.header) + '" onerror="this.style.visibility=\'hidden\'">'
            : '') +
          '<span class="c-name">' + esc(it.title) + '</span>' +
          '<span class="c-studio">' + esc(studio(it)) + '</span></a>';
      }).join('') + '</div>' + behind;
    bindShelf();
  }

  function render() {
    if (COMPACT) renderCompact();
    else { renderFull(); }
  }

  /* ── detail panel ──────────────────────────────────────────── */

  function openDetail(uid) {
    var it = DATA.items.filter(function (x) { return x.uid === uid; })[0];
    if (!it) return;
    var iss = DATA.issues.filter(function (x) { return x.number === it.issue; })[0] || {};

    var coverHero = iss.cover_large
      ? '<div class="detail-hero"><img src="' + esc(iss.cover_large) + '" alt="" style="object-position:center 18%"></div>'
      : '';
    var hero = it.steam && it.steam.header
      ? '<div class="detail-hero"><img alt="" src="' + esc(it.steam.header) +
        '" onerror="window.__heroFail&amp;&amp;window.__heroFail(this)"></div>'
      : coverHero;

    var rows = '';
    function row(k, v) { if (v) rows += '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>'; }
    row('Developer', (it.developer || []).join(', '));
    row('Publisher', (it.publisher || []).join(', '));
    row(it.kind === 'review' ? 'Reviewed on' : 'Platforms', (it.platforms || []).join(', '));
    row('Released', it.release_date);
    row(it.kind === 'review' ? 'Reviewer' : 'Writer', it.byline);
    row('In', (it.issue_title || 'Issue ' + it.issue) + (it.page ? ', page ' + it.page : ''));
    row('Section', it.section);
    row('Related games', (it.related_games || []).join(', '));

    // Previews carry a summary for 4 of 326 entries, so say why it is blank
    // rather than rendering an empty panel.
    var note = '';
    if (!it.summary) {
      note = it.kind === 'preview'
        ? '<div class="detail-note">Debug does not publish summaries for previews — the issue itself is the only way to read this one.</div>'
        : '<div class="detail-note">No summary in the feed for this entry.</div>';
    }

    var links = '<a class="btn btn-primary" href="' + esc(it.issue_url || iss.purchase_url || '#') +
      '" target="_blank" rel="noopener">Issue ' + it.issue + ' →</a>';
    if (it.steam && it.steam.store) {
      links += '<a class="btn" href="' + esc(it.steam.store) + '" target="_blank" rel="noopener">Steam page</a>';
    } else {
      links += '<a class="btn" href="https://store.steampowered.com/search/?term=' +
        encodeURIComponent(it.title) + '" target="_blank" rel="noopener">Search Steam</a>';
    }

    detail.querySelector('.detail-body').innerHTML = hero +
      '<div class="detail-content">' +
        '<div class="detail-title" id="d-title">' + esc(it.title) + '</div>' +
        '<div class="detail-sub">' + esc(it.kind.charAt(0).toUpperCase() + it.kind.slice(1)) +
          ' · ' + esc(fmtDate(it.date || iss.date)) + '</div>' +
        (it.score_label
          ? '<div class="detail-score" style="background:' + scoreVar(it.normalised) + '">' + esc(it.score_label) + '</div>'
          : '') +
        (it.summary ? '<div class="detail-summary">' + esc(it.summary) + '</div>' : '') + note +
        (rows ? '<dl class="detail-rows">' + rows + '</dl>' : '') +
        '<div class="detail-links">' + links + '</div>' +
      '</div>';
    detail.hidden = false;
  }

  function closeDetail() { detail.hidden = true; }

  // Steam's newer apps only publish the small hashed capsule, and an appid
  // that has one today can lose it. Any art 404 degrades to the issue cover
  // rather than to a hole in the grid.
  window.__artFail = function (img) {
    var box = img.closest('.card-art');
    if (!box || box.classList.contains('is-fallback')) return;
    box.classList.add('is-fallback');
    var kind = box.querySelector('.kind');
    var badge = box.querySelector('.badge');
    box.innerHTML = decodeURIComponent(box.dataset.fallback || '');
    if (kind) box.insertBefore(kind, box.firstChild);
    if (badge) box.appendChild(badge);
  };
  window.__heroFail = function (img) {
    img.parentNode.style.display = 'none';
  };

  /* ── events ────────────────────────────────────────────────── */

  function bindShelf() { /* delegated below; kept for symmetry with render paths */ }

  function debounce(fn, ms) {
    var t;
    return function () { clearTimeout(t); t = setTimeout(fn, ms); };
  }

  root.addEventListener('click', function (e) {
    var cover = e.target.closest('.cover');
    if (cover) {
      var n = parseInt(cover.dataset.issue, 10);
      if (COMPACT) { window.open(fullUrl({ issue: n }), '_blank', 'noopener'); return; }
      state.issue = state.issue === n ? null : n;
      render();
      return;
    }
    var chip = e.target.closest('.chip');
    if (chip) {
      if (chip.dataset.clear) { state.issue = null; state.kind = 'all'; state.q = ''; state.minScore = 0; }
      else if (chip.dataset.kind) state.kind = chip.dataset.kind;
      else if (chip.dataset.score != null) state.minScore = parseInt(chip.dataset.score, 10);
      render();
      return;
    }
    var card = e.target.closest('.card');
    if (card) openDetail(card.dataset.uid);
  });

  detail.addEventListener('click', function (e) {
    if (e.target.closest('[data-close]')) closeDetail();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !detail.hidden) closeDetail();
  });

  /* ── load ──────────────────────────────────────────────────── */

  function load() {
    fetch('api/data', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        DATA = d;
        if (!DATA.items.length) {
          root.innerHTML = '<div class="empty">No data yet — the first fetch is still running.</div>';
          return;
        }
        document.body.classList.toggle('compact', COMPACT);
        render();
        var want = qs.get('item');
        if (want && !COMPACT) openDetail(want);
      })
      .catch(function (e) {
        root.innerHTML = '<div class="empty error">Could not reach the widget API.</div>';
        console.error(e);
      });
  }

  document.body.classList.toggle('compact', COMPACT);
  load();
  // Cheap resync: the scheduler only replaces the snapshot twice a day, but a
  // long-lived dashboard tab should pick up art as it backfills.
  setInterval(load, 10 * 60 * 1000);
})();
