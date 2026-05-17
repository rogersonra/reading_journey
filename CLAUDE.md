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
**Columns:** `Author, Series, Title, Year, Rob, Mom`  
**Status values:** `Read`, `Reading`, `Hold`, `n/a`, or blank (blank = not yet read)

## Business Logic
- **Next 10 to Read** — first 10 books in CSV order where `Rob` column is blank
- **All Books** — full list with color-coded status badges; filterable by status; searchable by title/author/series

## Known Data Quirks
- Some years are negative (e.g. `-1989`) — app takes `abs()` to fix display
- ~15 blank rows in CSV — app skips rows where `Title` is empty
- Last row has missing Author/Series — handled gracefully

## Git & GitHub
- **Repo:** `reading_journey` on GitHub (rogersonra)
- **Branch:** `main`
- Commit every logical change with a clear message (`feat:`, `fix:`, `docs:`, `chore:`)
- Always push to GitHub after committing so there is a saved version to revert to
