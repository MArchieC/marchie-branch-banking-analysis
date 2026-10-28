"""Load four FRED series into clean.macro_quarterly, aligned to quarter-end."""

import csv
from datetime import date, timedelta
from postgres_connection import get_connection

from pathlib import Path
#pattern works from any working directory as path to data folder calculated relative to scripts real location
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Raw files
RAW_DIR = PROJECT_ROOT / "capstone_data"

# Series name -> file path. Series name is also the target column in clean.macro_quarterly.
FRED_FILES = {
    "federal_funds_rate_percent":        RAW_DIR / "fred_FEDFUNDS.csv",
    "unemployment_rate_percent":         RAW_DIR / "fred_UNRATE.csv",
    "thirty_year_mortgage_rate_percent": RAW_DIR / "fred_MORTGAGE30US.csv",
    "ten_year_treasury_yield_percent":   RAW_DIR / "fred_DGS10.csv",
}

# Quarter grid covers fdic_financials.csv window (2006 Q1 to 2026 Q2) per DATA_DICTIONARY.md window column
START_QUARTER = date(2006, 3, 31)
END_QUARTER   = date(2026, 6, 30)

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS clean;

CREATE TABLE IF NOT EXISTS clean.macro_quarterly (
    quarter_end_date                    DATE PRIMARY KEY,
    federal_funds_rate_percent          NUMERIC,
    unemployment_rate_percent           NUMERIC,
    thirty_year_mortgage_rate_percent   NUMERIC,
    ten_year_treasury_yield_percent     NUMERIC
);
"""

# Column order used for INSERT kept as list so INSERT is built from same source of truth row builder uses.
COLUMNS = ["quarter_end_date", "federal_funds_rate_percent", "unemployment_rate_percent", "thirty_year_mortgage_rate_percent",
           "ten_year_treasury_yield_percent",]
#VALUES are named placeholders in form %(column_name)s for executemany()
INSERT_SQL = f"INSERT INTO clean.macro_quarterly ({', '.join(COLUMNS)}) VALUES ({', '.join('%(' + c + ')s' for c in COLUMNS)});"

def yield_quarter_end_dates(start, end):
    """Yield quarter end dates from start through end inclusive."""
    current = start
    while current <= end:
        yield current #turns function into generator function with internal state (current) preserved between yield calls

        year = current.year
        month = current.month + 3

        if month > 12:
            month -= 12
            year += 1

        #Use datetime.date object holding first day of month after (year, month).
        #date(year, month, day) takes three integer arguments
        first_of_next = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1,1)

        # First day of next month after current quarter, minus one day = last day of current quarter.
        current = first_of_next - timedelta(days=1) #timedelta permits date math

def yield_fred_series(file_path) -> list[tuple]:
    """Return list of (observation_date, value) sorted ascending while skipping blank observations."""
    points: list[tuple] = []
    with open(file_path, newline="") as f:
        fred_reader = csv.DictReader(f) #DictReader = iterator of dicts keyed by the CSV header row returning every field as string
        for fred_record in fred_reader:
            raw_date = fred_record.get("observation_date")
            # FRED files have exactly two columns - second column is series value.
            raw_value = list(fred_record.values())[1]
            if raw_date is None or raw_value == "" or raw_value is None:
                continue
            #date.fromisoformat(raw_date) converts date string to native Python datetime.date object.
            points.append((date.fromisoformat(raw_date), float(raw_value)))
    points.sort()
    return points

def fix_macro_value(points, quarter_end) -> float|None:
    """Last observation on or before quarter_end. None if the series has nothing yet."""
    result = None
    for observation_date, value in points:
        if observation_date <= quarter_end:
            result = value
        else:
            break
    return result

def main():
    fred_series = {name: yield_fred_series(path) for name, path in FRED_FILES.items()}

    rows: list[dict] = []
    for quarter_end in yield_quarter_end_dates(START_QUARTER, END_QUARTER):
        row = {"quarter_end_date": quarter_end}
        for series_name in FRED_FILES:
            row[series_name] = fix_macro_value(fred_series[series_name], quarter_end)
        rows.append(row)

    #open 2 context managers in sequence:
        #get_connection() returns psycopg2 connection object which is pipe from Python to Postgres
        #db_connect.cursor() returns a cursor object from that connection which is the worker on pipe to Postgres
    with get_connection() as db_connect, db_connect.cursor() as cursor_object:
        cursor_object.execute(CREATE_TABLE_SQL)
        cursor_object.execute("TRUNCATE clean.macro_quarterly;")
        cursor_object.executemany(INSERT_SQL, rows)
        db_connect.commit()

    print(f"clean.macro_quarterly loaded: {len(rows)} quarters")

if __name__ == "__main__":
    main()