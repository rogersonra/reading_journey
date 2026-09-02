# Libby status lookup

A small standalone Flask page: fill in **Author** and/or **Title**, press **Get
Status**, and see whether each matching **audiobook** is available on Libby. Filling
both narrows the search to titles matching both (via the Thunder `title` / `creator`
params). Results are grouped by library — by default it checks **Toronto Public
Library** and **Whitby Public Library**. (The search is restricted to audiobooks via
`mediaTypes=audiobook`; drop that from the params in `_search_libby` to include
ebooks.)

It calls OverDrive's **Thunder API**
(`https://thunder.api.overdrive.com/v2/libraries/<key>/media?query=...`) — the same
unauthenticated JSON endpoint the Libby web app uses for catalogue search. No login,
no browser automation. This is why Playwright/Selenium are *not* used here: for search
and availability the API is simpler and far less brittle than scraping a single-page
app.

This tool is separate from the main Reading Journey app and is not imported by it.

## Run

```bash
pip install -r requirements.txt
python app.py
# -> http://localhost:5002
```

Environment variables:

| Var | Default | Meaning |
| --- | --- | --- |
| `PORT` | `5002` | Port to serve on (5000 = live app, 5001 = dev worktree). |
| `LIBBY_LIBRARY_KEYS` | `toronto,whitby` | Comma-separated library slugs from your Libby URL (`libbyapp.com/library/<key>`). Each is queried and shown as its own section. |

## What the status means

- **Available now** — `availableCopies > 0`, borrow immediately.
- **Wait list** — the library owns copies but all are out; shows the estimated wait and
  hold count.
- **Not in this library's catalogue** — no owned copies.
- **Lucky Day copy available** — a skip-the-line copy is on the shelf right now.

Results are cached in memory for 5 minutes per query. The Thunder API is unofficial and
its response shape can change without notice.

## Future: borrowing

Placing holds or borrowing needs an authenticated Libby session, so that step *would*
use Playwright — sign in once with the library card + PIN, persist the session, then
drive the "Place Hold" / "Borrow" buttons on `libbyapp.com`. Not built here. Keep any
such automation personal-use and low-rate; OverDrive's terms restrict automated access.
