#!/usr/bin/env bash
set -euo pipefail

echo "======================================================================"
echo "TimescaleDB Performance Benchmark - Full Test Suite"
echo "Production-scale data: 2M users, 100K offerers, 200K venues, 2M offers, 5M stocks, 10M bookings"
echo "======================================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOGS_DIR="$WORKSPACE_ROOT/logs"
RESULTS_DIR="$WORKSPACE_ROOT/results"

mkdir -p "$LOGS_DIR"
mkdir -p "$RESULTS_DIR"

cd "$WORKSPACE_ROOT"

echo ""
echo "======================================================================"
echo "Step 1: Ensuring infrastructure is running"
echo "======================================================================"
podman compose -f ./docker-compose-backend.yml up -d postgres postgres-test redis timescaledb
sleep 5

echo ""
echo "======================================================================"
echo "Step 2: Initializing databases with clean schema"
echo "======================================================================"

source .venv/bin/activate
cd api

echo "Running migrations on PostgreSQL..."
alembic -x dbUrl=postgresql://pass_culture:passq@localhost:5434/pass_culture upgrade pre@head
alembic -x dbUrl=postgresql://pass_culture:passq@localhost:5434/pass_culture upgrade post@head

echo "Running migrations on TimescaleDB..."
alembic -x dbUrl=postgresql://pass_culture:passq@localhost:5435/pass_culture upgrade pre@head
alembic -x dbUrl=postgresql://pass_culture:passq@localhost:5435/pass_culture upgrade post@head

echo "Disabling triggers for test data insertion..."
podman exec pc-postgres psql -U pass_culture -d pass_culture -c "ALTER TABLE \"user\" DISABLE TRIGGER ensure_password_or_sso_exists;"
podman exec pc-postgres psql -U pass_culture -d pass_culture -c "ALTER TABLE booking DISABLE TRIGGER booking_update;"
podman exec pc-timescaledb psql -U pass_culture -d pass_culture -c "ALTER TABLE \"user\" DISABLE TRIGGER ensure_password_or_sso_exists;"
podman exec pc-timescaledb psql -U pass_culture -d pass_culture -c "ALTER TABLE booking DISABLE TRIGGER booking_update;"

echo ""
echo "======================================================================"
echo "Step 3: Seeding PostgreSQL with production-scale data"
echo "======================================================================"
python ../scripts/seed_timescaledb_standalone.py \
    --host localhost \
    --port 5434 \
    --database pass_culture \
    --user pass_culture \
    --password passq \
    2>&1 | tee "$LOGS_DIR/seed_postgres_production.log"

echo ""
echo "======================================================================"
echo "Step 4: Seeding TimescaleDB with production-scale data"
echo "======================================================================"
python ../scripts/seed_timescaledb_standalone.py \
    --host localhost \
    --port 5435 \
    --database pass_culture \
    --user pass_culture \
    --password passq \
    2>&1 | tee "$LOGS_DIR/seed_timescaledb_production.log"

echo ""
echo "======================================================================"
echo "Step 5: Running baseline PostgreSQL benchmarks (10 runs)"
echo "======================================================================"
python ../scripts/benchmark_bookings_query.py \
    --database postgres \
    --host localhost \
    --port 5434 \
    --output "$RESULTS_DIR/baseline_postgres.json" \
    2>&1 | tee "$LOGS_DIR/benchmark_postgres.log"

echo ""
echo "======================================================================"
echo "Step 6: Converting TimescaleDB booking to hypertable (Strategy 1)"
echo "======================================================================"
python ../scripts/convert_to_hypertable.py \
    --host localhost \
    --port 5435 \
    --database-name pass_culture \
    --user pass_culture \
    --password passq \
    2>&1 | tee "$LOGS_DIR/convert_hypertable.log"

echo ""
echo "======================================================================"
echo "Step 7: Running Strategy 1 benchmarks (Hypertable, 10 runs)"
echo "======================================================================"
python ../scripts/benchmark_bookings_query.py \
    --database timescaledb \
    --host localhost \
    --port 5435 \
    --output "$RESULTS_DIR/strategy1_hypertable.json" \
    2>&1 | tee "$LOGS_DIR/benchmark_strategy1.log"

echo ""
echo "======================================================================"
echo "Step 8: Applying compression to TimescaleDB (Strategy 2)"
echo "======================================================================"
python ../scripts/apply_compression.py \
    --host localhost \
    --port 5435 \
    --database-name pass_culture \
    --user pass_culture \
    --password passq \
    2>&1 | tee "$LOGS_DIR/apply_compression.log"

echo ""
echo "======================================================================"
echo "Step 9: Running Strategy 2 benchmarks (Compression, 10 runs)"
echo "======================================================================"
python ../scripts/benchmark_bookings_query.py \
    --database timescaledb \
    --host localhost \
    --port 5435 \
    --output "$RESULTS_DIR/strategy2_compression.json" \
    2>&1 | tee "$LOGS_DIR/benchmark_strategy2.log"

echo ""
echo "======================================================================"
echo "Step 10: Generating comparison report"
echo "======================================================================"
python ../scripts/analyze_results.py \
    --results-dir "$RESULTS_DIR" \
    --output "$RESULTS_DIR/comparison_report.txt" \
    2>&1 | tee "$LOGS_DIR/analyze_results.log"

echo ""
echo "======================================================================"
echo "Benchmark Complete!"
echo "======================================================================"
echo "Results saved to: $RESULTS_DIR"
echo "Logs saved to: $LOGS_DIR"
echo ""
echo "Generated files:"
echo "  - $RESULTS_DIR/baseline_postgres.json"
echo "  - $RESULTS_DIR/strategy1_hypertable.json"
echo "  - $RESULTS_DIR/strategy2_compression.json"
echo "  - $RESULTS_DIR/comparison_report.txt"
echo "======================================================================"
