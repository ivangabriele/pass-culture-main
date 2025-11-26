# TimescaleDB Experimentation Status

## Current Objective

**Goal**: Benchmark PostgreSQL vs TimescaleDB for the `get_bookings_pro` endpoint with production-scale data (2M users, 100K offerers, 200K venues, 2M offers, 5M stocks, 10M bookings over 5 years).

**Status**: Ready to seed databases with corrected script after fixing critical execute_values bug.

## Progress Summary

### Phase 1: Research & Setup ✅

#### 1.1 Analysis of Current Implementation ✅
- Analyzed `get_bookings_pro` endpoint in `api/src/pcapi/routes/pro/bookings.py:45`
- Identified main query function: `booking_repository.find_by_pro_user()`
- Key bottlenecks identified:
  - Multiple table joins (booking → offerer → user_offerer → stock → offer → venue → addresses)
  - Period-based filtering with timezone conversions across multiple timezones
  - Date range queries on different columns (dateCreated, dateUsed, reimbursementDate) depending on status filter
  - Complex `ORDER BY dateCreated DESC` with pagination
  - Two separate queries: one for count, one for data retrieval

#### 1.2 Booking Table Structure Analysis ✅
- **Time-series fields**: dateCreated, dateUsed, cancellationDate, reimbursementDate
- **Foreign keys** (6): stockId, venueId, offererId, userId, depositId, cancellationUserId
- **Indexes**: dateCreated, dateUsed, status, all FK fields
- **Partial indexes**: cancellationUserId, cancellationReason
- Perfect candidate for TimescaleDB hypertables (time-series partitioning on dateCreated)

#### 1.3 TimescaleDB Infrastructure Setup ✅
- ✅ Added TimescaleDB service to `docker-compose-backend.yml`
  - Image: `timescale/timescaledb-ha:pg15-all`
  - Port: `5435` (host) → `5432` (container)
  - Container name: `pc-timescaledb`
  - Network: `db_nw` (same as main PostgreSQL)
- ✅ Created initialization script: `timescaledb-init/01-init.sql`
  - Extensions: timescaledb, postgis, postgis_tiger_geocoder, postgis_topology
  - Additional: btree_gist, pg_trgm, fuzzystrmatch, unaccent
- ✅ Verified installation:
  ```
  timescaledb            | 2.23.0  | Enables scalable inserts and complex queries for time-series data
  postgis                | 3.6.1   | PostGIS geometry and geography spatial types and functions
  ```

### Phase 2: Implementation ✅

#### 2.1 Production-Scale Seed Script ✅
**File**: `scripts/seed_timescaledb_standalone.py`

**Strategy**: Standalone script that generates complete dataset without relying on existing seed data.

**Target Dataset**:
- 2,000,000 users
- 2,000,000 deposits (€5000 each)
- 100,000 offerers
- 100,000 addresses (Paris area with realistic coordinates)
- 100,000 offerer_addresses
- 200,000 venues (2 per offerer on average)
- 2,000,000 offers (10 per venue on average)
- 5,000,000 stocks (2.5 per offer on average)
- 10,000,000 bookings (2 per stock on average)

**Data Characteristics**:
- Realistic date distribution (spread over 5 years: 2020-2025)
- Recent bias for bookings (weighted toward recent dates using quadratic distribution)
- Status distribution: 50% CONFIRMED, 30% USED, 15% CANCELLED, 5% REIMBURSED
- Batch processing for performance (10,000 record batches)
- Progress logging every batch

**Critical Bug Fixed** ✅:
- **Issue**: psycopg2's `execute_values()` paginates internally with default `page_size=100`
- **Impact**: When using `RETURNING` clause, `cursor.fetchall()` only returns results from the LAST page
- **Symptom**: Only 1% of expected IDs were captured (100 out of 10,000 per batch)
- **Solution**: Added `page_size=len(values)` to all `execute_values()` calls with `RETURNING` clause
- **Fixed in**: `_generate_users`, `_generate_deposits`, `_generate_offerers`, `_generate_addresses`, `_generate_offerer_addresses`, `_generate_venues`, `_generate_offers`, `_generate_stocks`

#### 2.2 Benchmark Script ✅
**File**: `scripts/benchmark_bookings_query.py`

**Queries Tested** (11 scenarios):
1. `count_query_30d` - Count bookings in last 30 days
2. `count_query_90d` - Count bookings in last 90 days
3. `count_query_365d` - Count bookings in last year
4. `list_query_30d_page1` - List first page of bookings (30d, 20 results)
5. `list_query_30d_page5` - List fifth page of bookings (30d, offset 80)
6. `list_query_90d_page1` - List first page of bookings (90d, 20 results)
7. `list_query_365d_page1` - List first page of bookings (1y, 20 results)
8. `status_filter_CONFIRMED_90d` - Filter by CONFIRMED status (90d)
9. `status_filter_USED_90d` - Filter by USED status (90d)
10. `status_filter_CANCELLED_90d` - Filter by CANCELLED status (90d)
11. `venue_filter_60d` - Filter by specific venue (60d)

**Output**: JSON file with execution times (mean, median, p95, p99) for 10 runs per query.

#### 2.3 TimescaleDB Strategy Scripts ✅

**Strategy 1: Hypertable** ✅
- **File**: `scripts/convert_to_hypertable.py`
- Converts `booking` table to hypertable partitioned by `dateCreated`
- Chunk interval: 7 days (optimized for weekly queries)
- Automatically creates chunks for existing data
- Migrates all data and indexes

**Strategy 2: Compression** ✅
- **File**: `scripts/apply_compression.py`
- Adds native TimescaleDB compression to hypertable
- Compression settings:
  - `orderby`: `dateCreated DESC` (optimize time-range queries)
  - `segmentby`: `offererId, venueId, status` (common filter columns)
- Compression policy: Auto-compress chunks older than 7 days (configurable)
- Manually compresses all existing chunks
- Reports compression ratios per chunk

**Orchestration Script** ✅
- **File**: `scripts/run_full_benchmark.sh`
- End-to-end automated benchmark pipeline:
  1. Start infrastructure (postgres, timescaledb, redis)
  2. Run Alembic migrations on both databases
  3. Disable triggers (ensure_password_or_sso_exists, booking_update)
  4. Seed PostgreSQL with production-scale data
  5. Seed TimescaleDB with production-scale data
  6. Run baseline PostgreSQL benchmarks (10 runs)
  7. Convert TimescaleDB booking to hypertable
  8. Run Strategy 1 benchmarks (10 runs)
  9. Apply 365-day compression policy
  10. Run Strategy 2 benchmarks (10 runs)
  11. Generate comparison report
- All outputs logged to `logs/` directory
- All results saved to `results/` directory

**Analysis Script** ✅
- **File**: `scripts/analyze_results.py`
- Compares performance across all strategies
- Calculates speedup ratios
- Identifies best/worst performers per query
- Generates human-readable report

### Phase 3: Benchmarking 🔄

#### Current Blockers
- ✅ Critical bug fixed (execute_values page_size)
- ✅ All infrastructure scripts completed
- ✅ All volumes cleaned

#### Next Steps
1. **Restart infrastructure**: Start postgres, timescaledb, redis containers
2. **Run migrations**: Apply Alembic schema to both databases
3. **Disable triggers**: Prevent validation triggers during bulk insert
4. **Seed databases**: Run corrected seed script for both PostgreSQL and TimescaleDB
5. **Execute benchmark pipeline**: Run `run_full_benchmark.sh`
6. **Analyze results**: Review performance comparison report

## Technical Details

### Database Trigger Management
Before seeding, these triggers must be disabled:
```sql
-- PostgreSQL (port 5434)
ALTER TABLE "user" DISABLE TRIGGER ensure_password_or_sso_exists;
ALTER TABLE booking DISABLE TRIGGER booking_update;

-- TimescaleDB (port 5435)
ALTER TABLE "user" DISABLE TRIGGER ensure_password_or_sso_exists;
ALTER TABLE booking DISABLE TRIGGER booking_update;
```

### Seed Script Critical Fix
**Before** (buggy):
```python
execute_values(cursor, """...""", values)  # Defaults to page_size=100
all_ids.extend([row[0] for row in cursor.fetchall()])  # Only gets last 100!
```

**After** (fixed):
```python
execute_values(cursor, """...""", values, page_size=len(values))  # One page
all_ids.extend([row[0] for row in cursor.fetchall()])  # Gets all IDs!
```

### Estimated Timings
Based on previous runs:
- User generation: ~40s for 2M users
- Deposit generation: ~10s for 2M deposits
- Offerer generation: ~5s for 100K offerers
- Address generation: ~5s for 100K addresses
- Venue generation: ~10s for 200K venues
- Offer generation: ~10s for 2M offers
- Stock generation: ~25s for 5M stocks
- Booking generation: ~300-400s for 10M bookings
- **Total seeding time**: ~7-8 minutes per database

## Connection Details

- **PostgreSQL** (main): `localhost:5434`
- **TimescaleDB**: `localhost:5435`
- **Database**: `pass_culture`
- **User**: `pass_culture`
- **Password**: `passq`

## Quick Start Commands

### Clean Start (Fresh Volumes)
```bash
# Stop all and remove volumes
podman compose -f ./docker-compose-backend.yml down -v

# Start infrastructure
podman compose -f ./docker-compose-backend.yml up -d postgres postgres-test redis timescaledb

# Wait 5 seconds for containers to be ready
sleep 5

# Run migrations
source .venv/bin/activate
cd api
alembic -x dbUrl=postgresql://pass_culture:passq@localhost:5434/pass_culture upgrade pre@head
alembic -x dbUrl=postgresql://pass_culture:passq@localhost:5434/pass_culture upgrade post@head
alembic -x dbUrl=postgresql://pass_culture:passq@localhost:5435/pass_culture upgrade pre@head
alembic -x dbUrl=postgresql://pass_culture:passq@localhost:5435/pass_culture upgrade post@head

# Disable triggers
podman exec pc-postgres psql -U pass_culture -d pass_culture -c "ALTER TABLE \"user\" DISABLE TRIGGER ensure_password_or_sso_exists;"
podman exec pc-postgres psql -U pass_culture -d pass_culture -c "ALTER TABLE booking DISABLE TRIGGER booking_update;"
podman exec pc-timescaledb psql -U pass_culture -d pass_culture -c "ALTER TABLE \"user\" DISABLE TRIGGER ensure_password_or_sso_exists;"
podman exec pc-timescaledb psql -U pass_culture -d pass_culture -c "ALTER TABLE booking DISABLE TRIGGER booking_update;"

# Seed PostgreSQL
python ../scripts/seed_timescaledb_standalone.py \
    --host localhost \
    --port 5434 \
    --database pass_culture \
    --user pass_culture \
    --password passq

# Seed TimescaleDB
python ../scripts/seed_timescaledb_standalone.py \
    --host localhost \
    --port 5435 \
    --database pass_culture \
    --user pass_culture \
    --password passq
```

### Run Full Benchmark Pipeline
```bash
cd /home/ivan/Workspace/pass-culture/pass-culture-main
./scripts/run_full_benchmark.sh
```

### Check TimescaleDB Status
```bash
podman ps --filter name=pc-timescaledb
```

### Connect to Databases
```bash
# PostgreSQL
podman exec -it pc-postgres psql -U pass_culture -d pass_culture

# TimescaleDB
podman exec -it pc-timescaledb psql -U pass_culture -d pass_culture
```

## Known Issues & Solutions

### Issue #1: execute_values page_size Bug ✅ FIXED
- **Symptom**: Seed script fails with "IndexError: list index out of range"
- **Cause**: `cursor.fetchall()` only returns RETURNING results from last page when `execute_values` paginates
- **Solution**: Add `page_size=len(values)` to ensure single page per batch
- **Status**: Fixed in all affected methods

### Issue #2: Postal Code Constraint Violation ✅ FIXED
- **Symptom**: Address generation fails with check constraint violation
- **Cause**: Generated postal codes outside valid range (10000-99999)
- **Solution**: Changed formula from `(i % 90000 + 1000)` to `(i % 90000 + 10000)`
- **Status**: Fixed in `_generate_addresses()` and `_generate_venues()`

## Files Created

### Scripts
- `scripts/seed_timescaledb_standalone.py` - Production-scale data generator
- `scripts/benchmark_bookings_query.py` - Query performance benchmark
- `scripts/convert_to_hypertable.py` - Strategy 1: Convert to hypertable
- `scripts/apply_compression.py` - Strategy 2: Add compression
- `scripts/analyze_results.py` - Results analysis and comparison
- `scripts/run_full_benchmark.sh` - End-to-end orchestration

### Infrastructure
- `docker-compose-backend.yml` - Added TimescaleDB service
- `timescaledb-init/01-init.sql` - Database initialization script

### Outputs (Generated)
- `logs/seed_postgres_production.log` - PostgreSQL seeding log
- `logs/seed_timescaledb_production.log` - TimescaleDB seeding log
- `logs/benchmark_postgres.log` - PostgreSQL benchmark log
- `logs/convert_hypertable.log` - Hypertable conversion log
- `logs/benchmark_strategy1.log` - Strategy 1 benchmark log
- `logs/apply_compression.log` - Compression application log
- `logs/benchmark_strategy2.log` - Strategy 2 benchmark log
- `results/baseline_postgres.json` - PostgreSQL benchmark results
- `results/strategy1_hypertable.json` - Hypertable benchmark results
- `results/strategy2_compression.json` - Compression benchmark results
- `results/comparison_report.txt` - Performance comparison report

## Lessons Learned

1. **psycopg2 execute_values behavior**: Always set `page_size=len(values)` when using `RETURNING` clause to ensure all results are captured in `cursor.fetchall()`.

2. **Batch size matters**: 10,000 records per batch provides good balance between memory usage and insert performance.

3. **Trigger management**: Database triggers must be disabled during bulk inserts to avoid performance penalties and validation errors on test data.

4. **Data realism**: Realistic data distribution (dates, statuses, relationships) is critical for meaningful benchmarks.

5. **Progress logging**: Essential for long-running operations to monitor progress and identify bottlenecks.
