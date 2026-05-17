from __future__ import annotations
import csv
from pathlib import Path
from flask import Flask, render_template_string

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "csv" / "books.csv"
NEXT_COUNT = 10

UNREAD = {"", None}


def load_books() -> list[dict]:
    books = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # First column has no header in the CSV; rename it to "Author"
        if reader.fieldnames and reader.fieldnames[0] == "":
            reader.fieldnames = ["Author"] + list(reader.fieldnames[1:])
        for row in reader:
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


def next_to_read(books: list[dict], n: int = NEXT_COUNT) -> list[dict]:
    return [b for b in books if b["Rob"] in UNREAD][:n]


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
</style>
</head>
<body>

<header>
  <h1>Reading Journey</h1>
  <span>{{ total }} books</span>
</header>

<div class="container">

  <!-- NEXT TO READ -->
  <p class="section-title">Next {{ next_books|length }} for Rob</p>
  <div class="next-grid">
    {% for b in next_books %}
    <div class="book-card">
      <div class="title">{{ b.Title }}</div>
      <div class="author">{{ b.Author or '—' }}</div>
      {% if b.Series %}<div class="series">{{ b.Series }}</div>{% endif %}
      <div class="year">{{ b.Year }}</div>
    </div>
    {% endfor %}
  </div>

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
  </div>
  <p class="count-note" id="count-note"></p>

  <div class="table-wrap" style="margin-top:.75rem">
    <table id="book-table">
      <thead>
        <tr>
          <th>Author</th>
          <th>Series</th>
          <th>Title</th>
          <th>Year</th>
          <th>Rob</th>
          <th>Mom</th>
        </tr>
      </thead>
      <tbody>
        {% for b in books %}
        <tr
          data-title="{{ b.Title|lower }}"
          data-author="{{ b.Author|lower }}"
          data-series="{{ b.Series|lower }}"
          data-rob="{{ b.Rob|lower }}"
        >
          <td>{{ b.Author or '—' }}</td>
          <td style="color:var(--muted)">{{ b.Series }}</td>
          <td>{{ b.Title }}</td>
          <td style="color:var(--muted)">{{ b.Year }}</td>
          <td>{{ badge(b.Rob) }}</td>
          <td>{{ badge(b.Mom) }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>

</div>

<script>
  let activeFilter = 'all';

  function badge(status) {
    if (!status) return '';
    const cls = { read:'badge-read', reading:'badge-reading', hold:'badge-hold', 'n/a':'badge-na' }[status.toLowerCase()] || 'badge-unread';
    return `<span class="badge ${cls}">${status}</span>`;
  }

  // Re-render badge cells (Jinja already did this server-side; JS handles dynamic filtering display)
  function filterTable() {
    const q = document.getElementById('search').value.toLowerCase();
    const rows = document.querySelectorAll('#book-table tbody tr');
    let visible = 0;
    rows.forEach(row => {
      const matchSearch = !q ||
        row.dataset.title.includes(q) ||
        row.dataset.author.includes(q) ||
        row.dataset.series.includes(q);
      const rob = row.dataset.rob;
      const matchFilter =
        activeFilter === 'all' ||
        (activeFilter === 'unread'  && rob === '') ||
        (activeFilter === 'read'    && rob === 'read') ||
        (activeFilter === 'reading' && rob === 'reading');
      const show = matchSearch && matchFilter;
      row.style.display = show ? '' : 'none';
      if (show) visible++;
    });
    document.getElementById('count-note').textContent = `Showing ${visible} books`;
  }

  function setFilter(btn) {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeFilter = btn.dataset.filter;
    filterTable();
  }

  // Initial count
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


@app.route("/")
def index():
    books = load_books()
    return render_template_string(
        TEMPLATE,
        books=books,
        next_books=next_to_read(books),
        total=len(books),
        badge=badge,
    )


if __name__ == "__main__":
    app.run(debug=True)
