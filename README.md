# Bank Health and Customer Complaints Capstone

Analysis of the Federal Deposit Insurance Corporation's (FDIC) bank directory, 
quarterly financials and failure records, the Consumer Financial Protection 
Bureau's (CFPB) consumer complaint database, and four economic series from the 
Federal Reserve Economic Data (FRED) system, as a PostgreSQL database and a 
Power Business Intelligence (Power BI) report. See `documentation/findings.md` 
for the written report.

## Table of Contents

1. [Requirements](#1-requirements)
2. [Layout](#2-layout)
3. [Notes](#3-notes)
4. [Setup](#4-setup)
5. [Verify database load](#5-verify-database-load)
   - [5.1 Index demonstrations](#51-index-demonstrations)
   - [5.2 Post build maintenance checks](#52-post-build-maintenance-checks)
6. [Rebuild from scratch](#6-rebuild-from-scratch)

## 1. Requirements

- Docker Desktop, or Docker Engine with the Compose plugin
- Python 3.11+ with the packages in `requirements.txt`
- Power BI Desktop
- The eight raw files


## 2. Layout

```
src/                                Python staging (pandas): raw -> clean.*
  01_clean_institutions.py
  02_clean_financials.py
  03_clean_failures.py
  04_clean_complaints.py
  05_build_crosswalk.py
  06_clean_macro.py
  07_data_quality.py
  postgres_connection.py
  run_all_python_cleaning.py
src_retired_bc_no_pandas/           Python staging (standard library): raw -> clean.*
  (same file structure as src/; kept for reference and comparison)
sql/
  01_data_warehouse/                data_warehouse.* built from clean.*
  02_data_mart/                     Star schema for Power BI, built from data_warehouse.*
  03_directed_analysis/             Analysis queries for Part 5 (read-only)
  04_open_ended_analysis/           Analysis queries for Part 6 (read-only)
  05_index_demos.sql                Index EXPLAIN before/after demos (not part of the build)
  run_all_sql.sql                   Entry point; builds the warehouse and mart in order
  validate_run_all_sql.sql          Read-only load validation; output saved to documentation/
capstone_data/                      Eight raw files (ignored by Git)
documentation/
  crosswalk_method.md               CFPB-to-FDIC name matching method
  findings.md                       Written report
  schema_documentation.md           Model and design decisions
  post_build_maintenance_checks.md  Queries to verify VACUUM ANALYZE ran successfully
  load_validation_output.txt        Output of sql/validate_run_all_sql.sql
  index_demo_output.txt             Output of sql/05_index_demos.sql
  images/                           Schema diagrams and Power BI model view
    bank_health_clean.png
    bank_health_data_mart.png
    bank_health_data_warehouse.png
    bank_health_public.png
    powerbi.png
powerbi/
  Capstone_PowerBI_marchie.pbix
docker-compose.yml                  Postgres 17 container
requirements.txt                    Python dependencies
```

## 3. Notes

- `docker compose up -d --wait` requires Docker Compose v2 (the version bundled with any current Docker Desktop). If you are on an older Compose v1 install, replace the `--wait` with a `until pg_isready` loop; see `docker-compose.yml`'s `healthcheck` for the probe it uses.
- `sql/run_all_sql.sql` and `sql/validate_run_all_sql.sql` use psql
  meta-commands (`\i`, `\set`, `\echo`). They must be run through `psql`, not
  through DBeaver or any other SQL client.
- The Python step must run before the SQL step. `data_warehouse` reads from
  `clean`, which the Python scripts populate.
- The pipeline is idempotent. `run_all_python_cleaning.py` truncates and
  reloads every `clean.*` table; `run_all_sql.sql` drops and recreates every
  `data_warehouse.*` and `data_mart.*` object.
- The report reads only from `data_mart`. Nothing in the Power BI model
  connects to `clean` or `data_warehouse`.
- **Python staging implementations:** The assignment required the Python layer to use `pandas`. Both `src/` (pandas) and `src_retired_bc_no_pandas/` (standard library only) produce identical `clean.*` tables. The standard `src/` is the default used in Setup below. The `src_retired_bc_no_pandas/` version is retained to demonstrate both approaches work.

## 4. Setup

0. Clone the repository.

1. Place the eight raw files in `capstone_data/` — exact filenames as published:
   `cfpb_complaints.csv`, `fdic_failures.csv`, `fdic_financials.csv`,
   `fdic_institutions.json`, `fred_FEDFUNDS.csv`, `fred_UNRATE.csv`,
   `fred_MORTGAGE30US.csv`, `fred_DGS10.csv`. `docker-compose.yml` mounts
   `./capstone_data` at `/data:ro` and `./sql` at `/sql:ro`. Nothing writes to
   either.

2. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Start Postgres and wait for it to be ready:

   ```bash
   docker compose up -d --wait
   ```

4. Build `clean.*` from the raw files (host, not container):

   ```bash
   cd src
   python run_all_python_cleaning.py
   cd ..
   ```

5. Build `data_warehouse.*` and `data_mart.*` from `clean.*`:

   ```bash
   docker exec -i bank_health_db sh -c "cd / && psql -U capstone -d bank_health -f /sql/run_all_sql.sql"
   ```

6. Open the Power BI report:
   
   Open `powerbi/Capstone_PowerBI_marchie.pbix` in Power BI Desktop. The report is in Import mode. If the data model does not automatically refresh, click **Refresh** on the Home ribbon to pull the latest mart data from the local PostgreSQL container. The database is exposed on `localhost:5432`. If Power BI prompts for credentials, use the ones defined in `docker-compose.yml` (database: `bank_health`, user: `capstone`, password: `capstone`, etc.).

## 5. Verify database load

The build is proven correct by four read-only checks. Run them and save the
output to the repository:

```bash
docker exec -i bank_health_db sh -c "cd / && psql -U capstone -d bank_health -f /sql/validate_run_all_sql.sql" > documentation/load_validation_output.txt
```

The saved file contains labelled blocks for:

- **Row counts** - `clean` and `data_warehouse` tables match on row count
  (institutions 27,835; financials 523,136; failures 4,117; complaints
  1,077,624; crosswalk 4,114; macro_quarterly 82).
- **Primary key uniqueness** - no duplicate keys in `institutions`,
  `financials`, or `complaints`.
- **Crosswalk coverage** - 61.65% of complaints join to an FDIC charter.
- **Spot check** - JPMorgan Chase (CERT 628) total assets at 2026-06-30 match
  between `clean.financials` and `data_warehouse.financials`.

To verify interactively instead:

```bash
docker exec -it bank_health_db psql -U capstone -d bank_health
```

Inside psql:

```sql
SELECT COUNT(*) FROM clean.complaints;                -- 1077624
SELECT COUNT(*) FROM data_warehouse.institutions;     -- 27835
SELECT COUNT(*) FROM data_warehouse.financials;       -- 523136
SELECT COUNT(*) FROM data_warehouse.failures;         -- 4117
SELECT COUNT(*) FROM data_warehouse.crosswalk;        -- 4114
SELECT COUNT(*) FROM data_warehouse.complaints;       -- 1077624
SELECT COUNT(*) FROM data_warehouse.macro_quarterly;  -- 82
\q
```

### 5.1 Index demonstrations

`sql/05_index_demos.sql` demonstrates four indexes with `EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)`
before and after: three kept, one removed in two different shapes. It is read only with respect
to loaded data as it only creates and drops indexes while ending with a safety net so re-running
leaves schema unchanged.

Run it against the populated database and save the output to the repository:

```bash
docker exec -i bank_health_db sh -c "cd / && psql -U capstone -d bank_health -f /sql/05_index_demos.sql" > documentation/index_demo_output.txt
```

The reasoning behind each kept/rejected index is in `documentation/findings.md` §1.

### 5.2 Post build maintenance checks

The build script (`run_all_sql.sql`) ends with a `VACUUM ANALYZE` step (STEP 4) to ensure the planner has current statistics and the visibility map is clean. To verify that this maintenance step ran successfully (and that `Index Only Scan` can actually skip the heap), run the three queries in `documentation/post_build_maintenance_checks.md`. 

These queries check that:
1. The visibility map is 100% clean.
2. Statistics exist for every column.
3. Statistics were refreshed during the most recent build.

## 6. Rebuild from scratch

```bash
docker compose down -v
docker compose up -d --wait
cd src && python run_all_python_cleaning.py && cd ..
docker exec -i bank_health_db sh -c "cd / && psql -U capstone -d bank_health -f /sql/run_all_sql.sql"
docker exec -i bank_health_db sh -c "cd / && psql -U capstone -d bank_health -f /sql/validate_run_all_sql.sql" > documentation/load_validation_output.txt
```

Once the rebuild is complete, open the `.pbix` file and click **Refresh** to pull the newly built data into the report.