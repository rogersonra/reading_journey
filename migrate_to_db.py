"""One-time migration: loads csv/books.csv into the pub400 BOOKS table.

Run once:
    python migrate_to_db.py

The table must already exist on pub400. Create it first with:

    CREATE TABLE <library>.BOOKS (
        AUTHOR  VARCHAR(200)  DEFAULT '',
        SERIES  VARCHAR(200)  DEFAULT '',
        TITLE   VARCHAR(500)  NOT NULL,
        YEAR    SMALLINT,
        ROB     VARCHAR(20)   DEFAULT '',
        MOM     VARCHAR(20)   DEFAULT ''
    );
"""
import csv
import pyodbc
from pathlib import Path
from config import PUB400_DSN, PUB400_USER, PUB400_PASS, PUB400_LIB

CSV_PATH = Path(__file__).resolve().parent / "csv" / "books.csv"


def parse_year(val):
    try:
        return abs(int(val))
    except (TypeError, ValueError):
        return None


conn = pyodbc.connect(
    driver='{IBM i Access ODBC Driver}',
    System=PUB400_DSN,
    Uid=PUB400_USER,
    Pwd=PUB400_PASS,
    nam=1,
    dbq=', *LIBL',
    translate=1,
    CCSID=1208,
    autocommit=True,
)

count = 0
with open(CSV_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = list(reader.fieldnames or [])
    if fieldnames and fieldnames[0] == "":
        fieldnames[0] = "Author"
        reader.fieldnames = fieldnames

    for row in reader:
        title = row.get("Title", "").strip()
        if not title:
            continue
        conn.execute(
            "INSERT INTO BOOKS (AUTHOR, SERIES, TITLE, YEAR, ROB, MOM) VALUES (?, ?, ?, ?, ?, ?)",
            (
                row.get("Author", "").strip(),
                row.get("Series", "").strip(),
                title,
                parse_year(row.get("Year", "")),
                row.get("Rob", "").strip(),
                row.get("Mom", "").strip(),
            ),
        )
        count += 1

conn.commit()
conn.close()
print(f"Migrated {count} books to {PUB400_LIB}.BOOKS on {PUB400_DSN}.")
