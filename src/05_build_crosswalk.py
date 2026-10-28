"""Build clean.company_crosswalk using pandas merges."""
import pandas as pd
import numpy as np
import json
import re
from postgres_connection import get_connection
from psycopg2.extras import execute_values
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "capstone_data"
COMPLAINTS_FILE = DATA_DIR / "cfpb_complaints.csv"
INSTITUTIONS_FILE = DATA_DIR / "fdic_institutions.json"

# Suffixes stripped in Step 3 'Match again with corporate suffixes stripped from both sides'.
CORPORATE_SUFFIXES = ["INCORPORATED", "INC", "CORPORATION", "CORP", "COMPANY", "CO", "LIMITED", "LTD", "LLC",
                      "NATIONAL ASSOCIATION", "N A", "NA", "FSB", "SSB", "SB", "BANCORPORATION", "BANCSHARES",
                      "HOLDINGS", "HOLDING", "GROUP", "FINANCIAL", "FINANCIALS", "THE", "AND",]

# Expand common FDIC/CFPB abbreviations so both sides normalize same way.
ABBREVIATION_EXPANSIONS = {
    "CORP":     "CORPORATION",
    "CO":       "COMPANY",
    "BCORP":    "BANCORP",
    "FINL":     "FINANCIAL",
    "SVC":      "SERVICES",
    "SERV":     "SERVICES",
    "NATL":     "NATIONAL",
    "ASSOC":    "ASSOCIATION",
    "ASSN":     "ASSOCIATION",
    "FED":      "FEDERAL",
}

# Manual overrides applied in Step 4 'Read the unmatched list sorted by complaint volume'.
# Key = CFPB company name exactly as stored in clean.complaints.
# Value = FDIC institution_name or holding_company_name exactly as stored in clean.institutions.
# Permits multiple CFPB names pointing to same FDIC charter
MANUAL_OVERRIDES = {
    "CITIBANK, N.A.":                         "CITIGROUP INC",
    "PNC Bank N.A.":                          "PNC FINL SERVICES GROUP INC",
    "BBVA FINANCIAL CORPORATION":             "PNC FINL SERVICES GROUP INC",   # merged into PNC
    "AMERICAN EXPRESS COMPANY":               "AMERICAN EXPRESS CO",
    "Comerica":                               "COMERICA INC",
    "SANTANDER HOLDINGS USA, INC.":           "BANCO SANTANDER SA",
    "M&T BANK CORPORATION":                   "M&T BANK CORP",
    "FIFTH THIRD FINANCIAL CORPORATION":      "FIFTH THIRD BCORP",
    "TD BANK US HOLDING COMPANY":             "TORONTO-DOMINION BANK THE",
    "Bread Financial Holdings, Inc.":         "COMENITY BANK",
    "UNITED SERVICES AUTOMOBILE ASSOCIATION": "USAA FEDERAL SAVINGS BANK",
    "HSBC NORTH AMERICA HOLDINGS INC.":       "HSBC BANK USA NATIONAL ASSOCIATION",
    "Flagstar Bank, N.A.":                    "FLAGSTAR BANK NATIONAL ASSOCIATION",
}

# Category keywords for companies that do not match an FDIC charter. Matched charters are categorized as "bank".
CATEGORY_KEYWORDS = [
    ("credit_bureau",       ["EXPERIAN", "TRANSUNION", "EQUIFAX"]),
    ("credit_union",        ["CREDIT UNION", "FEDERAL CREDIT"]),
    ("mortgage_servicer",   ["MORTGAGE", "SHELLPOINT", "OCWEN", "MR COOPER", "NATIONSTAR", "CARRINGTON", "PENNYMAC",
                             "SERVICING", "SPECIALIZED LOAN", "LOANCARE", "FREEDOM MORTGAGE", "ROCKET MORTGAGE",
                             "SELECT PORTFOLIO", "PHH MORTGAGE", "CALIBER HOME"]),
    ("auto_finance",        ["HYUNDAI CAPITAL", "TOYOTA MOTOR", "GM FINANCIAL", "FORD MOTOR", "SANTANDER CONSUMER",
                             "AUTO FINANCE", "WESTLAKE", "CREDIT ACCEPTANCE", "ALLY FINANCIAL"]),
    ("fintech_or_payments", ["BLOCK", "PAYPAL", "CHIME", "SOFI", "ROBINHOOD", "STRIPE", "PLAID", "AFFIRM", "UPGRADE",
                             "VENMO", "TRANSFERWISE", "NETSPEND", "SQUARE", "GREEN DOT", "META PLATFORMS", "GOOGLE"]),
    ("other_lender",        ["LENDING", "FINANCE COMPANY", "ONEMAIN", "LOAN", "PAYDAY", "CASH ADVANCE", "CONSUMER USA",
                             "OPORTUN"]),
    ("bank_named_unmatched",["BANK", "SAVINGS", "BANCORP", "BANCSHARES", "FEDERAL SAVINGS"]),
]

CREATE_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS clean;
CREATE TABLE IF NOT EXISTS clean.company_crosswalk (
    company_name TEXT PRIMARY KEY,
    company_name_normalized TEXT NOT NULL,
    matched_fdic_certificate_number INTEGER,
    match_method TEXT NOT NULL,
    company_category TEXT NOT NULL
);
"""


def normalize(name):
    if pd.isna(name): return ""
    uppercased = str(name).upper().replace("&", " AND ")
    uppercased = re.sub(r"\bN\s*\.?\s*A\b", " NA ", uppercased)
    cleaned = re.sub(r"[^A-Z0-9 ]", " ", uppercased)
    words = [ABBREVIATION_EXPANSIONS.get(w, w) for w in cleaned.split()]
    return " ".join(words)


def strip_suffixes(normalized_name):
    words = normalized_name.split()
    while words and words[-1] in CORPORATE_SUFFIXES: words.pop()
    return " ".join(words)


def categorize(company_name):
    upper = str(company_name).upper()
    for cat, keys in CATEGORY_KEYWORDS:
        #any() looks through for expression and returns True moment check is true
        if any(k in upper for k in keys): return cat
    return "unknown"


def load_fdic_index():
    with open(INSTITUTIONS_FILE) as f:
        records = json.load(f)
    index, tracking = {}, {}
    for record in records:
        data = record.get("data", {})
        cert = data.get("CERT")
        if cert is None: continue

        bank_name = data.get("NAME")
        if bank_name: index.setdefault(normalize(bank_name), int(cert))

        hcr = data.get("NAMEHCR")
        if hcr:
            key = normalize(hcr)
            assets = data.get("ASSET") or 0
            if assets > tracking.get(key, -1):
                index[key] = int(cert)
                tracking[key] = assets
    return index


def main():
    # 1 Get distinct companies from complaints
    df_complaints = pd.read_csv(COMPLAINTS_FILE, usecols=['Company'])
    df = pd.DataFrame({'company_name': df_complaints['Company'].str.lower().dropna().unique()})
    df['company_name_normalized'] = df['company_name'].apply(normalize)

    # 2 Build FDIC Index
    fdic_index = load_fdic_index()

    # 3 Matching Logic
    certs, methods, categories = [], [], []

    # iterrows() is generator that loops through DataFrame row by row yielding tuple for each row containing index
    # (row label) and row data as a Pandas Series
    for _, row in df.iterrows():
        name = row['company_name']
        norm = row['company_name_normalized']

        cert, method, cat = None, "unmatched", "unknown"

        # Manual Override
        for cfpb_name, fdic_name in MANUAL_OVERRIDES.items():
            if normalize(cfpb_name) == norm:
                cert = fdic_index.get(normalize(fdic_name))
                if cert: method, cat = "manual_override", "bank"; break

        # Exact Match
        if not cert:
            cert = fdic_index.get(norm)
            if cert: method, cat = "exact", "bank"

        # Suffix Stripped
        if not cert:
            stripped = strip_suffixes(norm)
            if stripped:
                cert = fdic_index.get(stripped)
                if cert: method, cat = "suffix_stripped", "bank"

        # Categorize Unmatched
        if not cert: cat = categorize(name)

        certs.append(cert)
        methods.append(method)
        categories.append(cat)

    df['matched_fdic_certificate_number'] = certs
    df['match_method'] = methods
    df['company_category'] = categories

    cols = ["company_name", "company_name_normalized", "matched_fdic_certificate_number", "match_method",
            "company_category"]

    # Bulk Insert
    # Finds every NaN in DataFrame and swaps for Python's None object which psycopg2 correctly translates to SQL NULL
    # execute_values requires each row to be a tuple
    rows = [tuple(x) for x in df.replace({np.nan: None}).to_numpy()]

    with get_connection() as db_connect, db_connect.cursor() as cursor_object:
        cursor_object.execute(CREATE_TABLE_SQL)
        cursor_object.execute("TRUNCATE clean.company_crosswalk;")
        execute_values(cursor_object, f"INSERT INTO clean.company_crosswalk ({', '.join(cols)}) VALUES %s", rows)
        db_connect.commit()

    print(
        f"clean.company_crosswalk loaded: {len(df)} company names ({df['matched_fdic_certificate_number'].notna().sum()} matched)")


if __name__ == "__main__":
    main()