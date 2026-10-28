"""Load fdic_financials.csv into clean.financials, converting YTD income to quarterly."""

import csv
from datetime import datetime
from collections import defaultdict
from postgres_connection import get_connection

from pathlib import Path
#pattern works from any working directory as path to data folder calculated relative to scripts real location
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

# Column order used for INSERT. Kept as a list so INSERT is built from same source of truth row builder uses.
COLUMNS = ["fdic_certificate_number", "report_date", "report_year", "report_quarter", "total_assets_thousands",
           "total_deposits_thousands", "domestic_deposits_thousands", "uninsured_deposits_thousands",
           "total_equity_thousands", "tier_one_risk_based_capital_thousands", "net_loans_and_leases_thousands",
           "gross_loans_and_leases_thousands", "real_estate_loans_thousands", "loan_loss_allowance_thousands",
           "noncurrent_loans_thousands", "assets_30_to_89_days_past_due_thousands",
           "assets_90_plus_days_past_due_thousands", "securities_held_thousands", "return_on_assets_percent",
           "return_on_equity_percent", "equity_to_assets_percent", "noncurrent_loan_rate_percent",
           "nonperforming_assets_rate_percent", "net_interest_margin_percent", "net_income_ytd_thousands",
           "net_income_quarterly_thousands", "interest_income_ytd_thousands", "interest_income_quarterly_thousands",
           "interest_expense_ytd_thousands", "interest_expense_quarterly_thousands", "noninterest_income_ytd_thousands",
           "noninterest_income_quarterly_thousands", "noninterest_expense_ytd_thousands",
           "noninterest_expense_quarterly_thousands", "provision_for_credit_losses_ytd_thousands",
           "provision_for_credit_losses_quarterly_thousands", "employee_count", "domestic_office_count", "api_record_id"]

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS clean;

CREATE TABLE IF NOT EXISTS clean.financials (
    fdic_certificate_number                         INTEGER NOT NULL,
    report_date                                     DATE    NOT NULL,
    report_year                                     INTEGER NOT NULL,
    report_quarter                                  INTEGER NOT NULL,

    total_assets_thousands                          BIGINT,
    total_deposits_thousands                        BIGINT,
    domestic_deposits_thousands                     BIGINT,
    uninsured_deposits_thousands                    BIGINT,
    total_equity_thousands                          BIGINT,
    tier_one_risk_based_capital_thousands           BIGINT,
    net_loans_and_leases_thousands                  BIGINT,
    gross_loans_and_leases_thousands                BIGINT,
    real_estate_loans_thousands                     BIGINT,
    loan_loss_allowance_thousands                   BIGINT,
    noncurrent_loans_thousands                      BIGINT,
    assets_30_to_89_days_past_due_thousands         BIGINT,
    assets_90_plus_days_past_due_thousands          BIGINT,
    securities_held_thousands                       BIGINT,

    return_on_assets_percent                        NUMERIC,
    return_on_equity_percent                        NUMERIC,
    equity_to_assets_percent                        NUMERIC,
    noncurrent_loan_rate_percent                    NUMERIC,
    nonperforming_assets_rate_percent               NUMERIC,
    net_interest_margin_percent                     NUMERIC,

    net_income_ytd_thousands                        BIGINT,
    net_income_quarterly_thousands                  BIGINT,
    interest_income_ytd_thousands                   BIGINT,
    interest_income_quarterly_thousands             BIGINT,
    interest_expense_ytd_thousands                  BIGINT,
    interest_expense_quarterly_thousands            BIGINT,
    noninterest_income_ytd_thousands                BIGINT,
    noninterest_income_quarterly_thousands          BIGINT,
    noninterest_expense_ytd_thousands               BIGINT,
    noninterest_expense_quarterly_thousands         BIGINT,
    provision_for_credit_losses_ytd_thousands       BIGINT,
    provision_for_credit_losses_quarterly_thousands BIGINT,

    employee_count                                  INTEGER,
    domestic_office_count                           INTEGER,
    api_record_id                                   TEXT,

    PRIMARY KEY (fdic_certificate_number, report_date)
);
"""

#VALUES are named placeholders in form %(column_name)s for executemany()
INSERT_SQL = f"INSERT INTO clean.financials ({', '.join(COLUMNS)}) VALUES ({', '.join('%(' + c + ')s' for c in COLUMNS)});"

def to_integer(value):
    """CSV integer field -> Python int or None if blank."""
    if value == "" or value is None:
        return None
    return int(float(value))

def to_decimal(value):
    """CSV decimal field -> Python float or None if blank."""
    if value == "" or value is None:
        return None
    return float(value)

def fix_report_date(value):
    """YYYYMMDD -> date."""
    return datetime.strptime(value, "%Y%m%d").date() #strptime yields datetime.date and .date() drops time part

def clean_csv_row(record):
    """Turn one CSV row into flat dict matching table. Quarterly values filled later."""

    #clean raw date for use in matching table
    report_date = fix_report_date(record["REPDTE"])

    row: dict = {
        "fdic_certificate_number": int(record["CERT"]), #composite key member so want loud fail if missing CERT
        "report_date": report_date,
        "report_year": report_date.year,
        "report_quarter": ((report_date.month - 1) // 3) + 1,

        # .get() yields None if key absent which is NULL in PostgreSQL
        "total_assets_thousands": to_integer(record.get("ASSET")),
        "total_deposits_thousands": to_integer(record.get("DEP")),
        "domestic_deposits_thousands": to_integer(record.get("DEPDOM")),
        "uninsured_deposits_thousands": to_integer(record.get("DEPUNINS")),
        "total_equity_thousands": to_integer(record.get("EQ")),
        "tier_one_risk_based_capital_thousands": to_integer(record.get("RBCT1J")),
        "net_loans_and_leases_thousands": to_integer(record.get("LNLSNET")),
        "gross_loans_and_leases_thousands": to_integer(record.get("LNLSGR")),
        "real_estate_loans_thousands": to_integer(record.get("LNRE")),
        "loan_loss_allowance_thousands": to_integer(record.get("LNATRES")),
        "noncurrent_loans_thousands": to_integer(record.get("NCLNLS")),
        "assets_30_to_89_days_past_due_thousands": to_integer(record.get("P3ASSET")),
        "assets_90_plus_days_past_due_thousands": to_integer(record.get("P9ASSET")),
        "securities_held_thousands": to_integer(record.get("SC")),

        "return_on_assets_percent": to_decimal(record.get("ROA")),
        "return_on_equity_percent": to_decimal(record.get("ROE")),
        "equity_to_assets_percent": to_decimal(record.get("EQV")),
        "noncurrent_loan_rate_percent": to_decimal(record.get("NCLNLSR")),
        "nonperforming_assets_rate_percent": to_decimal(record.get("NPERFV")),
        "net_interest_margin_percent": to_decimal(record.get("NIMY")),

        "employee_count": to_integer(record.get("NUMEMP")),
        "domestic_office_count": to_integer(record.get("OFFDOM")),
        "api_record_id": record.get("ID"),
    }

    # For each YTD field store reported year-to-date figure and leave quarterly figure None for get_quarterly() to fill.
    for ytd_column, descriptive_name in YTD_FIELDS.items():
        row[f"{descriptive_name}_ytd_thousands"] = to_integer(record.get(ytd_column))
        row[f"{descriptive_name}_quarterly_thousands"] = None

    return row

def get_quarterly(rows: list):
    """Per (CERT, year): Q1 quarterly = YTD1; Q2..Q4 quarterly = YTD(q) - YTD(q-1). If prior quarter's YTD is missing
    quarterly stays None."""

    # Step 1 of 4: group rows by (bank, year)
    cert_year_tuple_rows: dict = defaultdict(list)  # missing key still creates dict with empty list value instead of error
    for row in rows:
        cert_year_tuple_rows[(row["fdic_certificate_number"], row["report_year"])].append(row)

    # Step 2 of 4: walk each group in quarter order
    for list_group in cert_year_tuple_rows.values():
        list_group.sort(key=lambda r: r["report_quarter"])

    # Step 2b of 4: index this group's rows by quarter number so prior quarter can be looked up by key rather than by 
    # list position. Guards against skipped quarter.
        rows_by_quarter = {row["report_quarter"]: row for row in list_group}

    # Step 3 of 4: for each row, walk the six YTD fields
        for row in list_group:
            prior_quarter_row = rows_by_quarter.get(row["report_quarter"] - 1)

            for descriptive_name in YTD_FIELDS.values():
                ytd_column = f"{descriptive_name}_ytd_thousands"
                quarterly_column = f"{descriptive_name}_quarterly_thousands"
                current_ytd = row[ytd_column]

    # Step 4 of 4: apply four cases
                if current_ytd is None:
                    row[quarterly_column] = None
                elif row["report_quarter"] == 1:
                    row[quarterly_column] = current_ytd  # Q1 YTD is the quarter itself
                elif prior_quarter_row is not None and prior_quarter_row[ytd_column] is not None:
                    row[quarterly_column] = current_ytd - prior_quarter_row[ytd_column]
                else:
                    row[quarterly_column] = None  #if prior quarter absent quarterly undefined as None
    return rows

def main():
    with open(SOURCE_FILE, newline="") as f:
        reader = csv.DictReader(f) #DictReader = iterator of dicts keyed by the CSV header row returning every field as string

        # each dict has all columns from clean.financials with '_ytd_thousands' filled and '_quarterly_thousands' = None.
        rows: list[dict] = [clean_csv_row(record) for record in reader]

    rows = get_quarterly(rows) #fills in quarterly since can see prior quarter whereas clean_csv_row(record) cannot

    #open 2 context managers in sequence:
        #get_connection() returns psycopg2 connection object which is pipe from Python to Postgres
        #db_connect.cursor() returns a cursor object from that connection which is the worker on pipe to Postgres
    with get_connection() as db_connect, db_connect.cursor() as cursor_object:
        cursor_object.execute(CREATE_TABLE_SQL)
        cursor_object.execute("TRUNCATE clean.financials;")
        cursor_object.executemany(INSERT_SQL, rows)
        db_connect.commit()

    print(f"clean.financials loaded: {len(rows)} rows")

if __name__ == "__main__":
    main()