"""Load cfpb_complaints.csv into clean.complaints, harmonizing product labels."""

import csv
from datetime import datetime
from postgres_connection import get_connection

from pathlib import Path
#pattern works from any working directory as path to data folder calculated relative to scripts real location
DATA_DIR = Path(__file__).resolve().parent.parent / "capstone_data"
SOURCE_FILE = DATA_DIR /  "cfpb_complaints.csv"

# Since CFPB renamed its product labels August 2023, collapsing old and new spellings into one canonical name. Old labels
# map to the new label:
PRODUCT_HARMONIZATION = {
    "Credit card": "Credit card",
    "Credit card or prepaid card": "Credit card",
    "Checking or savings account": "Checking or savings account",
    "Mortgage": "Mortgage",
    "Vehicle loan or lease": "Vehicle loan or lease",
    "Payday loan, title loan, or personal loan": "Payday loan, title loan, personal loan, or advance loan",
    "Payday loan, title loan, personal loan, or advance loan": "Payday loan, title loan, personal loan, or advance loan",
    "Money transfer, virtual currency, or money service": "Money transfer, virtual currency, or money service",
    "Student loan": "Student loan",
}

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS clean;

CREATE TABLE IF NOT EXISTS clean.complaints (
    complaint_id                    BIGINT PRIMARY KEY,
    date_received                   DATE,
    date_sent_to_company            DATE,
    product_reported                TEXT,
    harmonized_product              TEXT NOT NULL,
    sub_product                     TEXT,
    issue                           TEXT,
    sub_issue                       TEXT,
    company_name                    TEXT,
    company_public_response         TEXT,
    company_response_to_consumer    TEXT,
    is_timely_response              BOOLEAN,
    consumer_state_code             TEXT,
    consumer_zip_code               TEXT,
    consumer_tags                   TEXT,
    submitted_via_channel           TEXT
);
"""

COLUMNS = ["complaint_id", "date_received", "date_sent_to_company", "product_reported", "harmonized_product", "sub_product",
           "issue", "sub_issue", "company_name", "company_public_response", "company_response_to_consumer",
           "is_timely_response", "consumer_state_code", "consumer_zip_code", "consumer_tags", "submitted_via_channel",]

#VALUES are named placeholders in form %(column_name)s for executemany()
INSERT_SQL = f"INSERT INTO clean.complaints ({', '.join(COLUMNS)}) VALUES ({', '.join('%(' + c + ')s' for c in COLUMNS)});"

def fix_date(value):
    """YYYY-MM-DD -> date. Blank -> None."""
    if value == "" or value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()

def harmonize_product(product_reported):
    """Map CFPB product label to canonical name. Unknowns kept."""
    if product_reported is None:
        return "Unknown"
    return PRODUCT_HARMONIZATION.get(product_reported, product_reported)

def fix_state_code(value):
    """Two uppercase letters or NULL. Anything else is not US state code."""
    if value is None:
        return None
    cleaned = value.strip().upper()
    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned
    return None

def clean_csv_row(record):
    """Turn one CSV row into flat dict matching table."""
    return {
        "complaint_id": int(record["Complaint ID"]), #primary key so want loud fail if missing "Complaint ID' instead of None
        "date_received": fix_date(record.get("Date received")),
        "date_sent_to_company": fix_date(record.get("Date sent to company")),
        "product_reported": record.get("Product"),
        "harmonized_product": harmonize_product(record.get("Product")),
        "sub_product": record.get("Sub-product") or None, #or None converts empty string to None -> NULL in PostgresSQL
        "issue": record.get("Issue") or None,
        "sub_issue": record.get("Sub-issue") or None,
        #company_name in clean.complaints is raw CFPB value which has to match clean.company_crosswalk.company_name for FK.
        "company_name": record.get("Company").lower() if record.get("Company") else None,
        "company_public_response": record.get("Company public response") or None,
        "company_response_to_consumer": record.get("Company response to consumer") or None,
        "is_timely_response": record.get("Timely response?") == "Yes",
        "consumer_state_code": fix_state_code(record.get("State")) or None,
        "consumer_zip_code": record.get("ZIP code") or None,
        "consumer_tags": record.get("Tags") or None,
        "submitted_via_channel": record.get("Submitted via"),
    }

def main():
    with open(SOURCE_FILE, newline="") as f:
        reader = csv.DictReader(f) #DictReader = iterator of dicts keyed by the CSV header row returning every field as string
        rows = [clean_csv_row(record) for record in reader]

    #open 2 context managers in sequence:
        #get_connection() returns psycopg2 connection object which is pipe from Python to Postgres
        #db_connect.cursor() returns a cursor object from that connection which is the worker on pipe to Postgres
    with get_connection() as db_connect, db_connect.cursor() as cursor_object:
        cursor_object.execute(CREATE_TABLE_SQL)
        cursor_object.execute("TRUNCATE clean.complaints;")
        cursor_object.executemany(INSERT_SQL, rows)
        db_connect.commit()

    print(f"clean.complaints loaded: {len(rows)} rows")

if __name__ == "__main__":
    main()