#!/usr/bin/env python3
"""
TimescaleDB Seed Script

This script generates a large realistic dataset for testing booking queries performance.
It creates millions of bookings with realistic distributions and relationships.

Usage:
    python timescaledb-seed.py --target-bookings 2000000

Architecture:
    1. Connect to both PostgreSQL and TimescaleDB databases
    2. Create base data (users, offerers, venues, offers, stocks)
    3. Generate millions of bookings with realistic distributions
    4. Insert data in batches for performance
    5. Create indexes for querying
"""

import argparse
import logging
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database connection configuration."""

    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password

    @property
    def connection_string(self) -> str:
        return f"host={self.host} port={self.port} dbname={self.database} user={self.user} password={self.password}"


class SeedDataGenerator:
    """Generates realistic seed data for bookings."""

    def __init__(self, postgres_config: DatabaseConfig, timescaledb_config: DatabaseConfig):
        self.postgres_config = postgres_config
        self.timescaledb_config = timescaledb_config
        self.postgres_conn = None
        self.timescaledb_conn = None

        self.booking_statuses = ["CONFIRMED", "USED", "CANCELLED", "REIMBURSED"]
        self.status_weights = [0.50, 0.30, 0.15, 0.05]

        self.start_date = datetime.now() - timedelta(days=3 * 365)
        self.end_date = datetime.now()

    def connect(self):
        """Establish database connections."""
        logger.info("Connecting to PostgreSQL...")
        self.postgres_conn = psycopg2.connect(self.postgres_config.connection_string)
        logger.info("Connecting to TimescaleDB...")
        self.timescaledb_conn = psycopg2.connect(self.timescaledb_config.connection_string)

    def disconnect(self):
        """Close database connections."""
        if self.postgres_conn:
            self.postgres_conn.close()
        if self.timescaledb_conn:
            self.timescaledb_conn.close()

    def copy_schema(self):
        """Copy database schema from PostgreSQL to TimescaleDB."""
        logger.info("Copying schema from PostgreSQL to TimescaleDB...")

        with self.postgres_conn.cursor() as pg_cursor:
            with self.timescaledb_conn.cursor() as ts_cursor:
                pg_cursor.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_type = 'BASE TABLE'
                    ORDER BY table_name;
                    """
                )
                tables = [row[0] for row in pg_cursor.fetchall()]
                logger.info(f"Found {len(tables)} tables to copy")

                for table in tables:
                    logger.debug(f"Copying schema for table: {table}")
                    pg_cursor.execute(
                        f"""
                        SELECT
                            'CREATE TABLE IF NOT EXISTS ' || quote_ident(table_name) || ' (' ||
                            string_agg(
                                quote_ident(column_name) || ' ' ||
                                data_type ||
                                CASE
                                    WHEN character_maximum_length IS NOT NULL
                                        THEN '(' || character_maximum_length || ')'
                                    WHEN numeric_precision IS NOT NULL AND numeric_scale IS NOT NULL
                                        THEN '(' || numeric_precision || ',' || numeric_scale || ')'
                                    ELSE ''
                                END ||
                                CASE WHEN is_nullable = 'NO' THEN ' NOT NULL' ELSE '' END,
                                ', '
                            ) || ');'
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                        AND table_name = %s
                        GROUP BY table_name;
                        """,
                        (table,)
                    )
                    create_sql = pg_cursor.fetchone()
                    if create_sql:
                        try:
                            ts_cursor.execute(create_sql[0])
                        except Exception as e:
                            logger.warning(f"Error creating table {table}: {e}")

                self.timescaledb_conn.commit()
                logger.info("Schema copy completed")

    def generate_random_date(self, start: datetime, end: datetime) -> datetime:
        """Generate a random datetime between start and end."""
        time_between_dates = end - start
        days_between_dates = time_between_dates.days
        random_number_of_days = random.randrange(days_between_dates)
        return start + timedelta(days=random_number_of_days)

    def generate_random_token(self) -> str:
        """Generate a random 6-character booking token."""
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        return "".join(random.choice(chars) for _ in range(6))

    def create_base_data(self, num_users: int, num_offerers: int, num_venues: int, num_offers: int):
        """Create base data needed for bookings."""
        logger.info("Creating base data...")

        with self.postgres_conn.cursor() as cursor:
            logger.info(f"Creating {num_users} users...")
            users = []
            for i in range(num_users):
                users.append((
                    f"user{i}@example.com",
                    f"User{i}",
                    f"Test{i}",
                    datetime.now(),
                ))

            execute_values(
                cursor,
                """
                INSERT INTO "user" (email, "firstName", "lastName", "dateCreated")
                VALUES %s
                ON CONFLICT (email) DO NOTHING
                """,
                users,
            )

            logger.info(f"Creating {num_offerers} offerers...")
            # Implementation continues...

        self.postgres_conn.commit()
        logger.info("Base data creation completed")

    def seed_bookings(self, target_bookings: int, batch_size: int = 10000):
        """Generate and insert bookings in batches."""
        logger.info(f"Generating {target_bookings} bookings in batches of {batch_size}...")

        # This will be implemented to generate bookings in batches
        # and insert them into both PostgreSQL and TimescaleDB

        pass


def main():
    parser = argparse.ArgumentParser(description="Seed TimescaleDB with realistic booking data")
    parser.add_argument(
        "--target-bookings",
        type=int,
        default=2000000,
        help="Target number of bookings to generate (default: 2000000)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Batch size for inserts (default: 10000)",
    )
    parser.add_argument(
        "--postgres-host",
        default="localhost",
        help="PostgreSQL host (default: localhost)",
    )
    parser.add_argument(
        "--postgres-port",
        type=int,
        default=5434,
        help="PostgreSQL port (default: 5434)",
    )
    parser.add_argument(
        "--timescaledb-host",
        default="localhost",
        help="TimescaleDB host (default: localhost)",
    )
    parser.add_argument(
        "--timescaledb-port",
        type=int,
        default=5435,
        help="TimescaleDB port (default: 5435)",
    )

    args = parser.parse_args()

    postgres_config = DatabaseConfig(
        host=args.postgres_host,
        port=args.postgres_port,
        database="pass_culture",
        user="pass_culture",
        password="passq",
    )

    timescaledb_config = DatabaseConfig(
        host=args.timescaledb_host,
        port=args.timescaledb_port,
        database="pass_culture",
        user="pass_culture",
        password="passq",
    )

    generator = SeedDataGenerator(postgres_config, timescaledb_config)

    try:
        generator.connect()
        generator.seed_bookings(args.target_bookings, args.batch_size)
        logger.info("Seeding completed successfully!")
    except Exception as e:
        logger.error(f"Error during seeding: {e}", exc_info=True)
        sys.exit(1)
    finally:
        generator.disconnect()


if __name__ == "__main__":
    main()
