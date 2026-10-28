"""Load fdic_financials.csv into clean.financials, converting YTD income to quarterly."""
import pandas as pd
import numpy as np
from postgres_connection import get_connection
from psycopg2.extras import execute_values
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "capstone_data"
SOURCE_FILE = DATA_DIR / "fdic_financials.csv"

YTD_FIELDS = {
    "NETINC": "net_income",
    "INTINC": "interest_income",
    "EINTEXP": "interest_expense",
    "NONII": "noninterest_income",
    "NONIX": "noninterest_expense",
    "ELNATR": "provision_for_credit_losses",
}

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS clean;
CREATE TABLE IF NOT EXISTS clean.financials (
    fdic_certificate_number INTEGER NOT NULL,
    report_date DATE NOT NULL,
    report_year INTEGER NOT NULL,
    report_quarter INTEGER NOT NULL,
    total_assets_thousands BIGINT,
    total_deposits_thousands BIGINT,
    domestic_deposits_thousands BIGINT,
    uninsured_deposits_thousands BIGINT,
    total_equity_thousands BIGINT,
    tier_one_risk_based_capital_thousands BIGINT,
    net_loans_and_leases_thousands BIGINT,
    gross_loans_and_leases_thousands BIGINT,
    real_estate_loans_thousands BIGINT,
    loan_loss_allowance_thousands BIGINT,
    noncurrent_loans_thousands BIGINT,
    assets_30_to_89_days_past_due_thousands BIGINT,
    assets_90_plus_days_past_due_thousands BIGINT,
    securities_held_thousands BIGINT,
    return_on_assets_percent NUMERIC,
    return_on_equity_percent NUMERIC,
    equity_to_assets_percent NUMERIC,
    noncurrent_loan_rate_percent NUMERIC,
    nonperforming_assets_rate_percent NUMERIC,
    net_interest_margin_percent NUMERIC,
    net_income_ytd_thousands BIGINT,
    net_income_quarterly_thousands BIGINT,
    interest_income_ytd_thousands BIGINT,
    interest_income_quarterly_thousands BIGINT,
    interest_expense_ytd_thousands BIGINT,
    interest_expense_quarterly_thousands BIGINT,
    noninterest_income_ytd_thousands BIGINT,
    noninterest_income_quarterly_thousands BIGINT,
    noninterest_expense_ytd_thousands BIGINT,
    noninterest_expense_quarterly_thousands BIGINT,
    provision_for_credit_losses_ytd_thousands BIGINT,
    provision_for_credit_losses_quarterly_thousands BIGINT,
    employee_count INTEGER,
    domestic_office_count INTEGER,
    api_record_id TEXT,
    PRIMARY KEY (fdic_certificate_number, report_date)
);
"""


def main():
    # dtype parameter forces Pandas to explicitly interpret CERT column as int while loading CSV to avoid guessing float
    df = pd.read_csv(SOURCE_FILE, dtype={'CERT': int})

    df['report_date'] = pd.to_datetime(df['REPDTE'], format='%Y%m%d')
    df['report_year'] = df['report_date'].dt.year
    df['report_quarter'] = df['report_date'].dt.quarter
    df['fdic_certificate_number'] = df['CERT']

    # Rename base columns
    df = df.rename(columns={
        'ASSET': 'total_assets_thousands', 'DEP': 'total_deposits_thousands',
        'DEPDOM': 'domestic_deposits_thousands', 'DEPUNINS': 'uninsured_deposits_thousands',
        'EQ': 'total_equity_thousands', 'RBCT1J': 'tier_one_risk_based_capital_thousands',
        'LNLSNET': 'net_loans_and_leases_thousands', 'LNLSGR': 'gross_loans_and_leases_thousands',
        'LNRE': 'real_estate_loans_thousands', 'LNATRES': 'loan_loss_allowance_thousands',
        'NCLNLS': 'noncurrent_loans_thousands', 'P3ASSET': 'assets_30_to_89_days_past_due_thousands',
        'P9ASSET': 'assets_90_plus_days_past_due_thousands', 'SC': 'securities_held_thousands',
        'ROA': 'return_on_assets_percent', 'ROE': 'return_on_equity_percent',
        'EQV': 'equity_to_assets_percent', 'NCLNLSR': 'noncurrent_loan_rate_percent',
        'NPERFV': 'nonperforming_assets_rate_percent', 'NIMY': 'net_interest_margin_percent',
        'NUMEMP': 'employee_count', 'OFFDOM': 'domestic_office_count', 'ID': 'api_record_id'
    })

    # YTD to quarterly math
    df = df.sort_values(['fdic_certificate_number', 'report_year', 'report_quarter'])

    for ytd_col, name in YTD_FIELDS.items():
        df = df.rename(columns={ytd_col: f"{name}_ytd_thousands"})
        ytd_name = f"{name}_ytd_thousands"
        q_name = f"{name}_quarterly_thousands"

        # Get previous quarter's YTD
        prior_ytd = df.groupby(['fdic_certificate_number', 'report_year'])[ytd_name].shift(1)
        prior_q = df.groupby(['fdic_certificate_number', 'report_year'])['report_quarter'].shift(1)

        # Calculate quarterly based on Q1 (no shift) or Q2-Q4 (YTD - prior YTD)
        # np.where(condition, value_if_true, value_if_false)
        df[q_name] = np.where(
            df['report_quarter'] == 1, df[ytd_name],
            np.where(
                (df['report_quarter'] > 1) & (prior_q == df['report_quarter'] - 1),
                df[ytd_name] - prior_ytd,
                np.nan
            )
        )

    # Reorder to match INSERT SQL exactly
    cols = ['fdic_certificate_number', 'report_date', 'report_year', 'report_quarter', 'total_assets_thousands',
        'total_deposits_thousands', 'domestic_deposits_thousands', 'uninsured_deposits_thousands',
        'total_equity_thousands', 'tier_one_risk_based_capital_thousands', 'net_loans_and_leases_thousands',
        'gross_loans_and_leases_thousands', 'real_estate_loans_thousands', 'loan_loss_allowance_thousands',
        'noncurrent_loans_thousands', 'assets_30_to_89_days_past_due_thousands',
        'assets_90_plus_days_past_due_thousands', 'securities_held_thousands', 'return_on_assets_percent',
        'return_on_equity_percent', 'equity_to_assets_percent', 'noncurrent_loan_rate_percent',
        'nonperforming_assets_rate_percent', 'net_interest_margin_percent', 'net_income_ytd_thousands',
        'net_income_quarterly_thousands', 'interest_income_ytd_thousands', 'interest_income_quarterly_thousands',
        'interest_expense_ytd_thousands', 'interest_expense_quarterly_thousands', 'noninterest_income_ytd_thousands',
        'noninterest_income_quarterly_thousands', 'noninterest_expense_ytd_thousands',
        'noninterest_expense_quarterly_thousands', 'provision_for_credit_losses_ytd_thousands',
        'provision_for_credit_losses_quarterly_thousands', 'employee_count', 'domestic_office_count', 'api_record_id']

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
        cursor_object.execute("TRUNCATE clean.financials;")
        execute_values(cursor_object, f"INSERT INTO clean.financials ({', '.join(cols)}) VALUES %s", rows)
        db_connect.commit()

    print(f"clean.financials loaded: {len(df)} rows")


if __name__ == "__main__":
    main()