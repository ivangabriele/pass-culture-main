#!/usr/bin/env python3
"""
Convert booking table to TimescaleDB hypertable.

This script converts the existing booking table to a TimescaleDB hypertable
partitioned by dateCreated timestamp.
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


def convert_to_hypertable(host: str, port: int, database: str, user: str, password: str):
    """Convert booking table to TimescaleDB hypertable."""
    conn_str = f"host={host} port={port} dbname={database} user={user} password={password}"

    logger.info("=" * 70)
    logger.info("Converting booking table to TimescaleDB hypertable")
    logger.info("=" * 70)

    try:
        conn = psycopg2.connect(conn_str)
        conn.autocommit = True

        with conn.cursor() as cursor:
            logger.info("Checking if booking is already a hypertable...")
            cursor.execute("""
                SELECT * FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'booking';
            """)
            already_hypertable = cursor.fetchone() is not None

            if already_hypertable:
                logger.info("✓ booking is already a hypertable!")
            else:
                logger.info("Dropping primary key and unique constraints...")
                cursor.execute('ALTER TABLE booking DROP CONSTRAINT IF EXISTS booking_pkey CASCADE;')
                cursor.execute('ALTER TABLE booking DROP CONSTRAINT IF EXISTS booking_token_key CASCADE;')
                logger.info("✓ Constraints dropped")

                logger.info("Creating hypertable (this may take a while with migrate_data=true)...")
                cursor.execute("""
                    SELECT create_hypertable(
                        'booking',
                        by_range('dateCreated'),
                        migrate_data => true,
                        if_not_exists => true
                    );
                """)
                logger.info("✓ Hypertable created successfully!")

            logger.info("Recreating indexes...")
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_booking_date_created
                ON booking ("dateCreated" DESC);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_booking_offerer_date
                ON booking ("offererId", "dateCreated" DESC);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_booking_venue_date
                ON booking ("venueId", "dateCreated" DESC);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_booking_status_date
                ON booking (status, "dateCreated" DESC);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_booking_token
                ON booking (token);
            """)
            logger.info("✓ Indexes recreated")
            logger.info("  Note: Token index is non-unique due to TimescaleDB partitioning constraints")

            logger.info("Verifying hypertable...")
            cursor.execute("""
                SELECT hypertable_name, num_dimensions
                FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'booking';
            """)
            result = cursor.fetchone()
            if result:
                logger.info(f"✓ Verification successful: {result[0]} with {result[1]} dimension(s)")

            logger.info("Checking chunks...")
            cursor.execute("""
                SELECT chunk_name, range_start, range_end
                FROM timescaledb_information.chunks
                WHERE hypertable_name = 'booking'
                ORDER BY range_start
                LIMIT 5;
            """)
            chunks = cursor.fetchall()
            logger.info(f"✓ Found {len(chunks)} initial chunks (showing first 5):")
            for chunk_name, range_start, range_end in chunks:
                logger.info(f"  - {chunk_name}: {range_start} to {range_end}")

        conn.close()

        logger.info("=" * 70)
        logger.info("✓ Conversion completed successfully!")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Conversion failed: {e}", exc_info=True)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Convert booking table to TimescaleDB hypertable")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5435)
    parser.add_argument("--database-name", default="pass_culture")
    parser.add_argument("--user", default="pass_culture")
    parser.add_argument("--password", default="passq")

    args = parser.parse_args()

    convert_to_hypertable(
        host=args.host,
        port=args.port,
        database=args.database_name,
        user=args.user,
        password=args.password,
    )


if __name__ == "__main__":
    main()
