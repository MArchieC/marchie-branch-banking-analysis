"""Flatten fdic_institutions.json into clean.institutions."""

import json
from datetime import datetime
from postgres_connection import get_connection

from pathlib import Path
#pattern works from any working directory as path to data folder calculated relative to scripts real location
DATA_DIR = Path(__file__).resolve().parent.parent / "capstone_data"
SOURCE_FILE = DATA_DIR / "fdic_institutions.json"
PLACEHOLDER_END_DATE = "12/31/9999"

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS clean;

CREATE TABLE IF NOT EXISTS clean.institutions (
    fdic_certificate_number       INTEGER PRIMARY KEY,
    institution_name              TEXT NOT NULL,
    headquarters_city             TEXT,
    headquarters_state_code       TEXT,
    headquarters_zip_code         TEXT,
    total_assets_thousands        BIGINT,
    total_deposits_thousands      BIGINT,
    is_active                     BOOLEAN NOT NULL,
    charter_class_code            TEXT,
    holding_company_name          TEXT,
    federal_reserve_rssd_id       TEXT,
    established_date              DATE,
    end_date                      DATE,
    website_address               TEXT,
    api_record_id                 TEXT
);
"""

#VALUES are named placeholders in form %(column_name)s for executemany()
INSERT_SQL = """
INSERT INTO clean.institutions (
    fdic_certificate_number, institution_name, headquarters_city, headquarters_state_code, 
    headquarters_zip_code, total_assets_thousands, total_deposits_thousands, is_active, 
    charter_class_code, holding_company_name, federal_reserve_rssd_id, established_date, end_date,
    website_address, api_record_id
) VALUES (
    %(fdic_certificate_number)s, %(institution_name)s, %(headquarters_city)s, %(headquarters_state_code)s, 
    %(headquarters_zip_code)s, %(total_assets_thousands)s, %(total_deposits_thousands)s, %(is_active)s, 
    %(charter_class_code)s, %(holding_company_name)s, %(federal_reserve_rssd_id)s, %(established_date)s, %(end_date)s,
    %(website_address)s, %(api_record_id)s
);
"""

def fix_date(value):
    """MM/DD/YYYY -> date and FDIC placeholder 12/31/9999 becomes NULL."""
    if value == "" or value is None:
        return None #becomes NULL in PostgreSQL
    if value == PLACEHOLDER_END_DATE:
        return None
    return datetime.strptime(value, "%m/%d/%Y").date() #strptime yields datetime.date and .date() drops time part

def trimmed_text_or_null_if_whitespace_or_empty_string(value):
    """Trimmed text or NULL if blank or empty string."""
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned == "":
        return None
    return cleaned

def clean_json_row(json_record):
    """Turn one nested JSON record into flat dict matching table."""
    data = json_record["data"]
    return {
        "fdic_certificate_number": int(data["CERT"]), #primary key so want loud fail due to KeyError if missing CERT instead of None/NULL
        # .get() yields None if key absent which is NULL in PostgreSQL
        "institution_name": data.get("NAME"), #set as not null in table definition as want loud fail if nameless row exists
        "headquarters_city": data.get("CITY"),
        "headquarters_state_code": data.get("STALP"),
        "headquarters_zip_code": data.get("ZIP"),
        "total_assets_thousands": data.get("ASSET"),
        "total_deposits_thousands": data.get("DEP"),
        "is_active": data.get("ACTIVE") == 1,
        "charter_class_code": trimmed_text_or_null_if_whitespace_or_empty_string(data.get("BKCLASS")),
        "holding_company_name": trimmed_text_or_null_if_whitespace_or_empty_string(data.get("NAMEHCR")),
        "federal_reserve_rssd_id": data.get("FED_RSSD"),
        "established_date": fix_date(data.get("ESTYMD")),
        "end_date": fix_date(data.get("ENDEFYMD")),
        "website_address": trimmed_text_or_null_if_whitespace_or_empty_string(data.get("WEBADDR")),
        "api_record_id": data.get("ID"),
    }

def main():
    with open(SOURCE_FILE) as f:
        records = json.load(f) #parse whole file into Python objects such that 'records' becomes list of dicts

    rows: list[dict] = [clean_json_row(r) for r in records]

    #open 2 context managers in sequence:
        #get_connection() returns psycopg2 connection object which is pipe from Python to Postgres
        #db_connect.cursor() returns a cursor object from that connection which is the worker on pipe to Postgres
    with get_connection() as db_connect, db_connect.cursor() as cursor_object:
        cursor_object.execute(CREATE_TABLE_SQL)
        cursor_object.execute("TRUNCATE clean.institutions;")
        cursor_object.executemany(INSERT_SQL, rows)
        db_connect.commit()

    print(f"clean.institutions loaded: {len(rows)} rows")

if __name__ == "__main__":
    main()