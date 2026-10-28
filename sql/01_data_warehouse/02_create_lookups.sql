-- Lookup tables = small tables holding repeated descriptive text.
-- Drop and recreate throughout so the script is safe to run twice.


BEGIN;

-- Charter class codes. Code list derived from codes actually present in clean.institutions and clean.failures, so lookup
-- matches the data instead of published Appendix A.
-- Descriptions come from small map; a code that appears in raw data but not in map gets a NULL description, which fails
-- NOT NULL constraint and forces an explicit decision.
-- Documented in documentation/schema_documentation.md: failures file uses one historic code (MI) that Appendix A does
-- not list.
DROP TABLE IF EXISTS data_warehouse.charter_class CASCADE;
CREATE TABLE data_warehouse.charter_class (
    charter_class_code TEXT    PRIMARY KEY,
    description        TEXT    NOT NULL CHECK (btrim(description) <> ''),
    is_insured         BOOLEAN NOT NULL DEFAULT TRUE
);

WITH code_descriptions (charter_class_code, description, is_insured) AS (
    VALUES
        ('N',  'National charter, Federal Reserve member, supervised by the OCC',        TRUE),
        ('NM', 'State charter, Federal Reserve non-member, supervised by the FDIC',      TRUE),
        ('SM', 'State charter, Federal Reserve member, supervised by the Federal Reserve', TRUE),
        ('SB', 'Federal savings bank',                                                   TRUE),
        ('SI', 'State stock savings institution',                                        TRUE),
        ('SL', 'State-chartered savings and loan association',                           TRUE),
        ('OI', 'Insured US branch of a foreign-chartered institution',                   TRUE),
        ('NC', 'Non-insured commercial bank',                                            FALSE),
        ('NS', 'Non-insured savings institution',                                        FALSE),
        ('CU', 'Credit union',                                                           TRUE),
        ('MI', 'State-chartered mutual savings bank, supervised by the FDIC. Retired.',  TRUE)
),
present_codes (charter_class_code) AS (
    SELECT DISTINCT charter_class_code FROM clean.institutions
    WHERE charter_class_code IS NOT NULL
    UNION
    SELECT DISTINCT charter_class_code FROM clean.failures
    WHERE charter_class_code IS NOT NULL
)
INSERT INTO data_warehouse.charter_class (charter_class_code, description, is_insured)
SELECT p.charter_class_code, d.description, d.is_insured
FROM present_codes p
LEFT JOIN code_descriptions d USING (charter_class_code);


-- Harmonized CFPB product labels (post-2023 relabel) populated from cleaned complaints file so list authoritative: no
-- product in the warehouse can be missing from this table because it was derived from same rows.
DROP TABLE IF EXISTS data_warehouse.product CASCADE;
CREATE TABLE data_warehouse.product (
    harmonized_product TEXT PRIMARY KEY CHECK (btrim(harmonized_product) <> '')
);

INSERT INTO data_warehouse.product (harmonized_product)
SELECT DISTINCT harmonized_product
FROM clean.complaints
ORDER BY harmonized_product;


-- CFPB issue categories. NULL issues stay NULL on complaint row; only holds the non-null distinct values.
DROP TABLE IF EXISTS data_warehouse.issue CASCADE;
CREATE TABLE data_warehouse.issue (
    issue TEXT PRIMARY KEY CHECK (btrim(issue) <> '')
);

INSERT INTO data_warehouse.issue (issue)
SELECT DISTINCT issue
FROM clean.complaints
WHERE issue IS NOT NULL AND btrim(issue) <> ''
ORDER BY issue;


-- How company closed a complaint.
DROP TABLE IF EXISTS data_warehouse.response_type CASCADE;
CREATE TABLE data_warehouse.response_type (
    response_type TEXT PRIMARY KEY CHECK (btrim(response_type) <> '')
);

INSERT INTO data_warehouse.response_type (response_type)
SELECT DISTINCT company_response_to_consumer
FROM clean.complaints
WHERE company_response_to_consumer IS NOT NULL AND btrim(company_response_to_consumer) <> ''
ORDER BY company_response_to_consumer;


-- Submission channel (Web, Referral, Phone, etc.).
DROP TABLE IF EXISTS data_warehouse.submission_channel CASCADE;
CREATE TABLE data_warehouse.submission_channel (
    channel TEXT PRIMARY KEY CHECK (btrim(channel) <> '')
);

INSERT INTO data_warehouse.submission_channel (channel)
SELECT DISTINCT submitted_via_channel
FROM clean.complaints
WHERE submitted_via_channel IS NOT NULL AND btrim(submitted_via_channel) <> ''
ORDER BY submitted_via_channel;


-- State codes. UNION of every state coded column in source data so no FK from any downstream table can fail on a code
-- that appears in only one of them.
DROP TABLE IF EXISTS data_warehouse.state CASCADE;
CREATE TABLE data_warehouse.state (
    state_code CHAR(2) PRIMARY KEY
);

INSERT INTO data_warehouse.state (state_code)
SELECT DISTINCT code FROM (
    SELECT headquarters_state_code AS code FROM clean.institutions
    UNION
    SELECT consumer_state_code            FROM clean.complaints
    UNION
    SELECT acquiring_state_code           FROM clean.failures
) s
WHERE code IS NOT NULL
ORDER BY code;

-- Holding company dimension. Extracted from the institution records.
-- A single holding company can own multiple charters (1-to-many relationship).
DROP TABLE IF EXISTS data_warehouse.holding_company CASCADE;
CREATE TABLE data_warehouse.holding_company (
    holding_company_id   INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    holding_company_name TEXT NOT NULL UNIQUE CHECK (btrim(holding_company_name) <> '')
);

INSERT INTO data_warehouse.holding_company (holding_company_name)
SELECT DISTINCT holding_company_name
FROM clean.institutions
WHERE holding_company_name IS NOT NULL
ORDER BY holding_company_name;


COMMIT;