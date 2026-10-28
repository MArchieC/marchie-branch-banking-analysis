"""Refresh data_quality_summary: one place for everything found and done."""

from postgres_connection import get_connection

DDL_SQL = """
DROP TABLE IF EXISTS data_quality_summary CASCADE;

CREATE TABLE data_quality_summary (
    table_name                   TEXT NOT NULL,
    column_name                  TEXT NOT NULL,   -- real column, or '(statement)'
    rule_name                    TEXT NOT NULL,   -- 'column profile' for profile rows
    rule_description             TEXT,            -- NULL for profile rows
    row_count                    BIGINT,          -- profile rows only
    null_count                   BIGINT,          -- profile rows only
    distinct_count               BIGINT,          -- profile rows only
    rows_failing                 BIGINT NOT NULL DEFAULT 0,
    action_taken                 TEXT NOT NULL DEFAULT 'kept',
    checked_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (table_name, column_name, rule_name)
);

CREATE OR REPLACE FUNCTION refresh_data_quality_summary() RETURNS void
LANGUAGE plpgsql AS $func$

DECLARE
    r          RECORD;
    n_total    BIGINT;
    n_null     BIGINT;
    n_distinct BIGINT;

BEGIN
    TRUNCATE data_quality_summary;

    -- START: Profile every column of every clean.* table.
    FOR r IN
        SELECT table_schema, table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'clean' AND table_name IN ('institutions', 'financials', 'failures', 'complaints', 
                                        'company_crosswalk', 'macro_quarterly')
        ORDER BY table_name, ordinal_position
    LOOP
        -- %I is PostgreSQL's format() placeholder for an identifier
        EXECUTE format('SELECT COUNT(*), COUNT(*) FILTER (WHERE %I IS NULL), COUNT(DISTINCT %I) FROM %I.%I',
                        r.column_name, r.column_name, r.table_schema, r.table_name) INTO n_total, n_null, n_distinct;
        INSERT INTO data_quality_summary
            (table_name, column_name, rule_name, rule_description, row_count, null_count, distinct_count, rows_failing, 
            action_taken)
        VALUES (r.table_name, r.column_name, 'column profile', NULL, n_total, n_null, n_distinct, 0, 'kept');
    END LOOP;


    -- START: Rule rows, one per cleaning decision.
    INSERT INTO data_quality_summary (table_name, column_name, rule_name, rule_description, rows_failing, action_taken)
    VALUES

    -- ============ institutions ============
    ('institutions', 'end_date', 'placeholder_date_to_null',
     'ENDEFYMD = 12/31/9999 is the FDIC placeholder for "no end date".',
     (SELECT COUNT(*) FROM clean.institutions WHERE end_date IS NULL), 'nulled'),

    ('institutions', 'federal_reserve_rssd_id', 'zero_sentinel_to_null',
     'FED_RSSD = 0 is the FDIC sentinel for "no RSSD identifier".',
     (SELECT COUNT(*) FROM clean.institutions WHERE federal_reserve_rssd_id IS NULL),
     'nulled'),

    ('institutions', 'website_address', 'blank_to_null', 'Blank or whitespace-only WEBADDR converted to NULL.',
     (SELECT COUNT(*) FROM clean.institutions WHERE website_address IS NULL),
     'nulled'),

    ('institutions', 'holding_company_name', 'blank_to_null', 'Blank NAMEHCR converted to NULL.',
     (SELECT COUNT(*) FROM clean.institutions WHERE holding_company_name IS NULL),
     'nulled'),

    ('institutions', 'total_assets_thousands', 'blank_to_null',
     'Absent ASSET converted to NULL. Present for active banks only.',
     (SELECT COUNT(*) FROM clean.institutions WHERE total_assets_thousands IS NULL),
     'nulled'),

    ('institutions', 'total_deposits_thousands', 'blank_to_null',
     'Absent DEP converted to NULL. Present for active banks only.',
     (SELECT COUNT(*) FROM clean.institutions WHERE total_deposits_thousands IS NULL),
     'nulled'),

    ('institutions', '(statement)', 'derive_is_active', 'ACTIVE = 1 mapped to boolean true, all other values to false.',
     (SELECT COUNT(*) FROM clean.institutions WHERE is_active IS NULL),
     'derived'),

    ('institutions', 'charter_class_code', 'blank_to_null',
     'Blank BKCLASS converted to NULL.',
     (SELECT COUNT(*) FROM clean.institutions WHERE charter_class_code IS NULL),
     'nulled'),
    
    ('institutions', 'charter_class_code', 'data_vs_published_definitions',
     'Appendix A lists 10 codes. Data adds MI (14 failure rows, 1938-1983) and omits CU (no credit unions in FDIC data).
      Cert 15656 has blank BKCLASS nulled in cleaner.',
     (SELECT COUNT(*) FROM clean.institutions WHERE charter_class_code IS NULL),
     'documented'),
 
    -- ============ financials ============
    ('financials', '(statement)', 'derive_year_quarter', 'report_year and report_quarter derived from report_date.',
     (SELECT COUNT(*) FROM clean.financials
      WHERE report_year IS NULL OR report_quarter IS NULL),
     'derived'),

    ('financials', 'net_income_quarterly_thousands', 'prior_quarter_missing',
     'Quarterly value undefined when prior quarter YTD is missing.',
     (SELECT COUNT(*) FROM clean.financials
      WHERE report_quarter > 1
        AND net_income_ytd_thousands IS NOT NULL
        AND net_income_quarterly_thousands IS NULL),
     'nulled'),

    ('financials', 'interest_income_quarterly_thousands', 'prior_quarter_missing',
     'Quarterly value undefined when prior quarter YTD is missing.',
     (SELECT COUNT(*) FROM clean.financials
      WHERE report_quarter > 1
        AND interest_income_ytd_thousands IS NOT NULL
        AND interest_income_quarterly_thousands IS NULL),
     'nulled'),

    ('financials', 'interest_expense_quarterly_thousands', 'prior_quarter_missing',
     'Quarterly value undefined when prior quarter YTD is missing.',
     (SELECT COUNT(*) FROM clean.financials
      WHERE report_quarter > 1
        AND interest_expense_ytd_thousands IS NOT NULL
        AND interest_expense_quarterly_thousands IS NULL),
     'nulled'),

    ('financials', 'noninterest_income_quarterly_thousands', 'prior_quarter_missing',
     'Quarterly value undefined when prior quarter YTD is missing.',
     (SELECT COUNT(*) FROM clean.financials
      WHERE report_quarter > 1
        AND noninterest_income_ytd_thousands IS NOT NULL
        AND noninterest_income_quarterly_thousands IS NULL),
     'nulled'),

    ('financials', 'noninterest_expense_quarterly_thousands', 'prior_quarter_missing',
     'Quarterly value undefined when prior quarter YTD is missing.',
     (SELECT COUNT(*) FROM clean.financials
      WHERE report_quarter > 1
        AND noninterest_expense_ytd_thousands IS NOT NULL
        AND noninterest_expense_quarterly_thousands IS NULL),
     'nulled'),

    ('financials', 'provision_for_credit_losses_quarterly_thousands', 'prior_quarter_missing',
     'Quarterly value undefined when prior quarter YTD is missing.',
     (SELECT COUNT(*) FROM clean.financials
      WHERE report_quarter > 1
        AND provision_for_credit_losses_ytd_thousands IS NOT NULL
        AND provision_for_credit_losses_quarterly_thousands IS NULL),
     'nulled'),

    ('financials', 'total_assets_thousands', 'blank_to_null', 'Blank ASSET converted to NULL.',
     (SELECT COUNT(*) FROM clean.financials WHERE total_assets_thousands IS NULL),
     'nulled'),

    ('financials', 'total_deposits_thousands', 'blank_to_null', 'Blank DEP converted to NULL.',
     (SELECT COUNT(*) FROM clean.financials WHERE total_deposits_thousands IS NULL),
     'nulled'),

    ('financials', 'total_equity_thousands', 'blank_to_null', 'Blank EQ converted to NULL.',
     (SELECT COUNT(*) FROM clean.financials WHERE total_equity_thousands IS NULL),
     'nulled'),

    -- ============ failures ============
    ('failures', 'fdic_certificate_number', 'blank_to_null',
     'Blank CERT converted to NULL. Some rows carry no certificate.',
     (SELECT COUNT(*) FROM clean.failures WHERE fdic_certificate_number IS NULL),
     'nulled'),

    ('failures', 'total_assets_at_failure_thousands', 'text_to_integer',
     'QBFASSET parsed to integer, blank to NULL.',
     (SELECT COUNT(*) FROM clean.failures WHERE total_assets_at_failure_thousands IS NULL),
     'nulled'),

    ('failures', 'total_deposits_at_failure_thousands', 'text_to_integer', 'QBFDEP parsed to integer, blank to NULL.',
     (SELECT COUNT(*) FROM clean.failures WHERE total_deposits_at_failure_thousands IS NULL),
     'nulled'),

    ('failures', 'failure_date', 'two_date_formats',
     'FAILDATE came in both M/D/YYYY and YYYY-MM-DD. Both parsed to date.', 0, 'parsed'),
     
    ('failures', 'headquarters_state_code', 'invalid_state_code_to_null',
     'Blank or non-US-state code converted to NULL.',
     (SELECT COUNT(*) FROM clean.failures WHERE headquarters_state_code IS NULL),
     'nulled'),
    
    ('failures', 'acquiring_state_code', 'invalid_state_code_to_null',
     'Blank, numeric sentinel, or non-US-state code converted to NULL.',
     (SELECT COUNT(*) FROM clean.failures WHERE acquiring_state_code IS NULL),
     'nulled'),

    -- ============ complaints ============
    ('complaints', 'harmonized_product', 'label_harmonization',
     'August 2023 CFPB relabel collapsed old and new product names.',
     (SELECT COUNT(*) FROM clean.complaints
      WHERE harmonized_product IS DISTINCT FROM product_reported),
     'harmonized'),

    ('complaints', 'is_timely_response', 'derive_boolean',
     'Timely response? "Yes" mapped to true, everything else to false.',
     0,
     'derived'),

    ('complaints', 'consumer_zip_code', 'masked_zip_preserved',
     'CFPB masks last two digits on small ZIPs, e.g. 304XX. Kept as-is.',
     (SELECT COUNT(*) FROM clean.complaints
      WHERE consumer_zip_code ~ '^[0-9]{3}XX$'),
     'kept'),

    ('complaints', 'consumer_state_code', 'invalid_state_code_to_null',
     'Blank or non-US-state code (e.g. region name) converted to NULL.',
     (SELECT COUNT(*) FROM clean.complaints WHERE consumer_state_code IS NULL),
     'nulled'),
     
    ('complaints', 'issue', 'blank_to_null',
     'Blank Issue converted to NULL.',
     (SELECT COUNT(*) FROM clean.complaints WHERE issue IS NULL),
     'nulled'),
     
    ('complaints', 'sub_issue', 'blank_to_null', 'Blank Sub-issue converted to NULL.',
     (SELECT COUNT(*) FROM clean.complaints WHERE sub_issue IS NULL),
     'nulled'),

    ('complaints', 'sub_product', 'blank_to_null', 'Blank Sub-product converted to NULL.',
     (SELECT COUNT(*) FROM clean.complaints WHERE sub_product IS NULL),
     'nulled'),

    ('complaints', 'company_public_response', 'blank_to_null', 'Blank Company public response converted to NULL.',
     (SELECT COUNT(*) FROM clean.complaints WHERE company_public_response IS NULL),
     'nulled'),

    ('complaints', 'consumer_tags', 'blank_to_null', 'Blank Tags converted to NULL.',
     (SELECT COUNT(*) FROM clean.complaints WHERE consumer_tags IS NULL),
     'nulled'),

    ('complaints', 'consumer_zip_code', 'blank_to_null', 'Blank ZIP code converted to NULL.',
     (SELECT COUNT(*) FROM clean.complaints WHERE consumer_zip_code IS NULL),
     'nulled'),
     
     ('complaints', 'company_name', 'case_fold_to_lower', 'Lowercase so case-only variants collapse. PostgreSQL accepted
      "ONEMAIN..." and "OneMain..." as distinct; Power BI''s case-insensitive collation did not.', 0, 'normalized'),

    -- ============ company_crosswalk ============
    ('company_crosswalk', 'match_method', 'crosswalk_matched',
     'Company names with an FDIC charter match (not complaint count).',
     (SELECT COUNT(*) FROM clean.company_crosswalk
      WHERE match_method <> 'unmatched'),
     'kept'),

    ('company_crosswalk', 'match_method', 'crosswalk_unmatched',
     'Company names without an FDIC charter match (not complaint count).',
     (SELECT COUNT(*) FROM clean.company_crosswalk
      WHERE match_method = 'unmatched'),
     'categorized'),
     
     ('complaints', '(statement)', 'crosswalk_complaint_coverage', 
      'Complaints attributed to an FDIC charter via the crosswalk.',
     (SELECT COUNT(*) FROM clean.complaints c
      JOIN clean.company_crosswalk cw ON c.company_name = cw.company_name WHERE cw.match_method <> 'unmatched'),
      'reported'),

    -- ============ macro_quarterly ============
    ('macro_quarterly', '(statement)', 'fred_align_last_observation',
     'FRED monthly/weekly/daily series aligned to quarter-end by '
     'taking the last observation on or before the quarter-end date.',
     0,
     'aligned'),

    ('macro_quarterly', 'federal_funds_rate_percent', 'series_not_started',
     'NULL where the FRED series has no observation on or before quarter-end.',
     (SELECT COUNT(*) FROM clean.macro_quarterly
      WHERE federal_funds_rate_percent IS NULL),
     'nulled'),

    ('macro_quarterly', 'unemployment_rate_percent', 'series_not_started',
     'NULL where the FRED series has no observation on or before quarter-end.',
     (SELECT COUNT(*) FROM clean.macro_quarterly
      WHERE unemployment_rate_percent IS NULL),
     'nulled'),

    ('macro_quarterly', 'thirty_year_mortgage_rate_percent', 'series_not_started',
     'NULL where the FRED series has no observation on or before quarter-end.',
     (SELECT COUNT(*) FROM clean.macro_quarterly
      WHERE thirty_year_mortgage_rate_percent IS NULL),
     'nulled'),

    ('macro_quarterly', 'ten_year_treasury_yield_percent', 'series_not_started',
     'NULL where the FRED series has no observation on or before quarter-end.',
     (SELECT COUNT(*) FROM clean.macro_quarterly
      WHERE ten_year_treasury_yield_percent IS NULL),
     'nulled');

END;
$func$;
"""


def main():

    #open 2 context managers in sequence:
        #get_connection() returns psycopg2 connection object which is pipe from Python to Postgres
        #db_connect.cursor() returns a cursor object from that connection which is the worker on pipe to Postgres
    with get_connection() as db_connect, db_connect.cursor() as cursor_object:
        cursor_object.execute(DDL_SQL)
        cursor_object.execute("SELECT refresh_data_quality_summary();")
        db_connect.commit()
    print("data_quality_summary refreshed")


if __name__ == "__main__":
    main()