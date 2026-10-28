-- One row per FDIC certificate.
-- "bank" axis of report carrying holding company name as a column so report can aggregate to parent without separate
-- dimension.
-- Report visual saying "bank" uses charter (fdic_certificate_number) whereas one saying "parent" uses holding_company_name.


BEGIN;

DROP TABLE IF EXISTS data_mart.dim_bank CASCADE;
CREATE TABLE data_mart.dim_bank (
    fdic_certificate_number INTEGER PRIMARY KEY REFERENCES data_warehouse.institutions (fdic_certificate_number),
    institution_name        TEXT NOT NULL,
    holding_company_name    TEXT,
    charter_class_code      TEXT,
    headquarters_state_code CHAR(2),
    is_active               BOOLEAN NOT NULL,
    established_date        DATE,
    end_date                DATE
);

INSERT INTO data_mart.dim_bank
SELECT
    i.fdic_certificate_number,
    i.institution_name,
    h.holding_company_name,
    i.charter_class_code,
    i.headquarters_state_code,
    i.is_active,
    i.established_date,
    i.end_date
FROM data_warehouse.institutions i
LEFT JOIN data_warehouse.holding_company h ON i.holding_company_id = h.holding_company_id;

COMMIT;