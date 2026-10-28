# Crosswalk Method

The Consumer Financial Protection Bureau's (CFPB) complaint file identifies companies by name only. There is no CERT. The Federal Deposit Insurance Corporation (FDIC) identifies banks by certificate number. Matching the two is a name problem, and this document describes how it was solved and what the solution leaves out.

## Table of Contents

1. [Result](#1-result)
2. [What the unmatched remainder is made of](#2-what-the-unmatched-remainder-is-made-of)
3. [Method](#3-method)
   - [3.1 Normalize both sides identically](#31-normalize-both-sides-identically)
   - [3.2 Index every FDIC charter and holding company](#32-index-every-fdic-charter-and-holding-company)
   - [3.3 Exact match](#33-exact-match)
   - [3.4 Suffix-stripped match](#34-suffix-stripped-match)
   - [3.5 Manual overrides](#35-manual-overrides)
   - [3.6 Categorize the remainder](#36-categorize-the-remainder)
4. [What the crosswalk cannot do](#4-what-the-crosswalk-cannot-do)
   - [4.1 Large complaint targets are not banks](#41-large-complaint-targets-are-not-banks)
   - [4.2 Crosswalk coverage is not complaint resolution](#42-crosswalk-coverage-is-not-complaint-resolution)
   - [4.3 The matched share is stable but not fixed](#43-the-matched-share-is-stable-but-not-fixed)
5. [Reproducing](#5-reproducing)

---

## 1. Result

61.65% of complaints (664,397 of 1,077,624) are attributed to an FDIC-insured charter. The remaining 38.35% are complaints against companies that are not FDIC-insured banks - credit bureaus, mortgage servicers, fintechs, credit unions, and others.

| Match method      | Companies | Complaints | Share  |
|-------------------|----------:|-----------:|-------:|
| exact             |       150 |    481,867 | 44.72% |
| manual_override   |        13 |    176,718 | 16.40% |
| suffix_stripped   |         4 |      5,812 |  0.54% |
| **matched**       |   **167** |**664,397** |**61.65%**|
| unmatched         |     3,947 |    413,227 | 38.35% |

Queries: `sql/03_directed_analysis/02_crosswalk.sql`.

## 2. What the unmatched remainder is made of

| Company category       | Companies | Complaints | Share of unmatched |
|------------------------|----------:|-----------:|-------------------:|
| unknown                |     2,938 |    137,385 |             33.25% |
| mortgage_servicer      |       559 |     83,645 |             20.24% |
| credit_bureau          |         3 |     60,747 |             14.70% |
| fintech_or_payments    |        18 |     49,710 |             12.03% |
| credit_union           |        24 |     39,094 |              9.46% |
| auto_finance           |        30 |     23,065 |              5.58% |
| other_lender           |       340 |     15,802 |              3.82% |
| bank_named_unmatched   |        35 |      3,779 |              0.91% |

Three categories - mortgage servicers, credit bureaus and fintechs - account for roughly 47% of the unmatched complaints. These are not banks, and the CFPB database is not the right lens for comparing their behaviour against banks. The single largest category, `unknown`, holds 2,938 companies with 33% of the unmatched complaints; these are mostly small companies with names that do not resolve to a bank and do not match any category keyword.

`bank_named_unmatched` (35 companies, 3,779 complaints) are companies whose names contain `BANK` or `SAVINGS` but that did not match an FDIC charter. Most are credit unions under an unusual name, or non-US banks, or small institutions that closed before the current FDIC directory was written.

## 3. Method

### 3.1 Normalize both sides identically

The CFPB and FDIC name conventions disagree on punctuation, abbreviation and corporate suffixes. Both sides are put through the same `normalize()` function before any comparison:

- Uppercase.
- Replace `&` with ` AND `.
- Expand common abbreviations: `CORP` → `CORPORATION`, `BCORP` → `BANCORP`, `FINL` → `FINANCIAL`, `NATL` → `NATIONAL`, `ASSN` → `ASSOCIATION`, `CO` → `COMPANY`, `FED` → `FEDERAL`.
- Collapse `N.A.`, `N. A.` and `N A` to a single `NA` token.
- Strip all remaining punctuation.
- Collapse whitespace.

So `CITIBANK, N.A.` (CFPB) and `CITIBANK, NATIONAL ASSOCIATION` (FDIC) both become `CITIBANK NA` and `CITIBANK NATIONAL ASSOCIATION` respectively, and the suffix-stripped pass brings them together.

### 3.2 Index every FDIC charter and holding company

`load_fdic_index()` reads `fdic_institutions.json` and builds a dict keyed by the normalized form of every `NAME` and `NAMEHCR` value. A single dict holds both, with the first charter indexed under each key winning when there is a collision.

The tie-break for holding companies: when two or more charters share a `NAMEHCR`, the one with the largest total assets wins. This was a correction - the first version of the function used `setdefault`, which picked whichever charter appeared first in the JSON. That meant a `Citizens Financial Group` match could resolve to a $0.4bn subsidiary instead of the multi-hundred-billion primary. The fix:

```python
hcr_assets = {}
for record in records:
    ...
    hcr = data.get("NAMEHCR")
    if hcr:
        key = normalize(hcr)
        assets = data.get("ASSET") or 0
        if assets > hcr_assets.get(key, -1):
            index[key] = int(cert)
            hcr_assets[key] = assets
```

Charters that share a holding company but are not the largest still exist in `data_warehouse.institutions`. The Bank Scorecard aggregates to the parent so complaints and deposits are compared at the same organisational level.

### 3.3 Exact match

The normalized CFPB company name is looked up directly in the index. This resolves 150 companies carrying 44.72% of complaints - the largest single contributor to coverage.

### 3.4 Suffix-stripped match

For names that do not match exactly, corporate suffixes are stripped from the right iteratively: `INCORPORATED`, `INC`, `CORPORATION`, `CORP`, `COMPANY`, `CO`, `LIMITED`, `LTD`, `LLC`, `NATIONAL ASSOCIATION`, `N A`, `NA`, `FSB`, `SSB`, `SB`, `BANCORPORATION`, `BANCSHARES`, `HOLDINGS`, `HOLDING`, `GROUP`, `FINANCIAL`, `FINANCIALS`, `THE`, `AND`.

A guard prevents an empty string from being looked up: `strip_suffixes` returns an empty key for names like `BANCORP HOLDINGS INC` and the empty key would match anything else that also strips to empty.

This pass resolves 4 companies carrying 0.54% of complaints. It is deliberately conservative - the more aggressive the stripping, the more collisions it creates.

### 3.5 Manual overrides

Thirteen CFPB company names that did not match automatically were added to a manual override table. Each entry maps a CFPB name to an FDIC `NAME` or `NAMEHCR`, not to a CERT, so the mapping survives FDIC renumbering.

The overrides fall into two groups.

**Parent holding companies whose CFPB name does not share a token with any FDIC charter.** Example: `CITIBANK, N.A.` (CFPB) resolves to `CITIGROUP INC` (FDIC holding company), because the CFPB uses the operating subsidiary name while the FDIC's matching index keys by the parent.

| CFPB name                                  | FDIC name                              |
|--------------------------------------------|----------------------------------------|
| CITIBANK, N.A.                             | CITIGROUP INC                          |
| PNC Bank N.A.                              | PNC FINL SERVICES GROUP INC            |
| AMERICAN EXPRESS COMPANY                   | AMERICAN EXPRESS CO                    |
| Comerica                                   | COMERICA INC                           |
| SANTANDER HOLDINGS USA, INC.               | BANCO SANTANDER SA                     |
| M&T BANK CORPORATION                       | M&T BANK CORP                          |
| FIFTH THIRD FINANCIAL CORPORATION          | FIFTH THIRD BCORP                      |
| TD BANK US HOLDING COMPANY                 | TORONTO-DOMINION BANK THE              |
| Bread Financial Holdings, Inc.             | COMENITY BANK                          |
| UNITED SERVICES AUTOMOBILE ASSOCIATION     | USAA FEDERAL SAVINGS BANK              |
| HSBC NORTH AMERICA HOLDINGS INC.           | HSBC BANK USA NATIONAL ASSOCIATION     |
| Flagstar Bank, N.A.                        | FLAGSTAR BANK NATIONAL ASSOCIATION     |
| BBVA FINANCIAL CORPORATION                 | PNC FINL SERVICES GROUP INC            |

The last entry is deliberate: BBVA USA merged into PNC in 2021, so complaints against BBVA are attributed to PNC as the surviving parent. This is a historical attribution, not a name match.

### 3.6 Categorize the remainder

Names that did not match a charter are categorized by keyword. The categories and their meanings:

- `credit_bureau` - Experian, TransUnion, Equifax.
- `credit_union` - names containing `CREDIT UNION` or `FEDERAL CREDIT`.
- `mortgage_servicer` - names containing `MORTGAGE`, `SERVICING`, or specific known servicers (`SHELLPOINT`, `OCWEN`, `MR COOPER`, `CARRINGTON`, `PENNYMAC`, `LOANCARE`, `FREEDOM MORTGAGE`, `ROCKET MORTGAGE`, `SELECT PORTFOLIO`, `PHH MORTGAGE`, `CALIBER HOME`).
- `auto_finance` - Hyundai Capital, Toyota Motor, GM Financial, Ford Motor, Santander Consumer, Westlake, Credit Acceptance, Ally Financial.
- `fintech_or_payments` - Block, PayPal, Chime, SoFi, Robinhood, Stripe, Plaid, Affirm, Upgrade, Venmo, TransferWise, Netspend, Square, Green Dot, Meta Platforms, Google.
- `other_lender` - names containing `LENDING`, `FINANCE COMPANY`, `LOAN`, `PAYDAY`, `CASH ADVANCE`, `CONSUMER USA`, `OPORTUN`.
- `bank_named_unmatched` - names containing `BANK`, `SAVINGS`, `BANCORP`, `BANCSHARES`, `FEDERAL SAVINGS` that did not match a charter.
- `unknown` - anything else.

The order matters: the first matching category wins. A company named `CITIZENS BANK MORTGAGE` would be categorized as `mortgage_servicer` before ever reaching `bank_named_unmatched`.

## 4. What the crosswalk cannot do

### 4.1 Large complaint targets are not banks

Three of the top five unmatched complaint targets are not FDIC-insured institutions:

- **Equifax, TransUnion, Experian** (60,747 complaints combined). Credit bureaus, regulated by the FTC and state attorneys general, not the FDIC.
- **Chime, Block, PayPal, Affirm** (49,710 combined). Fintechs, most of which partner with a bank but are not themselves banks.
- **Navy Federal, Pentagon Federal** (part of 39,094 combined). Credit unions insured by the NCUA, not the FDIC.

Any claim that compares banks on complaints must state that these companies are excluded from the "bank" side. The 38.35% unmatched share is not a data defect - it is a statement about what the CFPB database contains.

### 4.2 Crosswalk coverage is not complaint resolution

A matched complaint is one whose company resolved to an FDIC charter. It is not a claim that the complaint was about an FDIC-insured activity. A CFPB complaint against `Citibank, N.A.` might be about an FDIC-insured deposit or about an uninsured investment product; the file does not distinguish them.

### 4.3 The matched share is stable but not fixed

The crosswalk runs on every pipeline execution. If the CFPB adds new company names, or the FDIC changes the institutions file, the matched share changes. The respective Power BI Bank Scorecard and Complaints page surface the current matched share so the reader can see it alongside the number it qualifies.

## 5. Reproducing

```bash
python src_retired_bc_no_pandas/05_build_crosswalk.py
```

The script reads `cfpb_complaints.csv` and `fdic_institutions.json`, writes `clean.company_crosswalk`, and reports the matched count at the end. The `data_quality_summary` table records the matched/unmatched company counts and the complaint coverage under `crosswalk_matched`, `crosswalk_unmatched` and `crosswalk_complaint_coverage`.