# Changelog

## [1.0.0] - 2026-07-08

First versioned release, marking the app's baseline feature set after its initial development.

### Core
- Flask app reading book data from a Google Sheet, with automatic fallback to `csv/books.csv`
- "Next Reads" section showing the next books to read, rotating through authors
- "Bookshelf" section for books currently Reading, Borrowed, or On Hold
- "All Books" table grouped by author and series, with collapsible rows and read-percentage stats

### Search & discovery
- Combined author/series search with English-only filtering
- "Find New Books" modal via the Hardcover API, with select-all support
- Book description popups when clicking a title in search results

### Editing & status
- Inline edit modal for title/author/series/year/status, saved directly to the Sheet
- Live status updates (Read / Reading / Hold / Borrowed / n/a) without a page reload
- Skip and "Borrow on Libby" actions on Next Reads cards

### Bookshelf overhaul
- Renamed the `Rob` column to `Status` (in both the Sheet and CSV) and removed the unused `Mom` column
- Added support for a `Borrowed` status, shown between Reading and On Hold
- Standout "Currently Reading" badge styling for actively-read books
