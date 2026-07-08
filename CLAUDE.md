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
