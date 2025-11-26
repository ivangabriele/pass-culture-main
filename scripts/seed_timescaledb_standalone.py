#!/usr/bin/env python3
"""
TimescaleDB Standalone Seed Script

Generates a complete self-sufficient dataset for TimescaleDB performance testing.
Creates all base entities (users, offerers, venues, offers, stocks) and millions of bookings.

Production-scale defaults:
- 2M users and deposits
- 100K offerers and offerer_addresses
- 200K venues
- 2M offers
- 5M stocks
- 10M bookings
- 5-year date range

Usage:
    cd api
    python ../scripts/seed_timescaledb_standalone.py

This script is fully self-contained and does not depend on PostgreSQL data.
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


class StandaloneBookingSeedGenerator:
    """Generate complete self-sufficient booking dataset for TimescaleDB."""

    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self.conn_str = f"host={host} port={port} dbname={database} user={user} password={password}"
        self.conn = None

        self.start_date = datetime.now() - timedelta(days=5 * 365)
        self.end_date = datetime.now()

        self.booking_statuses = ["CONFIRMED", "USED", "CANCELLED", "REIMBURSED"]
        self.status_weights = [0.50, 0.30, 0.15, 0.05]

        self.cancellation_reasons = ["BENEFICIARY", "OFFERER", "EXPIRED", "FRAUD", "BACKOFFICE"]

        self.base_data = {
            "user_ids": [],
            "offerer_ids": [],
            "address_ids": [],
            "offerer_address_ids": [],
            "venue_ids": [],
            "offer_ids": [],
            "stock_data": [],
            "deposit_ids": [],
        }

    def connect(self):
        """Establish database connection."""
        logger.info("Connecting to TimescaleDB...")
        self.conn = psycopg2.connect(self.conn_str)
        self.conn.autocommit = False

    def disconnect(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def generate_base_entities(
        self, num_users: int = 1000, num_offerers: int = 200, num_venues: int = 500, num_offers: int = 2000, num_stocks: int = 6000
    ):
        """Generate all base entities needed for bookings."""
        logger.info("=" * 70)
        logger.info("Generating Base Entities")
        logger.info("=" * 70)

        try:
            self._generate_users(num_users)
            self._generate_deposits(num_users)
            self._generate_offerers(num_offerers)
            self._generate_addresses(num_offerers)
            self._generate_offerer_addresses(num_offerers)
            self._generate_venues(num_venues, num_offerers)
            self._generate_offers(num_offers, len(self.base_data["venue_ids"]))
            self._generate_stocks(num_stocks)
            self._generate_user_offerers(num_users, num_offerers)

            self.conn.commit()
            logger.info("✓ Base entities created successfully")

        except Exception as e:
            logger.error(f"Error generating base entities: {e}", exc_info=True)
            self.conn.rollback()
            raise

    def _generate_users(self, count: int):
        """Generate user records."""
        logger.info(f"Generating {count:,} users...")

        all_ids = []
        batch_size = 10000

        with self.conn.cursor() as cursor:
            for batch_start in range(0, count, batch_size):
                batch_end = min(batch_start + batch_size, count)
                values = []

                for i in range(batch_start, batch_end):
                    values.append(
                        (
                            f"user{i}@example.com",
                            f"User{i}",
                            f"Test{i}",
                            self.generate_random_date(self.start_date, self.end_date, recent_bias=False),
                            False,
                            True,
                        )
                    )

                execute_values(
                    cursor,
                    """
                    INSERT INTO "user" (
                        email, "firstName", "lastName", "dateCreated", "isEmailValidated", "hasSeenProTutorials"
                    )
                    VALUES %s
                    ON CONFLICT (email) DO NOTHING
                    RETURNING id
                    """,
                    values,
                    page_size=len(values),
                )
                all_ids.extend([row[0] for row in cursor.fetchall()])

        self.base_data["user_ids"] = all_ids
        logger.info(f"  ✓ Created {len(self.base_data['user_ids']):,} users")

    def _generate_deposits(self, count: int):
        """Generate deposit records for users with sufficient balance."""
        logger.info(f"Generating {count:,} deposits...")

        all_ids = []
        batch_size = 10000
        user_ids = self.base_data["user_ids"]

        with self.conn.cursor() as cursor:
            for batch_start in range(0, len(user_ids), batch_size):
                batch_end = min(batch_start + batch_size, len(user_ids))
                values = []

                for i in range(batch_start, batch_end):
                    user_id = user_ids[i]
                    values.append(
                        (
                            user_id,
                            Decimal("5000.00"),
                            self.generate_random_date(self.start_date, self.end_date, recent_bias=False),
                            "age-18",
                            1,
                        )
                    )

                execute_values(
                    cursor,
                    """
                    INSERT INTO deposit (
                        "userId", amount, "dateCreated", source, version
                    )
                    VALUES %s
                    RETURNING id
                    """,
                    values,
                    page_size=len(values),
                )
                all_ids.extend([row[0] for row in cursor.fetchall()])

        self.base_data["deposit_ids"] = all_ids
        logger.info(f"  ✓ Created {len(self.base_data['deposit_ids']):,} deposits")

    def _generate_offerers(self, count: int):
        """Generate offerer records."""
        logger.info(f"Generating {count:,} offerers...")

        all_ids = []
        batch_size = 10000

        with self.conn.cursor() as cursor:
            for batch_start in range(0, count, batch_size):
                batch_end = min(batch_start + batch_size, count)
                values = []

                for i in range(batch_start, batch_end):
                    siren = f"{100000000 + i:09d}"
                    values.append(
                        (
                            siren,
                            f"Offerer {i}",
                            self.generate_random_date(self.start_date, self.end_date, recent_bias=False),
                            True,
                            "VALIDATED",
                        )
                    )

                execute_values(
                    cursor,
                    """
                    INSERT INTO offerer (
                        siren, name, "dateCreated", "isActive", "validationStatus"
                    )
                    VALUES %s
                    ON CONFLICT (siren) DO NOTHING
                    RETURNING id
                    """,
                    values,
                    page_size=len(values),
                )
                all_ids.extend([row[0] for row in cursor.fetchall()])

        self.base_data["offerer_ids"] = all_ids
        logger.info(f"  ✓ Created {len(self.base_data['offerer_ids']):,} offerers")

    def _generate_addresses(self, count: int):
        """Generate address records for offerers."""
        logger.info(f"Generating {count:,} addresses...")

        all_ids = []
        batch_size = 10000

        with self.conn.cursor() as cursor:
            for batch_start in range(0, count, batch_size):
                batch_end = min(batch_start + batch_size, count)
                values = []

                for i in range(batch_start, batch_end):
                    values.append(
                        (
                            f"{i} Test Street",
                            f"{(i % 90000 + 10000):05d}",
                            "Paris",
                            48.8566 + (i % 100) * 0.001,
                            2.3522 + (i % 100) * 0.001,
                            "75",
                        )
                    )

                execute_values(
                    cursor,
                    """
                    INSERT INTO address (
                        street, "postalCode", city, latitude, longitude, "departmentCode"
                    )
                    VALUES %s
                    RETURNING id
                    """,
                    values,
                    page_size=len(values),
                )
                all_ids.extend([row[0] for row in cursor.fetchall()])

        self.base_data["address_ids"] = all_ids
        logger.info(f"  ✓ Created {len(self.base_data['address_ids']):,} addresses")

    def _generate_offerer_addresses(self, count: int):
        """Generate offerer_address records linking offerers to addresses."""
        logger.info(f"Generating {count:,} offerer_addresses...")

        all_ids = []
        batch_size = 10000

        with self.conn.cursor() as cursor:
            for batch_start in range(0, count, batch_size):
                batch_end = min(batch_start + batch_size, count)
                values = []

                for i in range(batch_start, batch_end):
                    address_id = self.base_data["address_ids"][i]
                    offerer_id = self.base_data["offerer_ids"][i]
                    values.append((address_id, offerer_id))

                execute_values(
                    cursor,
                    """
                    INSERT INTO offerer_address (
                        "addressId", "offererId"
                    )
                    VALUES %s
                    RETURNING id
                    """,
                    values,
                    page_size=len(values),
                )
                all_ids.extend([row[0] for row in cursor.fetchall()])

        self.base_data["offerer_address_ids"] = all_ids
        logger.info(f"  ✓ Created {len(self.base_data['offerer_address_ids']):,} offerer_addresses")

    def _generate_venues(self, count: int, num_offerers: int):
        """Generate venue records."""
        logger.info(f"Generating {count:,} venues...")

        dms_token_base = random.randint(100000000, 999999999)
        all_ids = []
        batch_size = 10000

        with self.conn.cursor() as cursor:
            for batch_start in range(0, count, batch_size):
                batch_end = min(batch_start + batch_size, count)
                values = []

                for i in range(batch_start, batch_end):
                    offerer_id = self.base_data["offerer_ids"][i % num_offerers]
                    offerer_address_id = self.base_data["offerer_address_ids"][i % num_offerers]
                    siret = f"{20000000000000 + i:014d}"
                    values.append(
                        (
                            f"Venue {i}",
                            offerer_id,
                            f"{10000 + i:05d}",
                            f"{i} Test Street",
                            "Paris",
                            self.generate_random_date(self.start_date, self.end_date, recent_bias=False),
                            0,
                            f"Venue {i}",
                            True,
                            "OTHER",
                            f"DMS{dms_token_base + i}",
                            offerer_address_id,
                            True,
                            siret,
                        )
                    )

                execute_values(
                    cursor,
                    """
                    INSERT INTO venue (
                        name, "managingOffererId", "postalCode", address, city, "dateCreated",
                        "thumbCount", "publicName", "isPermanent", "venueTypeCode", "dmsToken",
                        "offererAddressId", "isOpenToPublic", siret
                    )
                    VALUES %s
                    RETURNING id
                    """,
                    values,
                    page_size=len(values),
                )
                all_ids.extend([row[0] for row in cursor.fetchall()])

        self.base_data["venue_ids"] = all_ids
        logger.info(f"  ✓ Created {len(self.base_data['venue_ids']):,} venues")

    def _generate_offers(self, count: int, num_venues: int):
        """Generate offer records."""
        logger.info(f"Generating {count:,} offers...")

        all_ids = []
        batch_size = 10000

        with self.conn.cursor() as cursor:
            for batch_start in range(0, count, batch_size):
                batch_end = min(batch_start + batch_size, count)
                values = []

                for i in range(batch_start, batch_end):
                    venue_id = self.base_data["venue_ids"][i % num_venues]
                    values.append(
                        (
                            f"Offer {i}",
                            venue_id,
                            self.generate_random_date(self.start_date, self.end_date, recent_bias=False),
                            False,
                            "SUPPORT_PHYSIQUE_FILM",
                        )
                    )

                execute_values(
                    cursor,
                    """
                    INSERT INTO offer (
                        name, "venueId", "dateCreated", "isNational", "subcategoryId"
                    )
                    VALUES %s
                    RETURNING id
                    """,
                    values,
                    page_size=len(values),
                )
                all_ids.extend([row[0] for row in cursor.fetchall()])

        self.base_data["offer_ids"] = all_ids
        logger.info(f"  ✓ Created {len(self.base_data['offer_ids']):,} offers")

    def _generate_stocks(self, count: int):
        """Generate stock records."""
        logger.info(f"Generating {count:,} stocks...")

        all_stock_data = []
        batch_size = 10000

        with self.conn.cursor() as cursor:
            for batch_start in range(0, count, batch_size):
                batch_end = min(batch_start + batch_size, count)
                values = []

                for i in range(batch_start, batch_end):
                    offer_id = random.choice(self.base_data["offer_ids"])
                    price = Decimal(random.choice([5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 50.0, 100.0]))
                    date_created = self.generate_random_date(self.start_date, self.end_date, recent_bias=False)
                    values.append(
                        (
                            offer_id,
                            price,
                            date_created,
                            False,
                            date_created,
                        )
                    )

                execute_values(
                    cursor,
                    """
                    INSERT INTO stock (
                        "offerId", price, "dateCreated", "isSoftDeleted", "dateModified"
                    )
                    VALUES %s
                    RETURNING id, "offerId", price
                    """,
                    values,
                    page_size=len(values),
                )

                for row in cursor.fetchall():
                    stock_id, offer_id, price = row
                    all_stock_data.append({"id": stock_id, "offerId": offer_id, "price": price})

        self.base_data["stock_data"] = all_stock_data
        logger.info(f"  ✓ Created {len(self.base_data['stock_data']):,} stocks")

    def _generate_user_offerers(self, num_users: int, num_offerers: int):
        """Generate user_offerer relationships for benchmark queries."""
        logger.info(f"Generating user_offerer relationships...")

        values = []
        num_relationships = min(num_users, num_offerers * 5)

        for i in range(num_relationships):
            user_id = self.base_data["user_ids"][i % len(self.base_data["user_ids"])]
            offerer_id = self.base_data["offerer_ids"][i % len(self.base_data["offerer_ids"])]
            values.append((user_id, offerer_id, "VALIDATED"))

        with self.conn.cursor() as cursor:
            execute_values(
                cursor,
                """
                INSERT INTO user_offerer (
                    "userId", "offererId", "validationStatus"
                )
                VALUES %s
                ON CONFLICT ("userId", "offererId") DO NOTHING
                """,
                values,
            )

        logger.info(f"  ✓ Created user_offerer relationships")

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
            stock = random.choice(self.base_data["stock_data"])
            user_id = random.choice(self.base_data["user_ids"])
            date_created = self.generate_random_date(self.start_date, self.end_date, recent_bias=True)

            status = random.choices(self.booking_statuses, weights=self.status_weights)[0]

            venue_id = random.choice(self.base_data["venue_ids"])
            offerer_id = random.choice(self.base_data["offerer_ids"])

            booking = {
                "dateCreated": date_created,
                "stockId": stock["id"],
                "venueId": venue_id,
                "offererId": offerer_id,
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

    def insert_bookings_batch(self, bookings: list[dict[str, Any]]):
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

        with self.conn.cursor() as cursor:
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
            )

    def seed_bookings(self, target_bookings: int, batch_size: int = 10000):
        """Generate and insert bookings in batches."""
        logger.info("=" * 70)
        logger.info(f"Generating Bookings")
        logger.info(f"Target: {target_bookings:,} | Batch size: {batch_size:,}")
        logger.info("=" * 70)

        progress = ProgressTracker(target_bookings, "Bookings")
        total_inserted = 0
        batches = (target_bookings + batch_size - 1) // batch_size

        try:
            for batch_num in range(batches):
                current_batch_size = min(batch_size, target_bookings - total_inserted)
                bookings = self.generate_bookings_batch(current_batch_size)

                self.insert_bookings_batch(bookings)
                self.conn.commit()

                total_inserted += len(bookings)
                progress.update(len(bookings))

            logger.info(f"✓ Successfully inserted {total_inserted:,} bookings")

        except Exception as e:
            logger.error(f"Error during seeding: {e}", exc_info=True)
            self.conn.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description="Standalone seed for TimescaleDB experimentation")
    parser.add_argument(
        "--target-bookings",
        type=int,
        default=10000000,
        help="Target number of bookings to generate (default: 10,000,000)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Batch size for inserts (default: 10,000)",
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5435)
    parser.add_argument("--database", default="pass_culture")
    parser.add_argument("--user", default="pass_culture")
    parser.add_argument("--password", default="passq")
    parser.add_argument("--num-users", type=int, default=2000000, help="Number of users to generate (default: 2,000,000)")
    parser.add_argument(
        "--num-offerers", type=int, default=100000, help="Number of offerers to generate (default: 100,000)"
    )
    parser.add_argument("--num-venues", type=int, default=200000, help="Number of venues to generate (default: 200,000)")
    parser.add_argument("--num-offers", type=int, default=2000000, help="Number of offers to generate (default: 2,000,000)")
    parser.add_argument("--num-stocks", type=int, default=5000000, help="Number of stocks to generate (default: 5,000,000)")

    args = parser.parse_args()

    generator = StandaloneBookingSeedGenerator(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password,
    )

    try:
        logger.info("=" * 70)
        logger.info("TimescaleDB Standalone Seed Script")
        logger.info("=" * 70)

        generator.connect()
        generator.generate_base_entities(
            num_users=args.num_users,
            num_offerers=args.num_offerers,
            num_venues=args.num_venues,
            num_offers=args.num_offers,
            num_stocks=args.num_stocks,
        )
        generator.seed_bookings(target_bookings=args.target_bookings, batch_size=args.batch_size)

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
