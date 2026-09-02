"""Standalone "Libby status" lookup.

A tiny Flask page with a dialog: enter a title and/or an author, hit "Get Status", and
see whether each matching audiobook is available on Libby (via OverDrive's
unauthenticated Thunder API -- the same endpoint the Libby web app calls). If both
fields are filled the search requires both. Search / availability only; placing holds
or borrowing needs an authenticated session and is out of scope here.

Results are shown per library; by default it checks Toronto and Whitby.

Run:
    python app.py            # -> http://localhost:5002
    PORT=5010 python app.py  # different port
    LIBBY_LIBRARY_KEYS=toronto,whitby,mississauga python app.py   # different libraries
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import Flask, jsonify, render_template_string, request

LIBRARY_KEYS = [
    k.strip()
    for k in os.environ.get("LIBBY_LIBRARY_KEYS", "toronto,whitby").split(",")
    if k.strip()
]
# Friendly names for the keys we expect; anything else falls back to the key itself.
LIBRARY_NAMES = {
    "toronto": "Toronto Public Library",
    "whitby": "Whitby Public Library",
    "mississauga": "Mississauga Library System",
}
THUNDER_BASE = "https://thunder.api.overdrive.com/v2/libraries"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "libby-status-lookup/1.0 (personal reading tracker)"
)
CACHE_TTL = 300  # seconds
PORT = int(os.environ.get("PORT", "5002"))

app = Flask(__name__)

# cache key (title|author, lowercased) -> (fetched_at_monotonic, result_dict)
_cache: dict[str, tuple[float, dict]] = {}


def library_name(key: str) -> str:
    return LIBRARY_NAMES.get(key, key)


def _libby_search_url(title: str, author: str, library_key: str) -> str:
    terms = " ".join(t for t in (author, title) if t)
    return (
        f"https://libbyapp.com/search/{urllib.parse.quote(library_key)}"
        f"/search/query-{urllib.parse.quote(terms)}/page-1"
    )


def _search_libby(title: str, author: str, library_key: str) -> dict:
    """Call the Thunder media-search endpoint for one library and normalise it.

    Uses the fielded ``title`` / ``creator`` params: filling both narrows the search
    to titles that match both.
    """
    params = [("perPage", "24"), ("mediaTypes", "audiobook")]
    if title:
        params.append(("title", title))
    if author:
        params.append(("creator", author))
    url = (
        f"{THUNDER_BASE}/{urllib.parse.quote(library_key)}/media"
        f"?{urllib.parse.urlencode(params)}"
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.load(resp)

    items = []
    for raw in payload.get("items", []) or []:
        owned = int(raw.get("ownedCopies", 0) or 0)
        available = int(raw.get("availableCopies", 0) or 0)
        holds = int(raw.get("holdsCount", 0) or 0)
        wait_days = raw.get("estimatedWaitDays")
        lucky = int(raw.get("luckyDayAvailableCopies", 0) or 0)
        is_owned = bool(raw.get("isOwned")) or owned > 0

        if available > 0:
            label = f"Available now — {available}/{owned} copies"
            state = "available"
        elif is_owned:
            wait = f"~{wait_days} days" if wait_days not in (None, "") else "unknown wait"
            label = f"Wait list — {wait} ({holds} holds on {owned} copies)"
            state = "wait"
        else:
            label = "Not in this library's catalogue"
            state = "none"
        if lucky > 0:
            label += " · Lucky Day copy available"
            if state == "wait":
                state = "available"

        formats = [
            f.get("name") or f.get("id")
            for f in (raw.get("formats") or [])
            if isinstance(f, dict)
        ]

        media_type = raw.get("type")
        if isinstance(media_type, dict):
            type_key = (media_type.get("id") or media_type.get("name") or "").lower()
            media_type = media_type.get("name") or media_type.get("id") or ""
        else:
            type_key = str(media_type or "").lower()
        media_type = media_type or ""

        # Audiobooks only -- the query already asks for them, this drops any stray others.
        if type_key and type_key != "audiobook":
            continue

        items.append(
            {
                "id": raw.get("id"),
                "title": raw.get("title") or "(untitled)",
                "author": raw.get("firstCreatorName") or "",
                "media_type": media_type,
                "formats": [f for f in formats if f],
                "owned_copies": owned,
                "available_copies": available,
                "holds_count": holds,
                "wait_days": wait_days,
                "lucky_day": lucky,
                "status_label": label,
                "status_state": state,
            }
        )

    return {
        "library": library_key,
        "name": library_name(library_key),
        "total": len(items),
        "items": items,
        "libby_url": _libby_search_url(title, author, library_key),
    }


def _search_one(title: str, author: str, library_key: str) -> dict:
    """_search_libby wrapped so one library's failure doesn't sink the others."""
    try:
        return _search_libby(title, author, library_key)
    except urllib.error.HTTPError as exc:
        err = f"OverDrive returned HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError) as exc:
        err = f"could not reach OverDrive ({exc})"
    except (ValueError, KeyError) as exc:
        err = f"unexpected response from OverDrive ({exc})"
    return {
        "library": library_key,
        "name": library_name(library_key),
        "total": 0,
        "items": [],
        "libby_url": _libby_search_url(title, author, library_key),
        "error": err,
    }


def get_libby_status(title: str, author: str) -> dict:
    title = (title or "").strip()
    author = (author or "").strip()
    if not title and not author:
        return {"error": "Enter a title or an author"}

    key = f"{title.lower()}|{author.lower()}"
    hit = _cache.get(key)
    if hit and (time.monotonic() - hit[0]) < CACHE_TTL:
        return hit[1]

    result = {
        "title": title,
        "author": author,
        "libraries": [_search_one(title, author, k) for k in LIBRARY_KEYS],
    }
    _cache[key] = (time.monotonic(), result)
    return result


PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Libby status lookup</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: grid; place-items: start center;
    padding: 3rem 1rem; background: #f4f4f5;
    font: 15px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    color: #18181b;
  }
  dialog {
    border: none; border-radius: 14px; padding: 0; width: min(640px, 100%);
    box-shadow: 0 10px 40px rgba(0,0,0,.18); background: #fff; color: inherit;
  }
  .box { padding: 1.5rem 1.5rem 1.75rem; }
  h1 { margin: 0 0 .25rem; font-size: 1.15rem; }
  .sub { margin: 0 0 1.25rem; color: #71717a; font-size: .85rem; }
  form { display: grid; gap: .6rem; }
  .fields { display: flex; gap: .5rem; flex-wrap: wrap; }
  .field { flex: 1 1 200px; display: grid; gap: .2rem; }
  .field label { font-size: .78rem; font-weight: 600; color: #71717a; }
  input {
    width: 100%; padding: .6rem .75rem; border: 1px solid #d4d4d8; border-radius: 8px;
    font-size: 1rem; background: #fff; color: inherit;
  }
  button {
    justify-self: start; padding: .6rem 1.1rem; border: none; border-radius: 8px;
    cursor: pointer; background: #2563eb; color: #fff; font-size: .95rem;
    font-weight: 600;
  }
  button:disabled { opacity: .55; cursor: progress; }
  #results { margin-top: 1.25rem; display: grid; gap: 1.4rem; }
  .lib h2 {
    margin: 0 0 .5rem; font-size: .95rem; display: flex; align-items: baseline;
    gap: .5rem;
  }
  .lib h2 .count { color: #71717a; font-weight: 400; font-size: .82rem; }
  .lib .stack { display: grid; gap: .6rem; }
  .row {
    border: 1px solid #e4e4e7; border-radius: 10px; padding: .7rem .85rem;
    display: grid; gap: .3rem;
  }
  .row .t { font-weight: 600; }
  .row .m { color: #71717a; font-size: .82rem; }
  .badge {
    justify-self: start; font-size: .78rem; font-weight: 600; padding: .15rem .55rem;
    border-radius: 999px;
  }
  .badge.available { background: #dcfce7; color: #166534; }
  .badge.wait { background: #fef9c3; color: #854d0e; }
  .badge.none { background: #e4e4e7; color: #3f3f46; }
  .msg { color: #71717a; font-size: .85rem; }
  .err { color: #b91c1c; font-size: .85rem; }
  a.libby { font-size: .82rem; color: #2563eb; }
  @media (prefers-color-scheme: dark) {
    body { background: #18181b; color: #f4f4f5; }
    dialog { background: #27272a; }
    input { background: #18181b; border-color: #3f3f46; }
    .row { border-color: #3f3f46; }
    .sub, .field label, .lib h2 .count, .row .m, .msg { color: #a1a1aa; }
  }
</style>
</head>
<body>
<dialog open>
  <div class="box">
    <h1>Libby status lookup</h1>
    <p class="sub">Libraries: <strong>{{ libraries }}</strong> &middot; <strong>audiobooks only</strong> &middot; source: OverDrive Thunder API (catalogue &amp; availability only)</p>
    <form id="f">
      <div class="fields">
        <div class="field">
          <label for="author">Author</label>
          <input id="author" name="author" type="text" autocomplete="off" autofocus>
        </div>
        <div class="field">
          <label for="title">Title</label>
          <input id="title" name="title" type="text" autocomplete="off">
        </div>
      </div>
      <button id="go" type="submit">Get Status</button>
    </form>
    <div id="results"></div>
  </div>
</dialog>
<script>
  const f = document.getElementById('f');
  const author = document.getElementById('author');
  const title = document.getElementById('title');
  const go = document.getElementById('go');
  const out = document.getElementById('results');
  const esc = s => (s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  const rowHtml = it => `
    <div class="row">
      <span class="t">${esc(it.title)}</span>
      <span class="m">${esc(it.author)}${it.media_type ? ' &middot; ' + esc(it.media_type) : ''}${it.formats.length ? ' &middot; ' + esc(it.formats.join(', ')) : ''}</span>
      <span class="badge ${esc(it.status_state)}">${esc(it.status_label)}</span>
    </div>`;

  const libHtml = lib => {
    let body;
    if (lib.error) {
      body = '<div class="err">Lookup failed: ' + esc(lib.error) + '</div>';
    } else if (!lib.items.length) {
      body = '<div class="msg">Not in this library&rsquo;s audiobook collection &mdash; nothing to borrow or place a hold on. '
        + 'Libby&rsquo;s <em>deep search</em> may still list it as a &ldquo;Notify Me&rdquo; request. '
        + '<a class="libby" target="_blank" rel="noopener" href="' + esc(lib.libby_url) + '">Search all of Libby &#8599;</a></div>';
    } else {
      body = '<div class="stack">' + lib.items.map(rowHtml).join('') + '</div>'
        + '<div class="msg"><a class="libby" target="_blank" rel="noopener" href="' + esc(lib.libby_url) + '">Open this search in Libby &#8599;</a></div>';
    }
    return '<section class="lib"><h2>' + esc(lib.name)
      + '<span class="count">' + (lib.error ? '' : lib.total + (lib.total === 1 ? ' match' : ' matches')) + '</span></h2>'
      + body + '</section>';
  };

  f.addEventListener('submit', async e => {
    e.preventDefault();
    const a = author.value.trim();
    const t = title.value.trim();
    if (!a && !t) { out.innerHTML = '<div class="err">Enter a title or an author.</div>'; return; }
    go.disabled = true;
    out.innerHTML = '<div class="msg">Checking Libby&hellip;</div>';
    try {
      const qs = new URLSearchParams();
      if (t) qs.set('title', t);
      if (a) qs.set('author', a);
      const r = await fetch('/status?' + qs.toString());
      const data = await r.json();
      if (data.error) { out.innerHTML = '<div class="err">' + esc(data.error) + '</div>'; return; }
      out.innerHTML = data.libraries.map(libHtml).join('');
    } catch (err) {
      out.innerHTML = '<div class="err">Request failed: ' + esc(String(err)) + '</div>';
    } finally {
      go.disabled = false;
    }
  });
</script>
</body>
</html>
"""


@app.get("/")
def index():
    names = ", ".join(library_name(k) for k in LIBRARY_KEYS)
    return render_template_string(PAGE, libraries=names)


@app.get("/status")
def status():
    return jsonify(
        get_libby_status(request.args.get("title", ""), request.args.get("author", ""))
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=True)
