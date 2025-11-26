#!/usr/bin/env python3
"""
Apply compression policies to TimescaleDB hypertable (Strategy 2).

This script adds native TimescaleDB compression to older chunks of the booking hypertable.
Compression can significantly reduce storage and improve query performance for historical data.
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


def apply_compression(host: str, port: int, database: str, user: str, password: str, compress_after_days: int = 365):
    """Apply compression policies to booking hypertable."""
    conn_str = f"host={host} port={port} dbname={database} user={user} password={password}"

    logger.info("=" * 70)
    logger.info("Applying TimescaleDB Compression (Strategy 2)")
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

            logger.info(f"Configuring compression policy (compress chunks older than {compress_after_days} days)...")

            cursor.execute("""
                ALTER TABLE booking SET (
                    timescaledb.compress,
                    timescaledb.compress_orderby = '"dateCreated" DESC',
                    timescaledb.compress_segmentby = '"offererId", "venueId", status'
                );
            """)
            logger.info("✓ Compression settings configured")
            logger.info("  - Orderby: dateCreated DESC (optimize time-range queries)")
            logger.info("  - Segmentby: offererId, venueId, status (common filter columns)")

            logger.info(f"Adding compression policy (auto-compress after {compress_after_days} days)...")
            cursor.execute("""
                SELECT add_compression_policy('booking', INTERVAL '%s days');
            """ % compress_after_days)
            logger.info("✓ Compression policy added")

            logger.info("Manually compressing all existing chunks...")
            cursor.execute("""
                SELECT compress_chunk(chunk_schema || '.' || chunk_name)
                FROM timescaledb_information.chunks
                WHERE hypertable_name = 'booking'
                AND NOT is_compressed;
            """)
            compressed_count = cursor.rowcount
            logger.info(f"✓ Compressed {compressed_count} chunks")

            logger.info("Checking compression status...")
            cursor.execute("""
                SELECT
                    chunk_name,
                    pg_size_pretty(before_compression_total_bytes) as uncompressed_size,
                    pg_size_pretty(after_compression_total_bytes) as compressed_size,
                    round(
                        100.0 * (before_compression_total_bytes - after_compression_total_bytes)
                        / NULLIF(before_compression_total_bytes, 0),
                        2
                    ) as compression_ratio_pct
                FROM timescaledb_information.chunks
                WHERE hypertable_name = 'booking'
                AND is_compressed
                ORDER BY range_start
                LIMIT 10;
            """)
            results = cursor.fetchall()

            if results:
                logger.info(f"✓ Compression statistics (showing first 10 chunks):")
                for chunk_name, uncompressed, compressed, ratio in results:
                    logger.info(f"  - {chunk_name}: {uncompressed} → {compressed} ({ratio}% reduction)")

            cursor.execute("""
                SELECT
                    COUNT(*) as total_chunks,
                    COUNT(*) FILTER (WHERE is_compressed) as compressed_chunks,
                    pg_size_pretty(SUM(before_compression_total_bytes)) as total_uncompressed,
                    pg_size_pretty(SUM(after_compression_total_bytes)) as total_compressed
                FROM timescaledb_information.chunks
                WHERE hypertable_name = 'booking';
            """)
            total_chunks, compressed, total_uncompressed, total_compressed = cursor.fetchone()
            logger.info(f"\n📊 Overall Statistics:")
            logger.info(f"  - Total chunks: {total_chunks}")
            logger.info(f"  - Compressed chunks: {compressed}")
            logger.info(f"  - Total size: {total_uncompressed} → {total_compressed}")

        conn.close()

        logger.info("=" * 70)
        logger.info("✓ Compression applied successfully!")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Compression failed: {e}", exc_info=True)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Apply compression to TimescaleDB hypertable")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5435)
    parser.add_argument("--database-name", default="pass_culture")
    parser.add_argument("--user", default="pass_culture")
    parser.add_argument("--password", default="passq")
    parser.add_argument(
        "--compress-after-days",
        type=int,
        default=7,
        help="Compress chunks older than N days (default: 7)"
    )

    args = parser.parse_args()

    apply_compression(
        host=args.host,
        port=args.port,
        database=args.database_name,
        user=args.user,
        password=args.password,
        compress_after_days=args.compress_after_days,
    )


if __name__ == "__main__":
    main()
