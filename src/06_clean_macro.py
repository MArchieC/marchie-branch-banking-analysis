"""Load four FRED series into clean.macro_quarterly using pandas merge_asof."""
import pandas as pd
import numpy as np
from postgres_connection import get_connection
from psycopg2.extras import execute_values
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "capstone_data"

FRED_FILES = {
    "federal_funds_rate_percent": RAW_DIR / "fred_FEDFUNDS.csv",
    "unemployment_rate_percent": RAW_DIR / "fred_UNRATE.csv",
    "thirty_year_mortgage_rate_percent": RAW_DIR / "fred_MORTGAGE30US.csv",
    "ten_year_treasury_yield_percent": RAW_DIR / "fred_DGS10.csv",
}

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS clean;
CREATE TABLE IF NOT EXISTS clean.macro_quarterly (
    quarter_end_date DATE PRIMARY KEY,
    federal_funds_rate_percent NUMERIC,
    unemployment_rate_percent NUMERIC,
    thirty_year_mortgage_rate_percent NUMERIC,
    ten_year_treasury_yield_percent NUMERIC
);
"""


def main():
    # 1 Generate Quarter Grid (2006 Q1 to 2026 Q2)
    quarters = pd.date_range(start='2006-03-31', end='2026-06-30', freq='QE')
    df = pd.DataFrame({'quarter_end_date': quarters}).sort_values('quarter_end_date')

    # 2 Load and Merge Series
    for series_name, file_path in FRED_FILES.items():
        df_fred = pd.read_csv(file_path)
        df_fred['observation_date'] = pd.to_datetime(df_fred['observation_date'])
        df_fred = df_fred.sort_values('observation_date')

        val_col = df_fred.columns[1]
        df_fred = df_fred.rename(columns={val_col: series_name})

        # merge_asof finds the last observation on or before the quarter_end_date
        df = pd.merge_asof(
            df,  # left table = quarterly grid
            df_fred[['observation_date', series_name]],  # right table = FRED dates + values
            left_on='quarter_end_date',  # look at this date in left table
            right_on='observation_date',  # look at this date in right table
            direction='backward'  # match right date that is <= left date
        ).drop(columns=['observation_date'])

    cols = ["quarter_end_date", "federal_funds_rate_percent", "unemployment_rate_percent",
            "thirty_year_mortgage_rate_percent", "ten_year_treasury_yield_percent"]

    # Bulk Insert
    # Finds every NaN in DataFrame and swaps for Python's None object which psycopg2 correctly translates to SQL NULL
    # execute_values requires each row to be a tuple
    rows = [tuple(x) for x in df.replace({np.nan: None}).to_numpy()]

    with get_connection() as db_connect, db_connect.cursor() as cursor_object:
        cursor_object.execute(CREATE_TABLE_SQL)
        cursor_object.execute("TRUNCATE clean.macro_quarterly;")
        execute_values(cursor_object, f"INSERT INTO clean.macro_quarterly ({', '.join(cols)}) VALUES %s", rows)
        db_connect.commit()

    print(f"clean.macro_quarterly loaded: {len(df)} quarters")


if __name__ == "__main__":
    main()