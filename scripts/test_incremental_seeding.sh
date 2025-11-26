#!/bin/bash
# Incremental Seeding Performance Test
#
# Tests the seeding script with progressively larger datasets
# to measure performance and estimate time for larger volumes.

set -e

echo "===================================================================="
echo "Incremental Seeding Performance Test"
echo "===================================================================="
echo ""

# Activate venv
source ../.venv/bin/activate
cd ../api

# Test sizes
SIZES=(10000 100000 500000)

for SIZE in "${SIZES[@]}"; do
    echo "--------------------------------------------------------------------"
    echo "Testing with $SIZE bookings..."
    echo "--------------------------------------------------------------------"

    START_TIME=$(date +%s)

    python ../scripts/seed_timescaledb.py \
        --target-bookings "$SIZE" \
        --batch-size 10000 \
        --skip-postgres \
        2>&1 | tee "../logs/seed_${SIZE}.log"

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo "✓ Completed $SIZE bookings in $DURATION seconds"
    echo "  Rate: $((SIZE / DURATION)) bookings/second"
    echo ""

    # Extrapolate to larger sizes
    RATE=$((SIZE / DURATION))
    echo "Extrapolations:"
    echo "  1M bookings: ~$((1000000 / RATE)) seconds (~$((1000000 / RATE / 60)) minutes)"
    echo "  2M bookings: ~$((2000000 / RATE)) seconds (~$((2000000 / RATE / 60)) minutes)"
    echo "  5M bookings: ~$((5000000 / RATE)) seconds (~$((5000000 / RATE / 60)) minutes)"
    echo ""
done

echo "===================================================================="
echo "✓ Incremental testing completed!"
echo "===================================================================="
