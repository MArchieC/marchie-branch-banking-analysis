-- Builds the entire database from raw CSV in an idempotent manner.
-- Run from repository root:  psql -f sql/run_all_sql.sql

-- psql sees a backslash, understands it as a meta-command, and sets variable.
-- No SQL is sent to the server.
\set ON_ERROR_STOP on

-- Quiet the "does not exist, skipping" NOTICEs emitted by
-- DROP ... IF EXISTS in the schema files below.
SET client_min_messages = warning;


-- ======================================================================================
-- STEP 1 Staging: flatten raw files into clean.* tables. Python not psql.
-- Run `python src/run_all_python_cleaning.py` before this run_all_sql.sql script.
-- ======================================================================================

-- ======================================================================================
-- STEP 2 Data Warehouse schema: lookups first then tables referencing lookups.
-- All Data Warehouse tables read from clean.* tables.
-- ======================================================================================

\echo === START: sql/01_data_warehouse/* ===

\echo === 01_data_warehouse/01_create_schema.sql ===
\i sql/01_data_warehouse/01_create_schema.sql

\echo === 01_data_warehouse/02_create_lookups.sql ===
\i sql/01_data_warehouse/02_create_lookups.sql

\echo === 01_data_warehouse/03_create_institutions.sql ===
\i sql/01_data_warehouse/03_create_institutions.sql

\echo === 01_data_warehouse/04_create_financials.sql ===
\i sql/01_data_warehouse/04_create_financials.sql

\echo === 01_data_warehouse/05_create_failures.sql ===
\i sql/01_data_warehouse/05_create_failures.sql

\echo === 01_data_warehouse/06_create_crosswalk.sql ===
\i sql/01_data_warehouse/06_create_crosswalk.sql

\echo === 01_data_warehouse/07_create_complaints.sql ===
\i sql/01_data_warehouse/07_create_complaints.sql

\echo === 01_data_warehouse/08_create_macro.sql ===
\i sql/01_data_warehouse/08_create_macro.sql

\echo === END: sql/01_data_warehouse/*  ===

-- ======================================================================================
-- STEP 3 Data Mart (star schema): Built from data warehouse and read by Power BI.
-- ======================================================================================

\echo === START: sql/02_data_mart/* ===

\echo === 02_data_mart/01_create_schema.sql ===
\i sql/02_data_mart/01_create_schema.sql

\echo === 02_data_mart/02_dim_date_quarterly.sql ===
\i sql/02_data_mart/02_dim_date_quarterly.sql

\echo === 02_data_mart/03_dim_date_daily.sql ===
\i sql/02_data_mart/03_dim_date_daily.sql

\echo === 02_data_mart/04_dim_bank.sql ===
\i sql/02_data_mart/04_dim_bank.sql

\echo === 02_data_mart/05_dim_crosswalk.sql ===
\i sql/02_data_mart/05_dim_crosswalk.sql

\echo === 02_data_mart/06_fact_bank_quarter.sql ===
\i sql/02_data_mart/06_fact_bank_quarter.sql

\echo === 02_data_mart/07_fact_complaints.sql ===
\i sql/02_data_mart/07_fact_complaints.sql

\echo === 02_data_mart/08_fact_failures.sql ===
\i sql/02_data_mart/08_fact_failures.sql

\echo === sql/02_data_mart/09_fact_concentration.sql ===
\i sql/02_data_mart/09_fact_concentration.sql

\echo === END: sql/02_data_mart/* ===


-- ======================================================================================
-- STEP 4 Data warehouse and mart maintenance.
-- VACUUM ANALYZE after load so visibility map is clean and planner's statistics reflect
-- loaded rows. Without this, Index Only Scan falls back to fetching from heap on every
-- row, and first query plans against estimates from before load.

-- On this build tables are freshly created and populated, so there are no dead tuples
-- to reclaim - VACUUM is for visibility and statistics only. After a long running
-- deployment with many updates, same VACUUM also reclaims dead tuple space, but that
-- is not what the build needs.

-- \gexec is used instead of a DO block because VACUUM cannot run inside a transaction
-- block, and DO blocks run as a single transaction. \gexec runs each generated statement
-- as its own statement, outside any transaction.
-- ======================================================================================

\echo === START: VACUUM ANALYZE ===

SELECT format('VACUUM ANALYZE %I.%I;', schemaname, tablename)
FROM pg_tables
WHERE schemaname IN ('data_warehouse', 'data_mart')
ORDER BY schemaname, tablename
\gexec

\echo === END: VACUUM ANALYZE ===

\echo ''

\echo === SUCCESS: Database (warehouse + mart) build complete (with clean visibility maps and current planners'' stats) ===