"""Build clean.company_crosswalk: mapping each CFPB company name to FDIC charter when possible."""

import csv
import json
import re
from postgres_connection import get_connection


from pathlib import Path
#pattern works from any working directory as path to data folder calculated relative to scripts real location
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
    company_name                      TEXT PRIMARY KEY,
    company_name_normalized           TEXT NOT NULL,
    matched_fdic_certificate_number   INTEGER,
    match_method                      TEXT NOT NULL,
    company_category                  TEXT NOT NULL
);
"""

# Column order used for INSERT. Kept as list so INSERT is built from same source of truth row builder uses.
COLUMNS = ["company_name", "company_name_normalized", "matched_fdic_certificate_number", "match_method", "company_category"]

#VALUES are named placeholders in form %(column_name)s for executemany()
INSERT_SQL = f"INSERT INTO clean.company_crosswalk ({', '.join(COLUMNS)}) VALUES ({', '.join('%(' + c + ')s' for c in COLUMNS)});"

def normalize(name):
    """Uppercase, & -> AND, expand abbreviations, drop punctuation, collapse whitespace."""
    if name is None:
        return ""
    
    uppercased = name.upper().replace("&", " AND ")
    #collapse N.A. / N. A. / N A to a single NA by function end
    uppercased = re.sub(r"\bN\s*\.?\s*A\b", " NA ", uppercased)
    
    cleaned = re.sub(r"[^A-Z0-9 ]", " ", uppercased) #keep letters, digits, spaces
    
    words = [ABBREVIATION_EXPANSIONS.get(w, w) for w in cleaned.split()] #avoid KeyError if key doesn't exist
    
    return " ".join(words)

def strip_suffixes(normalized_name):
    """Remove trailing corporate suffixes, applied iteratively from right."""
    list_of_words = normalized_name.split()
    while list_of_words != [] and list_of_words[-1] in CORPORATE_SUFFIXES:
        list_of_words.pop()
    return " ".join(list_of_words)

def load_fdic_index():
    """Return {normalized_name: certificate_number} for every FDIC charter name and holding company name. When multiple
    charters share a NAMEHCR largest by total assets wins."""
    with open(INSTITUTIONS_FILE) as f:
        records: list[dict] = json.load(f) #parse whole file into Python objects such that 'records' becomes list of dicts

    index = {}  #holds {normalized_name: certificate_number} only for largest by total assets
    tracking_dict = {}   #keeps track of highest asset amt seen so far

    for record in records:
        data = record["data"]
        cert = data.get("CERT")

        if cert is None:
            continue

        # Step 1 of 2: index bank name
        bank_name = data.get("NAME")
        if bank_name:
        #setdefault method returns key value if key exists in dict else inserts key with a specified default value and returns that value.
            index.setdefault(normalize(bank_name), int(cert))

        # Step 2 of 2: index holding company name having highest assets (necessary for PowerBI Bank Scorecard page)
        holding_company_name = data.get("NAMEHCR")
        if holding_company_name:
            key = normalize(holding_company_name)
            assets = data.get("ASSET") or 0
            if assets > tracking_dict.get(key, -1):
                index[key] = int(cert)  #always yields cert number of highest asset for given HCR
                tracking_dict[key] = assets  #tracking dict updates its max value to latest highest asset amt
    return index

def categorize(company_name):
    """Return category for a company that did not match an FDIC charter."""
    uppercased = company_name.upper()
    for category, keywords in CATEGORY_KEYWORDS:
        for keyword in keywords:
            if keyword in uppercased:
                return category
    return "unknown"

def match_cfpb_company(cfpb_company_name, fdic_index_argument):
    """Return (cert_or_None, match_method, category) for one CFPB company name."""
    normalized_cfpb_company_name_argument = normalize(cfpb_company_name)
    if normalized_cfpb_company_name_argument == "":
        return None, "unmatched", "unknown"

    # Step 4 first: manual override, keyed by CFPB name so multiple CFPB names can resolve to same FDIC charter. Runs
    # before automatic lookups because manual override is authoritative.
    for cfpb_name, fdic_name in MANUAL_OVERRIDES.items():
        if normalize(cfpb_name) == normalized_cfpb_company_name_argument:
            cert = fdic_index_argument.get(normalize(fdic_name))
            if cert is not None:
                return cert, "manual_override", "bank"

    # Step 2: exact match.
    cert = fdic_index_argument.get(normalized_cfpb_company_name_argument)
    if cert is not None:
        return cert, "exact", "bank"

    # Step 3: suffix-stripped match with the empty string guard.
    stripped = strip_suffixes(normalized_cfpb_company_name_argument)
    if stripped:
        cert = fdic_index_argument.get(stripped)
        if cert is not None:
            return cert, "suffix_stripped", "bank"

    # Step 5: categorize the remainder.
    return None, "unmatched", categorize(cfpb_company_name)

def main():

    #Yield distinct CFPB company names from complaints file.
    with open(COMPLAINTS_FILE, newline="") as f:
        reader = csv.DictReader(f) #DictReader = iterator of dicts keyed by the CSV header row returning every field as string

        #Collapsing case so values that differ only by case are treated as one company since PostgreSQL's case-sensitive
        #TEXT PK accepts 'ONEMAIN...' and 'OneMain...' as two keys whereas Power BI's case-insensitive collation does
        #not such that trying to create PowerBI relationship fails on duplicates. Canonical form = lowercase.
        #Using set comprehension to yield sorted list of every distinct Company value that is non-empty.
        company_names = sorted({record["Company"].lower() for record in reader if record.get("Company")})

    fdic_index = load_fdic_index()

    rows: list[dict] = []
    for company_name in company_names:
        normalized = normalize(company_name)
        cert, method, category = match_cfpb_company(company_name, fdic_index)
        rows.append({
            "company_name": company_name,
            "company_name_normalized": normalized,
            "matched_fdic_certificate_number": cert,
            "match_method": method,
            "company_category": category,
        })

    #open 2 context managers in sequence:
        #get_connection() returns psycopg2 connection object which is pipe from Python to Postgres
        #db_connect.cursor() returns a cursor object from that connection which is the worker on pipe to Postgres
    with get_connection() as db_connect, db_connect.cursor() as cursor_object:
        cursor_object.execute(CREATE_TABLE_SQL)
        cursor_object.execute("TRUNCATE clean.company_crosswalk;")
        cursor_object.executemany(INSERT_SQL, rows)
        db_connect.commit()

    matched_count = sum(1 for r in rows if r["matched_fdic_certificate_number"] is not None)
    print(f"clean.company_crosswalk loaded: {len(rows)} company names ({matched_count} matched)")

if __name__ == "__main__":
    main()