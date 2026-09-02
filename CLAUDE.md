# Reading Journey — Project Context

## Purpose
A personal reading tracker web app for Rob and Mom. Displays the next 10 books to read and a full searchable/filterable book list, sourced from a local CSV file.

## Stack
- **Python + Flask** — local web server, single-file app (`app.py`)
- **CSV data** — `csv/books.csv` (~726 books), no database
- **Virtual environment** — `venv/` (git-ignored)

## Setup & Run

```bash
# 1. Create virtual environment (first time only)
python -m venv venv

# 2. Activate (Windows)
venv\Scripts\activate

# 2. Activate (Mac/Linux)
source venv/bin/activate

# 3. Install dependencies (first time only)
pip install -r requirements.txt

# 4. Run the app
python app.py
# → Open http://localhost:5000
```

## CSV Format
**File:** `csv/books.csv`  
**Columns:** `Author, Series, Title, Year, Status`  
**Status values:** `Read`, `Reading`, `Hold`, `n/a`, or blank (blank = not yet read)

## Business Logic
- **Next 10 to Read** — first 10 books in CSV order where `Status` column is blank
- **All Books** — full list with color-coded status badges; filterable by status; searchable by title/author/series

## Known Data Quirks
- Some years are negative (e.g. `-1989`) — app takes `abs()` to fix display
- ~15 blank rows in CSV — app skips rows where `Title` is empty
- Last row has missing Author/Series — handled gracefully

## Google Sheets Integration
The app reads book data from a Google Sheet (falling back to `csv/books.csv` if unavailable).

- **Sheet ID:** `1WuO8vyFegtg6eI7f9V4eMm6vMkzxhDCo1DfSBT-pnDo`
- **Sheet URL:** https://drive.google.com/drive/folders/1jxJ6MIjZEe0O_fV6E47j05Zq9PTDFxVi
- **Service account:** `reading-jouney-app@reading-jouney.iam.gserviceaccount.com`
- **Credentials file:** `credentials.json` in project root (git-ignored — never commit this)
- **Cache:** Sheet data is cached for 5 minutes (`CACHE_TTL = 300` in app.py)

To set up on a new machine:
1. Get `credentials.json` from the Google Cloud Console (or from a secure store)
2. Place it in the project root
3. `SHEET_ID` is already set in `app.py`

## Git & GitHub
- **Repo:** `reading_journey` on GitHub (rogersonra)
- **Branch:** `main`
- Commit every logical change with a clear message (`feat:`, `fix:`, `docs:`, `chore:`)
- Always push to GitHub after committing so there is a saved version to revert to

## Developing Without Disrupting the Live App
The app is kept always-on via a Windows Scheduled Task (`ReadingJourneyApp`), which
runs `start_app.ps1` → `python app.py` directly out of this checked-out directory on
port 5000 (reachable on the local network for Mom, e.g. `http://10.0.0.29:5000`).
Because `app.run(..., debug=True, ...)` uses Flask's auto-reloader, **any edit saved
to `app.py` in this directory restarts the live server immediately** — so new feature
work should not happen here directly.

Instead, use a git worktree as a second, independent working directory:
```bash
git worktree add ../reading_journey-dev -b feat/<name>
```
Then in `reading_journey-dev/`:
1. Copy the git-ignored `config.py` and `credentials.json` from the live directory
   (a worktree only contains tracked files).
2. Run it with the live venv's interpreter on a different port so both copies can run
   at once:
   ```bash
   PORT=5001 ../reading_journey/venv/Scripts/python.exe app.py
   ```
   (`PORT` defaults to 5000 if unset, so the live app's behavior is unchanged.)
3. **Caveat:** both copies point at the same `SHEET_ID`, so status changes made while
   testing (Read/Borrowed/Hold buttons, the edit modal) write to the real shared
   Google Sheet — be deliberate before testing anything that calls
   `update_book_status`/`edit_book`.

To ship a finished feature: merge the feature branch into `main`, then `git pull` in
the **live** directory — the reloader picks up the new `app.py` and restarts
automatically. Remove the worktree when done (`git worktree remove
../reading_journey-dev`).
