"""Load cfpb_complaints.csv into clean.complaints, harmonizing product labels."""
import pandas as pd
import numpy as np
from postgres_connection import get_connection
from psycopg2.extras import execute_values
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "capstone_data"
SOURCE_FILE = DATA_DIR / "cfpb_complaints.csv"

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
    complaint_id BIGINT PRIMARY KEY,
    date_received DATE,
    date_sent_to_company DATE,
    product_reported TEXT,
    harmonized_product TEXT NOT NULL,
    sub_product TEXT,
    issue TEXT,
    sub_issue TEXT,
    company_name TEXT,
    company_public_response TEXT,
    company_response_to_consumer TEXT,
    is_timely_response BOOLEAN,
    consumer_state_code TEXT,
    consumer_zip_code TEXT,
    consumer_tags TEXT,
    submitted_via_channel TEXT
);
"""


def main():
    df = pd.read_csv(SOURCE_FILE)

    df['complaint_id'] = df['Complaint ID']
    df['date_received'] = pd.to_datetime(df['Date received'], errors='coerce')
    df['date_sent_to_company'] = pd.to_datetime(df['Date sent to company'], errors='coerce')

    df['product_reported'] = df['Product']
    df['harmonized_product'] = df['Product'].replace(PRODUCT_HARMONIZATION).fillna('Unknown')

    df['company_name'] = df['Company'].str.lower()
    df['is_timely_response'] = df['Timely response?'] == 'Yes'

    # Clean State Code
    df['consumer_state_code'] = df['State'].astype(str).str.strip().str.upper()
    df['consumer_state_code'] = np.where(df['consumer_state_code'].str.len() == 2, df['consumer_state_code'], np.nan)

    df = df.rename(columns={
        'Sub-product': 'sub_product', 'Issue': 'issue', 'Sub-issue': 'sub_issue',
        'Company public response': 'company_public_response',
        'Company response to consumer': 'company_response_to_consumer',
        'ZIP code': 'consumer_zip_code', 'Tags': 'consumer_tags', 'Submitted via': 'submitted_via_channel'
    })

    # Replace empty strings with NaN
    text_cols = ['sub_product', 'issue', 'sub_issue', 'company_public_response', 'company_response_to_consumer',
                 'consumer_zip_code', 'consumer_tags']
    for col in text_cols:
        df[col] = df[col].replace(r'^\s*$', np.nan, regex=True)

    cols = ['complaint_id', 'date_received', 'date_sent_to_company', 'product_reported', 'harmonized_product',
        'sub_product', 'issue', 'sub_issue', 'company_name', 'company_public_response', 'company_response_to_consumer',
        'is_timely_response', 'consumer_state_code', 'consumer_zip_code', 'consumer_tags', 'submitted_via_channel']

    for c in cols:
        # df.columns returns names of all columns currently inside Pandas DataFrame.
        if c not in df.columns: df[c] = np.nan
    df = df[cols]

    # Bulk Insert
    # Finds every NaN in DataFrame and swaps for Python's None object which psycopg2 correctly translates to SQL NULL
    # execute_values requires each row to be a tuple
    rows = [tuple(x) for x in df.replace({np.nan: None}).to_numpy()]

    with get_connection() as db_connect, db_connect.cursor() as cursor_object:
        cursor_object.execute(CREATE_TABLE_SQL)
        cursor_object.execute("TRUNCATE clean.complaints;")
        execute_values(cursor_object, f"INSERT INTO clean.complaints ({', '.join(cols)}) VALUES %s", rows)
        db_connect.commit()

    print(f"clean.complaints loaded: {len(df)} rows")


if __name__ == "__main__":
    main()