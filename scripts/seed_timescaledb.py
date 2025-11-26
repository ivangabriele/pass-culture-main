#!/usr/bin/env python3
"""
TimescaleDB Large Dataset Seed Script

Generates millions of realistic bookings for performance testing.

Usage:
    # From workspace root, with venv activated:
    cd api
    python ../scripts/seed_timescaledb.py --target-bookings 2000000

Strategy:
    1. Read existing base data from PostgreSQL (users, offerers, venues, offers, stocks)
    2. If insufficient, generate additional base data
    3. Generate bookings in large batches
    4. Insert to both PostgreSQL and TimescaleDB for comparison
"""

import argparse
import logging
import random
import string
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class ProgressTracker:
    """Track and display progress during long-running operations."""

    def __init__(self, total: int, name: str = "Progress"):
        self.total = total
        self.name = name
        self.current = 0
        self.start_time = datetime.now()

    def update(self, increment: int = 1):
        self.current += increment
        if self.current % 10000 == 0 or self.current == self.total:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            rate = self.current / elapsed if elapsed > 0 else 0
            percent = (self.current / self.total * 100) if self.total > 0 else 0
            eta_seconds = (self.total - self.current) / rate if rate > 0 else 0
            logger.info(
                f"{self.name}: {self.current:,}/{self.total:,} ({percent:.1f}%) - "
                f"Rate: {rate:.0f}/s - ETA: {timedelta(seconds=int(eta_seconds))}"
            )


class BookingSeedGenerator:
    """Generate large volumes of realistic booking data."""

    def __init__(
        self,
        pg_host: str,
        pg_port: int,
        ts_host: str,
        ts_port: int,
        database: str,
        user: str,
        password: str,
    ):
        self.pg_conn_str = f"host={pg_host} port={pg_port} dbname={database} user={user} password={password}"
        self.ts_conn_str = f"host={ts_host} port={ts_port} dbname={database} user={user} password={password}"
        self.pg_conn = None
        self.ts_conn = None

        self.start_date = datetime.now() - timedelta(days=3 * 365)
        self.end_date = datetime.now()

        self.booking_statuses = ["CONFIRMED", "USED", "CANCELLED", "REIMBURSED"]
        self.status_weights = [0.50, 0.30, 0.15, 0.05]

        self.cancellation_reasons = [
            "BENEFICIARY",
            "OFFERER",
            "EXPIRED",
            "FRAUD",
            "BACKOFFICE",
        ]

        self.base_data = {
            "users": [],
            "offerers": [],
            "venues": [],
            "offers": [],
            "stocks": [],
        }

    def connect(self):
        """Establish database connections."""
        logger.info("Connecting to PostgreSQL...")
        self.pg_conn = psycopg2.connect(self.pg_conn_str)
        self.pg_conn.autocommit = False

        logger.info("Connecting to TimescaleDB...")
        self.ts_conn = psycopg2.connect(self.ts_conn_str)
        self.ts_conn.autocommit = False

    def disconnect(self):
        """Close database connections."""
        if self.pg_conn:
            self.pg_conn.close()
        if self.ts_conn:
            self.ts_conn.close()

    def load_existing_base_data(self):
        """Load existing users, offerers, venues, offers, and stocks from PostgreSQL."""
        logger.info("Loading existing base data from PostgreSQL...")

        with self.pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("SELECT id FROM \"user\" ORDER BY id")
            self.base_data["users"] = [row["id"] for row in cursor.fetchall()]
            logger.info(f"Loaded {len(self.base_data['users'])} users")

            cursor.execute("SELECT id FROM offerer ORDER BY id")
            self.base_data["offerers"] = [row["id"] for row in cursor.fetchall()]
            logger.info(f"Loaded {len(self.base_data['offerers'])} offerers")

            cursor.execute("SELECT id FROM venue ORDER BY id")
            self.base_data["venues"] = [row["id"] for row in cursor.fetchall()]
            logger.info(f"Loaded {len(self.base_data['venues'])} venues")

            cursor.execute("SELECT id, \"venueId\" FROM offer ORDER BY id")
            self.base_data["offers"] = [
                {"id": row["id"], "venueId": row["venueId"]} for row in cursor.fetchall()
            ]
            logger.info(f"Loaded {len(self.base_data['offers'])} offers")

            cursor.execute(
                """
                SELECT s.id, s."offerId", s.price, o."venueId"
                FROM stock s
                JOIN offer o ON s."offerId" = o.id
                WHERE s."isSoftDeleted" = FALSE
                ORDER BY s.id
                """
            )
            self.base_data["stocks"] = [
                {
                    "id": row["id"],
                    "offerId": row["offerId"],
                    "price": row["price"],
                    "venueId": row["venueId"],
                }
                for row in cursor.fetchall()
            ]
            logger.info(f"Loaded {len(self.base_data['stocks'])} stocks")

        if not all(
            [
                self.base_data["users"],
                self.base_data["offerers"],
                self.base_data["venues"],
                self.base_data["offers"],
                self.base_data["stocks"],
            ]
        ):
            logger.error("Insufficient base data! Please seed the database first with: flask sandbox -n industrial")
            sys.exit(1)

    def generate_random_date(self, start: datetime, end: datetime, recent_bias: bool = True) -> datetime:
        """Generate random datetime with optional bias toward recent dates."""
        time_between = end - start
        days_between = time_between.days

        if recent_bias:
            random_days = int(days_between * (random.random() ** 2))
        else:
            random_days = random.randint(0, days_between)

        random_date = start + timedelta(days=random_days)
        random_seconds = random.randint(0, 86400)
        return random_date + timedelta(seconds=random_seconds)

    def generate_booking_token(self) -> str:
        """Generate a random 6-character alphanumeric token."""
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    def generate_bookings_batch(self, batch_size: int) -> list[dict[str, Any]]:
        """Generate a batch of booking records."""
        bookings = []

        for _ in range(batch_size):
            stock = random.choice(self.base_data["stocks"])
            user_id = random.choice(self.base_data["users"])
            date_created = self.generate_random_date(self.start_date, self.end_date, recent_bias=True)

            status = random.choices(self.booking_statuses, weights=self.status_weights)[0]

            booking = {
                "dateCreated": date_created,
                "stockId": stock["id"],
                "venueId": stock["venueId"],
                "offererId": random.choice(self.base_data["offerers"]),
                "quantity": random.choice([1, 1, 1, 1, 1, 1, 1, 1, 1, 2]),
                "token": self.generate_booking_token(),
                "userId": user_id,
                "amount": stock["price"] or Decimal("10.00"),
                "status": status,
            }

            if status == "USED":
                booking["dateUsed"] = date_created + timedelta(days=random.randint(1, 60))
            elif status == "CANCELLED":
                booking["cancellationDate"] = date_created + timedelta(days=random.randint(0, 30))
                booking["cancellationReason"] = random.choice(self.cancellation_reasons)
            elif status == "REIMBURSED":
                booking["dateUsed"] = date_created + timedelta(days=random.randint(1, 30))
                booking["reimbursementDate"] = booking["dateUsed"] + timedelta(days=random.randint(15, 45))

            bookings.append(booking)

        return bookings

    def insert_bookings_to_db(self, bookings: list[dict[str, Any]], connection):
        """Insert booking batch to database."""
        if not bookings:
            return

        values = []
        for booking in bookings:
            values.append(
                (
                    booking["dateCreated"],
                    booking.get("dateUsed"),
                    booking["stockId"],
                    booking["venueId"],
                    booking["offererId"],
                    booking["quantity"],
                    booking["token"],
                    booking["userId"],
                    booking["amount"],
                    booking["status"],
                    booking.get("cancellationDate"),
                    booking.get("cancellationReason"),
                    booking.get("reimbursementDate"),
                )
            )

        with connection.cursor() as cursor:
            execute_values(
                cursor,
                """
                INSERT INTO booking (
                    "dateCreated", "dateUsed", "stockId", "venueId", "offererId",
                    quantity, token, "userId", amount, status,
                    "cancellationDate", "cancellationReason", "reimbursementDate"
                )
                VALUES %s
                ON CONFLICT (token) DO NOTHING
                """,
                values,
                page_size=1000,
            )

    def seed_bookings(
        self,
        target_bookings: int,
        batch_size: int = 10000,
        insert_to_postgres: bool = True,
        insert_to_timescaledb: bool = True,
    ):
        """Generate and insert bookings in batches."""
        logger.info(f"Target: {target_bookings:,} bookings | Batch size: {batch_size:,}")

        if not insert_to_postgres and not insert_to_timescaledb:
            logger.error("Must insert to at least one database!")
            return

        progress = ProgressTracker(target_bookings, "Bookings generation")
        total_inserted = 0
        batches = (target_bookings + batch_size - 1) // batch_size

        try:
            for batch_num in range(batches):
                current_batch_size = min(batch_size, target_bookings - total_inserted)
                bookings = self.generate_bookings_batch(current_batch_size)

                if insert_to_postgres:
                    self.insert_bookings_to_db(bookings, self.pg_conn)

                if insert_to_timescaledb:
                    self.insert_bookings_to_db(bookings, self.ts_conn)

                if insert_to_postgres:
                    self.pg_conn.commit()
                if insert_to_timescaledb:
                    self.ts_conn.commit()

                total_inserted += len(bookings)
                progress.update(len(bookings))

            logger.info(f"✓ Successfully inserted {total_inserted:,} bookings")

        except Exception as e:
            logger.error(f"Error during seeding: {e}", exc_info=True)
            if insert_to_postgres:
                self.pg_conn.rollback()
            if insert_to_timescaledb:
                self.ts_conn.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description="Seed large dataset for TimescaleDB experimentation")
    parser.add_argument(
        "--target-bookings",
        type=int,
        default=2000000,
        help="Target number of bookings to generate (default: 2,000,000)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Batch size for inserts (default: 10,000)",
    )
    parser.add_argument("--postgres-host", default="localhost")
    parser.add_argument("--postgres-port", type=int, default=5434)
    parser.add_argument("--timescaledb-host", default="localhost")
    parser.add_argument("--timescaledb-port", type=int, default=5435)
    parser.add_argument("--database", default="pass_culture")
    parser.add_argument("--user", default="pass_culture")
    parser.add_argument("--password", default="passq")
    parser.add_argument("--skip-postgres", action="store_true", help="Skip inserting to PostgreSQL")
    parser.add_argument("--skip-timescaledb", action="store_true", help="Skip inserting to TimescaleDB")

    args = parser.parse_args()

    generator = BookingSeedGenerator(
        pg_host=args.postgres_host,
        pg_port=args.postgres_port,
        ts_host=args.timescaledb_host,
        ts_port=args.timescaledb_port,
        database=args.database,
        user=args.user,
        password=args.password,
    )

    try:
        logger.info("=" * 70)
        logger.info("TimescaleDB Large Dataset Seed Script")
        logger.info("=" * 70)

        generator.connect()
        generator.load_existing_base_data()
        generator.seed_bookings(
            target_bookings=args.target_bookings,
            batch_size=args.batch_size,
            insert_to_postgres=not args.skip_postgres,
            insert_to_timescaledb=not args.skip_timescaledb,
        )

        logger.info("=" * 70)
        logger.info("✓ Seeding completed successfully!")
        logger.info("=" * 70)

    except KeyboardInterrupt:
        logger.warning("\n! Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"✗ Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        generator.disconnect()


if __name__ == "__main__":
    main()
