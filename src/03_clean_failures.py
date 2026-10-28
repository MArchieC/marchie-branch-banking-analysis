"""Load fdic_failures.csv into clean.failures using pandas."""
import pandas as pd
import numpy as np
from postgres_connection import get_connection
from psycopg2.extras import execute_values
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "capstone_data"
SOURCE_FILE = DATA_DIR / "fdic_failures.csv"

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS clean;
CREATE TABLE IF NOT EXISTS clean.failures (
    failure_id INTEGER PRIMARY KEY,
    fdic_certificate_number INTEGER,
    institution_name TEXT,
    headquarters_city TEXT,
    headquarters_state_code TEXT,
    city_and_state TEXT,
    failure_date DATE,
    failure_year INTEGER,
    resolution_date DATE,
    resolution_type TEXT,
    transaction_type_code TEXT,
    charter_class_code TEXT,
    total_assets_at_failure_thousands BIGINT,
    total_deposits_at_failure_thousands BIGINT,
    estimated_loss_to_insurance_fund_thousands BIGINT,
    uninsured_deposits_at_failure_thousands BIGINT,
    insurance_fund_code TEXT,
    acquiring_institution_name TEXT,
    acquiring_city TEXT,
    acquiring_state_code TEXT,
    fdic_press_release_url TEXT,
    fdic_comments TEXT,
    api_record_id TEXT
);
"""


def main():
    df = pd.read_csv(SOURCE_FILE)

    df['failure_id'] = range(1, len(df) + 1)
    df['fdic_certificate_number'] = df['CERT']

    # pd.to_datetime handles M/D/YYYY and YYYY-MM-DD automatically
    df['failure_date'] = pd.to_datetime(df['FAILDATE'], errors='coerce')
    df['resolution_date'] = pd.to_datetime(df['RESDATE'], errors='coerce')

    df = df.rename(columns={
        'NAME': 'institution_name', 'CITY': 'headquarters_city', 'CITYST': 'city_and_state',
        'FAILYR': 'failure_year', 'RESTYPE': 'resolution_type', 'RESTYPE1': 'transaction_type_code',
        'CHCLASS1': 'charter_class_code', 'QBFASSET': 'total_assets_at_failure_thousands',
        'QBFDEP': 'total_deposits_at_failure_thousands', 'COST': 'estimated_loss_to_insurance_fund_thousands',
        'UNINSDEP': 'uninsured_deposits_at_failure_thousands', 'SAVR': 'insurance_fund_code',
        'BIDNAME': 'acquiring_institution_name', 'BIDCITY': 'acquiring_city', 'URL': 'fdic_press_release_url',
        'COMMENTS': 'fdic_comments', 'ID': 'api_record_id'
    })

    # Clean State Codes
    for col in ['PSTALP', 'BIDSTATE']:
        target = 'headquarters_state_code' if col == 'PSTALP' else 'acquiring_state_code'
        df[target] = df[col].astype(str).str.strip().str.upper()
        df[target] = np.where(df[target].str.len() == 2, df[target], np.nan)

    cols = ['failure_id', 'fdic_certificate_number', 'institution_name', 'headquarters_city', 'headquarters_state_code',
        'city_and_state', 'failure_date', 'failure_year', 'resolution_date', 'resolution_type', 'transaction_type_code',
        'charter_class_code', 'total_assets_at_failure_thousands', 'total_deposits_at_failure_thousands',
        'estimated_loss_to_insurance_fund_thousands', 'uninsured_deposits_at_failure_thousands', 'insurance_fund_code',
        'acquiring_institution_name', 'acquiring_city', 'acquiring_state_code', 'fdic_press_release_url',
        'fdic_comments', 'api_record_id']

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
        cursor_object.execute("TRUNCATE clean.failures;")
        execute_values(cursor_object, f"INSERT INTO clean.failures ({', '.join(cols)}) VALUES %s", rows)
        db_connect.commit()

    print(f"clean.failures loaded: {len(df)} rows")


if __name__ == "__main__":
    main()