"""Load fdic_failures.csv into clean.failures."""

import csv
from datetime import datetime
from postgres_connection import get_connection

from pathlib import Path
#pattern works from any working directory as path to data folder calculated relative to scripts real location
DATA_DIR = Path(__file__).resolve().parent.parent / "capstone_data"
SOURCE_FILE = DATA_DIR / "fdic_failures.csv"

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS clean;

CREATE TABLE IF NOT EXISTS clean.failures (
    failure_id                                      INTEGER PRIMARY KEY,
    fdic_certificate_number                         INTEGER,
    institution_name                                TEXT,
    headquarters_city                               TEXT,
    headquarters_state_code                         TEXT,
    city_and_state                                  TEXT,
    failure_date                                    DATE,
    failure_year                                    INTEGER,
    resolution_date                                 DATE,
    resolution_type                                 TEXT,
    transaction_type_code                           TEXT,
    charter_class_code                              TEXT,
    total_assets_at_failure_thousands               BIGINT,
    total_deposits_at_failure_thousands             BIGINT,
    estimated_loss_to_insurance_fund_thousands      BIGINT,
    uninsured_deposits_at_failure_thousands         BIGINT,
    insurance_fund_code                             TEXT,
    acquiring_institution_name                      TEXT,
    acquiring_city                                  TEXT,
    acquiring_state_code                            TEXT,
    fdic_press_release_url                          TEXT,
    fdic_comments                                   TEXT,
    api_record_id                                   TEXT
);
"""

COLUMNS = ["failure_id", "fdic_certificate_number", "institution_name", "headquarters_city", "headquarters_state_code",
           "city_and_state", "failure_date", "failure_year", "resolution_date", "resolution_type", "transaction_type_code",
           "charter_class_code", "total_assets_at_failure_thousands", "total_deposits_at_failure_thousands",
           "estimated_loss_to_insurance_fund_thousands", "uninsured_deposits_at_failure_thousands", "insurance_fund_code",
           "acquiring_institution_name", "acquiring_city", "acquiring_state_code", "fdic_press_release_url", "fdic_comments",
           "api_record_id",]

#VALUES are named placeholders in form %(column_name)s for executemany()
INSERT_SQL = f"INSERT INTO clean.failures ({', '.join(COLUMNS)}) VALUES ({', '.join('%(' + c + ')s' for c in COLUMNS)});"

def to_integer(value):
    """CSV integer field -> Python int or None if blank."""
    if value == "" or value is None:
        return None
    return int(float(value))

def to_decimal(value):
    """CSV dollar field -> Python int (thousands) or None if blank."""
    if value == "" or value is None:
        return None
    return int(float(value))

def fix_date(value):
    """M/D/YYYY or YYYY-MM-DD -> date. Blank -> None."""
    if value == "" or value is None:
        return None
    if len(value) == 10 and value[4] == "-":
        return datetime.strptime(value, "%Y-%m-%d").date()
    return datetime.strptime(value, "%m/%d/%Y").date()

def fix_state_code(value):
    """Two uppercase letters or NULL. Anything else is not US state code."""
    if value is None:
        return None
    cleaned = value.strip().upper()
    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned
    return None

def clean_csv_row(record, failure_id):
    """Turn one CSV row into a flat dict matching table."""
    return {
        "failure_id": failure_id,
        "fdic_certificate_number": to_integer(record.get("CERT")),
        "institution_name": record.get("NAME"),
        "headquarters_city": record.get("CITY"),
        "headquarters_state_code": fix_state_code(record.get("PSTALP")),
        "city_and_state": record.get("CITYST"),
        "failure_date": fix_date(record.get("FAILDATE")),
        "failure_year": to_integer(record.get("FAILYR")),
        "resolution_date": fix_date(record.get("RESDATE")),
        "resolution_type": record.get("RESTYPE"),
        "transaction_type_code": record.get("RESTYPE1"),
        "charter_class_code": record.get("CHCLASS1"),
        "total_assets_at_failure_thousands": to_decimal(record.get("QBFASSET")),
        "total_deposits_at_failure_thousands": to_decimal(record.get("QBFDEP")),
        "estimated_loss_to_insurance_fund_thousands": to_decimal(record.get("COST")),
        "uninsured_deposits_at_failure_thousands": to_decimal(record.get("UNINSDEP")),
        "insurance_fund_code": record.get("SAVR"),
        "acquiring_institution_name": record.get("BIDNAME"),
        "acquiring_city": record.get("BIDCITY"),
        "acquiring_state_code": fix_state_code(record.get("BIDSTATE")),
        "fdic_press_release_url": record.get("URL"),
        "fdic_comments": record.get("COMMENTS"),
        "api_record_id": record.get("ID"),
    }

def main():
    with open(SOURCE_FILE, newline="") as f:
        reader = csv.DictReader(f) #DictReader = iterator of dicts keyed by the CSV header row returning every field as string
        rows = [clean_csv_row(record, i + 1) for i, record in enumerate(reader)]

    #open 2 context managers in sequence:
        #get_connection() returns psycopg2 connection object which is pipe from Python to Postgres
        #db_connect.cursor() returns a cursor object from that connection which is the worker on pipe to Postgres
    with get_connection() as db_connect, db_connect.cursor() as cursor_object:
        cursor_object.execute(CREATE_TABLE_SQL)
        cursor_object.execute("TRUNCATE clean.failures;")
        cursor_object.executemany(INSERT_SQL, rows)
        db_connect.commit()

    print(f"clean.failures loaded: {len(rows)} rows")

if __name__ == "__main__":
    main()