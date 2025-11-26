#!/usr/bin/env python3
"""
Apply continuous aggregates to TimescaleDB hypertable (Strategy 3).

This script creates continuous aggregates (materialized views) for common
aggregation patterns in the booking queries.
"""

import argparse
import logging
import sys

import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def apply_continuous_aggregates(host: str, port: int, database: str, user: str, password: str):
    """Apply continuous aggregates to booking hypertable."""
    conn_str = f"host={host} port={port} dbname={database} user={user} password={password}"

    logger.info("=" * 70)
    logger.info("Applying TimescaleDB Continuous Aggregates (Strategy 3)")
    logger.info("=" * 70)

    try:
        conn = psycopg2.connect(conn_str)
        conn.autocommit = True

        with conn.cursor() as cursor:
            logger.info("Verifying booking is a hypertable...")
            cursor.execute("""
                SELECT hypertable_name
                FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'booking';
            """)
            if not cursor.fetchone():
                logger.error("booking is not a hypertable! Run convert_to_hypertable.py first.")
                sys.exit(1)
            logger.info("✓ Verified")

            logger.info("Creating continuous aggregate for daily booking counts by offerer...")
            cursor.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS booking_daily_counts_by_offerer
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('1 day'::interval, "dateCreated") AS day,
                    "offererId",
                    COUNT(*) as booking_count,
                    SUM(quantity) as total_quantity
                FROM booking
                GROUP BY day, "offererId"
                WITH NO DATA;
            """)
            logger.info("✓ Created booking_daily_counts_by_offerer")

            logger.info("Creating continuous aggregate for daily booking counts by venue...")
            cursor.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS booking_daily_counts_by_venue
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('1 day'::interval, "dateCreated") AS day,
                    "venueId",
                    COUNT(*) as booking_count,
                    SUM(quantity) as total_quantity
                FROM booking
                GROUP BY day, "venueId"
                WITH NO DATA;
            """)
            logger.info("✓ Created booking_daily_counts_by_venue")

            logger.info("Creating continuous aggregate for daily booking counts by status...")
            cursor.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS booking_daily_counts_by_status
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('1 day'::interval, "dateCreated") AS day,
                    status,
                    COUNT(*) as booking_count,
                    SUM(quantity) as total_quantity
                FROM booking
                GROUP BY day, status
                WITH NO DATA;
            """)
            logger.info("✓ Created booking_daily_counts_by_status")

            logger.info("Creating continuous aggregate for hourly booking stats...")
            cursor.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS booking_hourly_stats
                WITH (timescaledb.continuous) AS
                SELECT
                    time_bucket('1 hour'::interval, "dateCreated") AS hour,
                    "offererId",
                    "venueId",
                    status,
                    COUNT(*) as booking_count,
                    SUM(quantity) as total_quantity,
                    SUM(amount) as total_amount
                FROM booking
                GROUP BY hour, "offererId", "venueId", status
                WITH NO DATA;
            """)
            logger.info("✓ Created booking_hourly_stats")

            logger.info("Refreshing continuous aggregates (this may take a while)...")
            cursor.execute("CALL refresh_continuous_aggregate('booking_daily_counts_by_offerer', NULL, NULL);")
            logger.info("✓ Refreshed booking_daily_counts_by_offerer")

            cursor.execute("CALL refresh_continuous_aggregate('booking_daily_counts_by_venue', NULL, NULL);")
            logger.info("✓ Refreshed booking_daily_counts_by_venue")

            cursor.execute("CALL refresh_continuous_aggregate('booking_daily_counts_by_status', NULL, NULL);")
            logger.info("✓ Refreshed booking_daily_counts_by_status")

            cursor.execute("CALL refresh_continuous_aggregate('booking_hourly_stats', NULL, NULL);")
            logger.info("✓ Refreshed booking_hourly_stats")

            logger.info("Adding refresh policies (auto-refresh every 1 hour)...")
            cursor.execute("""
                SELECT add_continuous_aggregate_policy('booking_daily_counts_by_offerer',
                    start_offset => INTERVAL '3 days',
                    end_offset => INTERVAL '1 hour',
                    schedule_interval => INTERVAL '1 hour');
            """)
            cursor.execute("""
                SELECT add_continuous_aggregate_policy('booking_daily_counts_by_venue',
                    start_offset => INTERVAL '3 days',
                    end_offset => INTERVAL '1 hour',
                    schedule_interval => INTERVAL '1 hour');
            """)
            cursor.execute("""
                SELECT add_continuous_aggregate_policy('booking_daily_counts_by_status',
                    start_offset => INTERVAL '3 days',
                    end_offset => INTERVAL '1 hour',
                    schedule_interval => INTERVAL '1 hour');
            """)
            cursor.execute("""
                SELECT add_continuous_aggregate_policy('booking_hourly_stats',
                    start_offset => INTERVAL '3 days',
                    end_offset => INTERVAL '1 hour',
                    schedule_interval => INTERVAL '1 hour');
            """)
            logger.info("✓ Refresh policies added")

            logger.info("Verifying continuous aggregates...")
            cursor.execute("""
                SELECT view_name, materialized_only
                FROM timescaledb_information.continuous_aggregates
                ORDER BY view_name;
            """)
            results = cursor.fetchall()
            if results:
                logger.info(f"✓ Found {len(results)} continuous aggregates:")
                for view_name, materialized_only in results:
                    logger.info(f"  - {view_name} (materialized_only: {materialized_only})")

        conn.close()

        logger.info("=" * 70)
        logger.info("✓ Continuous aggregates applied successfully!")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Continuous aggregates failed: {e}", exc_info=True)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Apply continuous aggregates to TimescaleDB hypertable")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5435)
    parser.add_argument("--database-name", default="pass_culture")
    parser.add_argument("--user", default="pass_culture")
    parser.add_argument("--password", default="passq")

    args = parser.parse_args()

    apply_continuous_aggregates(
        host=args.host,
        port=args.port,
        database=args.database_name,
        user=args.user,
        password=args.password,
    )


if __name__ == "__main__":
    main()
