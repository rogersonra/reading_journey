from __future__ import annotations
import csv
import json
import time
from itertools import groupby
from pathlib import Path
from flask import Flask, render_template_string, request

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "csv" / "books.csv"
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
SHEET_ID = "1WuO8vyFegtg6eI7f9V4eMm6vMkzxhDCo1DfSBT-pnDo"
STATE_PATH = BASE_DIR / "state.json"
CACHE_TTL = 300  # seconds before re-fetching from Sheets
NEXT_COUNT = 5

UNREAD = {"", None}
_cache: dict = {"books": None, "ts": 0.0}


def _clean_rows(headers: list[str], raw_rows: list[dict | list]) -> list[dict]:
    if headers and headers[0] == "":
        headers[0] = "Author"
    books = []
    for row in raw_rows:
        if isinstance(row, list):
            row = dict(zip(headers, row))
        if not row.get("Title", "").strip():
            continue
        try:
            row["Year"] = str(abs(int(row["Year"])))
        except (ValueError, TypeError):
            row["Year"] = ""
        row["Author"] = row.get("Author", "").strip()
        row["Rob"] = row.get("Rob", "").strip()
        row["Mom"] = row.get("Mom", "").strip()
        books.append(row)
    return books


def load_books_from_sheets() -> list[dict]:
    import gspread
    from google.oauth2.service_account import Credentials

    now = time.monotonic()
    if _cache["books"] is not None and now - _cache["ts"] < CACHE_TTL:
        return _cache["books"]

    creds = Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    client = gspread.authorize(creds)
    ws = client.open_by_key(SHEET_ID).sheet1
    all_values = ws.get_all_values()
    if not all_values:
        return []

    headers = [h.strip() for h in all_values[0]]
    books = _clean_rows(headers, all_values[1:])
    _cache["books"] = books
    _cache["ts"] = now
    return books


def load_books() -> list[dict]:
    if SHEET_ID and CREDENTIALS_PATH.exists():
        try:
            return load_books_from_sheets()
        except Exception as e:
            app.logger.warning(f"Sheets load failed, falling back to CSV: {e}")

    books = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        for row in reader:
            books.append(dict(row))
    return _clean_rows(headers, books)


def load_state() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_author": ""}


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)


def update_book_status(title: str, author: str, status: str) -> None:
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    client = gspread.authorize(creds)
    ws = client.open_by_key(SHEET_ID).sheet1
    all_values = ws.get_all_values()
    if not all_values:
        return

    headers = [h.strip() for h in all_values[0]]
    if headers and headers[0] == "":
        headers[0] = "Author"

    try:
        author_col = headers.index("Author")
        title_col  = headers.index("Title")
        rob_col    = headers.index("Rob") + 1  # gspread update_cell is 1-indexed
    except ValueError:
        return

    for row_idx, row in enumerate(all_values[1:], start=2):
        row_title  = row[title_col].strip()  if len(row) > title_col  else ""
        row_author = row[author_col].strip() if len(row) > author_col else ""
        if row_title == title and row_author == author:
            ws.update_cell(row_idx, rob_col, status)
            return


def reading_books(sorted_books: list[dict]) -> list[dict]:
    return [b for b in sorted_books if b["Rob"].lower() == "reading"]


def _unread_by_author(sorted_books: list[dict], exclude_authors: set[str] | None = None) -> list[tuple[str, dict]]:
    """Return [(author_lower, first_unread_book)] sorted by last name, skipping excluded authors."""
    exclude_authors = exclude_authors or set()
    seen: dict[str, dict] = {}
    for b in sorted_books:
        if b["Rob"] not in UNREAD:
            continue
        key = b["Author"].lower()
        if key not in exclude_authors and key not in seen:
            seen[key] = b
    return sorted(seen.items(), key=lambda x: last_name(x[0]))


def _next_from_rotation(ordered: list[tuple[str, dict]], last_author: str) -> tuple[str, dict] | None:
    """Return the next (author_lower, book) after last_author in the ordered list."""
    if not ordered:
        return None
    last = last_author.lower()
    start = 0
    for i, (akey, _) in enumerate(ordered):
        if last_name(akey) > last_name(last):
            start = i
            break
    return ordered[start % len(ordered)]


def next_to_read(sorted_books: list[dict], n: int = NEXT_COUNT) -> list[dict]:
    state = load_state()
    saved = state.get("next_reads", [])

    # Restore saved list, dropping any books that are no longer unread
    unread = {(b["Title"], b["Author"]): b for b in sorted_books if b["Rob"] in UNREAD}
    restored = []
    for item in saved:
        key = (item["title"], item["author"])
        if key in unread:
            restored.append(unread[key])

    if len(restored) == n:
        return restored  # saved list is complete — use it unchanged

    # First visit or stale state: generate a fresh list via rotation
    ordered = _unread_by_author(sorted_books)
    total = len(ordered)
    if not total:
        return []

    last = state.get("last_author", "").lower()
    start = 0
    for i, (akey, _) in enumerate(ordered):
        if last_name(akey) > last_name(last):
            start = i
            break

    count = min(n, total)
    selected = [ordered[(start + i) % total][1] for i in range(count)]
    new_last = ordered[(start + count - 1) % total][0]

    state["last_author"] = new_last
    state["next_reads"] = [{"title": b["Title"], "author": b["Author"]} for b in selected]
    save_state(state)
    return selected


def advance_after_status_change(sorted_books: list[dict], changed_title: str, changed_author: str) -> list[dict]:
    """Replace only the changed book with the next unread book from rotation."""
    state = load_state()
    saved = state.get("next_reads", [])

    # Remove the book whose status changed
    remaining = [s for s in saved
                 if not (s["title"] == changed_title and s["author"] == changed_author)]
    was_in_next_reads = len(remaining) < len(saved)

    # Only slot in a replacement if the book was actually in Next Reads
    if was_in_next_reads:
        already = {s["author"].lower() for s in remaining}
        ordered = _unread_by_author(sorted_books, exclude_authors=already)
        entry = _next_from_rotation(ordered, state.get("last_author", ""))
        if entry:
            akey, next_book = entry
            remaining.append({"title": next_book["Title"], "author": next_book["Author"]})
            state["last_author"] = akey

    state["next_reads"] = remaining
    save_state(state)

    unread = {(b["Title"], b["Author"]): b for b in sorted_books if b["Rob"] in UNREAD}
    return [unread[(s["title"], s["author"])] for s in remaining
            if (s["title"], s["author"]) in unread]


READING_PARTIAL = """
{% for b in reading_books %}
<div class="book-card">
  <div class="title">{{ b.Title }}</div>
  <div class="author">{{ b.Author or '—' }}</div>
  {% if b.Series %}<div class="series">{{ b.Series }}</div>{% endif %}
  <div class="year">{{ b.Year }}</div>
  <div class="status-btns">
    <button class="status-btn s-read" onclick="setStatus(this, {{ b.Title|tojson }}, {{ b.Author|tojson }}, 'Read')">Read</button>
    <button class="status-btn s-hold" onclick="setStatus(this, {{ b.Title|tojson }}, {{ b.Author|tojson }}, 'Hold')">Hold</button>
    <button class="status-btn s-na"   onclick="setStatus(this, {{ b.Title|tojson }}, {{ b.Author|tojson }}, 'n/a')">n/a</button>
  </div>
  <button class="copy-btn" onclick="copyTitle(this, {{ b.Title|tojson }})">Copy title</button>
</div>
{% endfor %}
"""

CARDS_PARTIAL = """
{% for b in next_books %}
<div class="book-card">
  <div class="title">{{ b.Title }}</div>
  <div class="author">{{ b.Author or '—' }}</div>
  {% if b.Series %}<div class="series">{{ b.Series }}</div>{% endif %}
  <div class="year">{{ b.Year }}</div>
  <div class="status-btns">
    <button class="status-btn s-read"    onclick="setStatus(this, {{ b.Title|tojson }}, {{ b.Author|tojson }}, 'Read')">Read</button>
    <button class="status-btn s-reading" onclick="setStatus(this, {{ b.Title|tojson }}, {{ b.Author|tojson }}, 'Reading')">Reading</button>
    <button class="status-btn s-hold"    onclick="setStatus(this, {{ b.Title|tojson }}, {{ b.Author|tojson }}, 'Hold')">Hold</button>
    <button class="status-btn s-na"      onclick="setStatus(this, {{ b.Title|tojson }}, {{ b.Author|tojson }}, 'n/a')">n/a</button>
  </div>
  <button class="copy-btn" onclick="copyTitle(this, {{ b.Title|tojson }})">Copy title</button>
</div>
{% endfor %}
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reading Journey</title>
<style>
  :root {
    --bg: #0f1117;
    --card: #1a1d27;
    --surface: #22263a;
    --text: #e8eaf0;
    --muted: #7a7f99;
    --border: #2e3250;
    --accent: #6c8eff;
    --green: #4caf7d;
    --amber: #f5a623;
    --blue: #5bc0de;
    --red: #e05c5c;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; min-height: 100vh; }

  header {
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 1rem 2rem;
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  header h1 { font-size: 1.4rem; font-weight: 700; color: var(--accent); }
  header span { color: var(--muted); font-size: 0.9rem; }

  .container { max-width: 1200px; margin: 0 auto; padding: 2rem 1.5rem; }

  /* ---- Next to Read ---- */
  .section-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .08em;
    margin-bottom: 1rem;
  }
  .next-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 2.5rem;
  }
  .book-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    transition: border-color .15s;
  }
  .book-card:hover { border-color: var(--accent); }
  .book-card .title { font-weight: 600; font-size: 0.95rem; line-height: 1.3; }
  .book-card .author { font-size: 0.8rem; color: var(--muted); }
  .book-card .series { font-size: 0.78rem; color: var(--accent); margin-top: 0.2rem; }
  .book-card .year { font-size: 0.75rem; color: var(--muted); margin-top: auto; padding-top: 0.5rem; }
  .status-btns { display: flex; gap: 0.3rem; margin-top: 0.5rem; }
  .status-btn {
    flex: 1;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.25rem 0.2rem;
    font-size: 0.7rem;
    font-weight: 600;
    cursor: pointer;
    background: var(--surface);
    color: var(--muted);
    transition: opacity .15s;
    white-space: nowrap;
  }
  .status-btn:hover { opacity: 0.75; }
  .status-btn.s-read    { background: rgba(76,175,125,.2);  color: var(--green); border-color: var(--green); }
  .status-btn.s-reading { background: rgba(245,166,35,.2);  color: var(--amber); border-color: var(--amber); }
  .status-btn.s-hold    { background: rgba(91,192,222,.2);  color: var(--blue);  border-color: var(--blue); }
  .status-btn.s-na      { background: rgba(122,127,153,.15);color: var(--muted); border-color: var(--border); }

  .copy-btn {
    margin-top: 0.5rem;
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--muted);
    border-radius: 5px;
    padding: 0.3rem 0.6rem;
    font-size: 0.75rem;
    cursor: pointer;
    transition: all .15s;
    width: 100%;
  }
  .copy-btn:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
  .copy-btn.copied { background: var(--green); color: #fff; border-color: var(--green); }

  /* ---- Controls ---- */
  .controls {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: center;
    margin-bottom: 1rem;
  }
  .controls input {
    flex: 1;
    min-width: 200px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    padding: 0.5rem 0.75rem;
    font-size: 0.9rem;
    outline: none;
  }
  .controls input:focus { border-color: var(--accent); }
  .filters { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .filter-btn {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--muted);
    border-radius: 6px;
    padding: 0.4rem 0.85rem;
    font-size: 0.82rem;
    cursor: pointer;
    transition: all .15s;
  }
  .filter-btn.active, .filter-btn:hover { background: var(--accent); color: #fff; border-color: var(--accent); }

  /* ---- Table ---- */
  .table-wrap { overflow-x: auto; border-radius: 10px; border: 1px solid var(--border); }
  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  thead tr { background: var(--surface); }
  th {
    text-align: left;
    padding: 0.65rem 1rem;
    color: var(--muted);
    font-weight: 600;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: .06em;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }
  td { padding: 0.6rem 1rem; border-bottom: 1px solid var(--border); vertical-align: middle; }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr:hover { background: var(--surface); }

  .badge {
    display: inline-block;
    padding: 0.2rem 0.55rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    white-space: nowrap;
  }
  .badge-read    { background: rgba(76,175,125,.18); color: var(--green); }
  .badge-reading { background: rgba(245,166,35,.18); color: var(--amber); }
  .badge-hold    { background: rgba(91,192,222,.18); color: var(--blue); }
  .badge-na      { background: rgba(122,127,153,.12); color: var(--muted); }
  .badge-unread  { background: transparent; color: var(--muted); border: 1px solid var(--border); }

  .count-note { color: var(--muted); font-size: 0.82rem; margin-top: 0.5rem; }

  /* ---- Author group rows ---- */
  .author-row { cursor: pointer; user-select: none; background: var(--surface); }
  .author-row:hover { background: #2a2e45; }
  .author-row td {
    padding: 0.55rem 1rem;
    font-weight: 600;
    font-size: 0.85rem;
    color: var(--accent);
    border-bottom: 1px solid var(--border);
  }
  /* ---- Series group rows ---- */
  .series-row { cursor: pointer; user-select: none; background: #161926; }
  .series-row:hover { background: #1e2235; }
  .series-row td {
    padding: 0.45rem 1rem 0.45rem 2.5rem;
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
  }
  /* ---- Shared chevron ---- */
  .author-row .chevron, .series-row .chevron {
    display: inline-block;
    margin-right: 0.4rem;
    transition: transform .2s;
    font-style: normal;
    color: var(--muted);
    font-size: 0.7rem;
  }
  .author-row.collapsed .chevron,
  .series-row.collapsed .chevron { transform: rotate(-90deg); }
  .book-count {
    font-size: 0.75rem;
    color: var(--muted);
    font-weight: 400;
    margin-left: 0.4rem;
  }
  /* ---- Book rows indented under series ---- */
  .book-row td:first-child { padding-left: 3.5rem; }

  /* ---- % read badge (shown only when author row is collapsed) ---- */
  .pct { display: none; font-size: 0.75rem; color: var(--green); margin-left: 0.6rem; font-weight: 500; }
  .author-row.collapsed .pct { display: inline; }

  /* ---- Toggle all button ---- */
  #toggleAllBtn {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--muted);
    border-radius: 6px;
    padding: 0.4rem 0.85rem;
    font-size: 0.82rem;
    cursor: pointer;
    transition: all .15s;
    white-space: nowrap;
  }
  #toggleAllBtn:hover { background: var(--accent); color: #fff; border-color: var(--accent); }
</style>
</head>
<body>

<header>
  <h1>Reading Journey</h1>
  <span>{{ total }} books</span>
</header>

<div class="container">

  <!-- NEXT TO READ -->
  <p class="section-title">Next Reads</p>
  <div class="next-grid" id="next-reads-grid">{{ cards_html | safe }}</div>

  <!-- READING -->
  {% if reading_html | trim %}
  <p class="section-title">Reading</p>
  <div class="next-grid" id="reading-grid">{{ reading_html | safe }}</div>
  {% endif %}

  <!-- ALL BOOKS -->
  <p class="section-title">All Books</p>

  <div class="controls">
    <input id="search" type="text" placeholder="Search title, author, series…" oninput="filterTable()">
    <div class="filters">
      <button class="filter-btn active" data-filter="all"    onclick="setFilter(this)">All</button>
      <button class="filter-btn"        data-filter="unread" onclick="setFilter(this)">Unread</button>
      <button class="filter-btn"        data-filter="read"   onclick="setFilter(this)">Read</button>
      <button class="filter-btn"        data-filter="reading"onclick="setFilter(this)">Reading</button>
    </div>
    <button id="toggleAllBtn" onclick="toggleAll()">Expand All</button>
  </div>
  <p class="count-note" id="count-note"></p>

  <div class="table-wrap" style="margin-top:.75rem">
    <table id="book-table">
      <thead>
        <tr>
          <th>Title</th>
          <th>Year</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {% for group in grouped_books %}
        {% set aid = loop.index %}
        <tr class="author-row" data-aid="{{ aid }}" onclick="toggleAuthor(this)">
          <td colspan="3">
            <i class="chevron">&#9660;</i>
            {{ group.author }}
            <span class="book-count">{{ group.total }} books</span>
            <span class="pct">{{ group.read_pct }}% read</span>
          </td>
        </tr>
        {% for sg in group.series_groups %}
        {% set sid = aid ~ '-' ~ loop.index %}
        <tr class="series-row" data-aid="{{ aid }}" data-sid="{{ sid }}" onclick="toggleSeries(event, this)">
          <td colspan="3">
            <i class="chevron">&#9660;</i>
            {{ sg.series }}
            <span class="book-count">{{ sg.books|length }}</span>
          </td>
        </tr>
        {% for b in sg.books %}
        <tr class="book-row"
          data-aid="{{ aid }}"
          data-sid="{{ sid }}"
          data-title="{{ b.Title|lower }}"
          data-author="{{ b.Author|lower }}"
          data-series="{{ b.Series|lower }}"
          data-rob="{{ b.Rob|lower }}"
        >
          <td>{{ b.Title }}</td>
          <td style="color:var(--muted)">{{ b.Year }}</td>
          <td>{{ badge(b.Rob) | safe }}</td>
        </tr>
        {% endfor %}
        {% endfor %}
        {% endfor %}
      </tbody>
    </table>
  </div>

</div>

<script>
  function setStatus(btn, title, author, status) {
    btn.textContent = '…';
    btn.disabled = true;
    fetch('/update_status', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({title, author, status})
    }).then(r => r.json()).then(data => {
      if (data.ok) {
        document.getElementById('next-reads-grid').innerHTML = data.cards_html;
        const rg = document.getElementById('reading-grid');
        if (rg) rg.innerHTML = data.reading_html;
      } else {
        btn.textContent = 'Error';
        btn.disabled = false;
      }
    }).catch(() => { btn.textContent = 'Error'; btn.disabled = false; });
  }

  function copyTitle(btn, title) {
    navigator.clipboard.writeText(title).then(() => {
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => { btn.textContent = 'Copy title'; btn.classList.remove('copied'); }, 2000);
    });
  }

  let activeFilter = 'all';
  let wasFiltering = false;

  function matchesRow(row, q) {
    const rob = row.dataset.rob;
    const search = !q || row.dataset.title.includes(q) || row.dataset.author.includes(q) || row.dataset.series.includes(q);
    const filter = activeFilter === 'all' ||
      (activeFilter === 'unread'  && rob === '') ||
      (activeFilter === 'read'    && rob === 'read') ||
      (activeFilter === 'reading' && rob === 'reading');
    return search && filter;
  }

  // Re-apply visibility based purely on collapsed classes (no filter active)
  function applyCollapseState() {
    document.querySelectorAll('.author-row').forEach(authorRow => {
      const aid = authorRow.dataset.aid;
      const authorCollapsed = authorRow.classList.contains('collapsed');
      document.querySelectorAll(`.series-row[data-aid="${aid}"]`).forEach(seriesRow => {
        seriesRow.style.display = authorCollapsed ? 'none' : '';
        if (!authorCollapsed) {
          const seriesCollapsed = seriesRow.classList.contains('collapsed');
          document.querySelectorAll(`.book-row[data-sid="${seriesRow.dataset.sid}"]`).forEach(r => {
            r.style.display = seriesCollapsed ? 'none' : '';
          });
        }
      });
      if (authorCollapsed) {
        document.querySelectorAll(`.book-row[data-aid="${aid}"]`).forEach(r => r.style.display = 'none');
      }
    });
  }

  function filterTable() {
    const q = document.getElementById('search').value.toLowerCase();
    const filtering = q !== '' || activeFilter !== 'all';

    if (!filtering && wasFiltering) applyCollapseState();
    wasFiltering = filtering;

    const aidVisible = {}, sidVisible = {};
    let totalMatching = 0;

    document.querySelectorAll('.book-row').forEach(row => {
      const show = matchesRow(row, q);
      if (filtering) row.style.display = show ? '' : 'none';
      if (show) {
        totalMatching++;
        aidVisible[row.dataset.aid] = (aidVisible[row.dataset.aid] || 0) + 1;
        sidVisible[row.dataset.sid] = (sidVisible[row.dataset.sid] || 0) + 1;
      }
    });

    if (filtering) {
      document.querySelectorAll('.series-row').forEach(r => {
        const count = sidVisible[r.dataset.sid] || 0;
        r.style.display = count > 0 ? '' : 'none';
        if (count > 0) r.classList.remove('collapsed');
      });
      document.querySelectorAll('.author-row').forEach(r => {
        const count = aidVisible[r.dataset.aid] || 0;
        r.style.display = count > 0 ? '' : 'none';
        if (count > 0) r.classList.remove('collapsed');
      });
    }

    document.getElementById('count-note').textContent = filtering
      ? `Showing ${totalMatching} books`
      : `${totalMatching} books total`;
  }

  function toggleAuthor(authorRow) {
    const aid = authorRow.dataset.aid;
    const collapsed = authorRow.classList.toggle('collapsed');
    document.querySelectorAll(`.series-row[data-aid="${aid}"], .book-row[data-aid="${aid}"]`).forEach(r => {
      r.style.display = collapsed ? 'none' : '';
      if (!collapsed && r.classList.contains('series-row')) r.classList.remove('collapsed');
    });
  }

  function toggleSeries(event, seriesRow) {
    event.stopPropagation();
    const sid = seriesRow.dataset.sid;
    const collapsed = seriesRow.classList.toggle('collapsed');
    document.querySelectorAll(`.book-row[data-sid="${sid}"]`).forEach(r => {
      r.style.display = collapsed ? 'none' : '';
    });
  }

  function collapseAll() {
    document.querySelectorAll('.author-row, .series-row').forEach(r => r.classList.add('collapsed'));
    document.querySelectorAll('.series-row, .book-row').forEach(r => r.style.display = 'none');
    document.getElementById('toggleAllBtn').textContent = 'Expand All';
  }

  function expandAll() {
    document.querySelectorAll('.author-row, .series-row').forEach(r => r.classList.remove('collapsed'));
    document.querySelectorAll('.series-row, .book-row').forEach(r => r.style.display = '');
    document.getElementById('toggleAllBtn').textContent = 'Collapse All';
  }

  function toggleAll() {
    if (document.getElementById('toggleAllBtn').textContent.trim() === 'Expand All') expandAll();
    else collapseAll();
  }

  function setFilter(btn) {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeFilter = btn.dataset.filter;
    filterTable();
  }

  // Init: start collapsed
  collapseAll();
  filterTable();
</script>
</body>
</html>
"""


def badge(status: str) -> str:
    s = (status or "").strip().lower()
    cls_map = {"read": "badge-read", "reading": "badge-reading", "hold": "badge-hold", "n/a": "badge-na"}
    cls = cls_map.get(s, "badge-unread")
    label = status.strip() if status.strip() else ""
    if not label:
        return ""
    return f'<span class="badge {cls}">{label}</span>'


def last_name(author: str) -> str:
    parts = author.strip().split()
    return parts[-1].lower() if parts else ""


def sort_key(b: dict):
    year = int(b["Year"]) if b["Year"].isdigit() else 0
    return (last_name(b["Author"]), b["Author"].lower(), b["Series"].lower(), year)


@app.route("/update_status", methods=["POST"])
def update_status():
    data = request.get_json() or {}
    title  = data.get("title", "").strip()
    author = data.get("author", "").strip()
    status = data.get("status", "").strip()
    if not title or status not in {"Read", "Reading", "Hold", "n/a"}:
        return {"ok": False, "error": "invalid input"}, 400
    try:
        update_book_status(title, author, status)
        _cache["books"] = None
        books = load_books()
        sorted_books = sorted(books, key=sort_key)
        next_books   = advance_after_status_change(sorted_books, title, author)
        cards_html   = render_template_string(CARDS_PARTIAL,   next_books=next_books)
        reading_html = render_template_string(READING_PARTIAL, reading_books=reading_books(sorted_books))
        return {"ok": True, "cards_html": cards_html, "reading_html": reading_html}
    except Exception as e:
        app.logger.error(f"update_status failed: {e}")
        return {"ok": False, "error": str(e)}, 500


@app.route("/")
def index():
    books = load_books()
    sorted_books = sorted(books, key=sort_key)
    grouped_books = []
    for _, author_group in groupby(sorted_books, key=lambda b: b["Author"].lower()):
        author_books = list(author_group)
        author = author_books[0]["Author"]
        series_groups = []
        for _, sg in groupby(author_books, key=lambda b: b["Series"].lower()):
            sg_books = list(sg)
            series_groups.append({"series": sg_books[0]["Series"] or "Standalone", "books": sg_books})
        read_count = sum(1 for b in author_books if b["Rob"].lower() == "read")
        read_pct = round(read_count / len(author_books) * 100) if author_books else 0
        grouped_books.append({
            "author": author or "—",
            "total": len(author_books),
            "read_pct": read_pct,
            "series_groups": series_groups,
        })
    next_books = next_to_read(sorted_books)
    cards_html   = render_template_string(CARDS_PARTIAL,   next_books=next_books)
    reading_html = render_template_string(READING_PARTIAL, reading_books=reading_books(sorted_books))
    return render_template_string(
        TEMPLATE,
        grouped_books=grouped_books,
        cards_html=cards_html,
        reading_html=reading_html,
        total=len(books),
        badge=badge,
    )


if __name__ == "__main__":
    app.run(debug=True)
