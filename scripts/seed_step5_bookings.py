#!/usr/bin/env python3
"""
Step 5: Generate bookings.
Loads state from previous steps, generates bookings in batches, updates state file.
Can be run multiple times to generate bookings in consecutive batches.
"""

import argparse
import json
import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "seed_state.json"


class BookingGenerator:
    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self.conn_str = f"host={host} port={port} dbname={database} user={user} password={password}"
        self.conn = None
        self.start_date = datetime(2020, 1, 1)
        self.end_date = datetime(2025, 1, 1)
        self.state = {}

    def load_state(self):
        logger.info(f"Loading state from {STATE_FILE}...")
        if not STATE_FILE.exists():
            logger.error(f"State file not found! Run previous steps first.")
            sys.exit(1)

        with open(STATE_FILE, "r") as f:
            self.state = json.load(f)

        logger.info("✓ State loaded")
        logger.info(f"  Users: {len(self.state.get('user_ids', [])):,}")
        logger.info(f"  Stock data: {len(self.state.get('stock_data', [])):,}")

        existing_bookings = self.state.get('booking_ids', [])
        if existing_bookings:
            logger.info(f"  Existing bookings: {len(existing_bookings):,}")

    def connect(self):
        logger.info("Connecting to database...")
        self.conn = psycopg2.connect(self.conn_str)
        self.conn.autocommit = True
        logger.info("✓ Connected")

    def generate_random_date_recent_bias(self, start: datetime, end: datetime) -> datetime:
        """Generate random date with quadratic bias toward recent dates."""
        time_between = end - start
        days_between = time_between.days
        random_factor = random.random() ** 2
        random_days = int(days_between * random_factor)
        random_date = end - timedelta(days=random_days)
        random_seconds = random.randint(0, 86400)
        return random_date + timedelta(seconds=random_seconds)

    def generate_random_date(self, start: datetime, end: datetime) -> datetime:
        time_between = end - start
        days_between = time_between.days
        random_days = random.randint(0, days_between)
        random_date = start + timedelta(days=random_days)
        random_seconds = random.randint(0, 86400)
        return random_date + timedelta(seconds=random_seconds)

    def generate_booking_token(self, booking_number: int) -> str:
        """Generate a unique 6-character token for a booking based on its number."""
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        base = len(chars)
        token = ""
        num = booking_number
        for _ in range(6):
            token = chars[num % base] + token
            num //= base
        return token

    def generate_bookings(self, count: int, batch_size: int = 10000):
        logger.info(f"Generating {count:,} bookings in batches of {batch_size:,}...")

        user_ids = self.state["user_ids"]
        deposit_ids = self.state["deposit_ids"]
        stock_data = self.state["stock_data"]
        venue_ids = self.state["venue_ids"]
        offerer_ids = self.state["offerer_ids"]

        if not stock_data:
            logger.error("No stock data found in state! Run step 4 first.")
            sys.exit(1)

        all_ids = self.state.get("booking_ids", [])
        initial_count = len(all_ids)
        booking_counter = initial_count

        status_distribution = [
            ("CONFIRMED", 50),
            ("USED", 30),
            ("CANCELLED", 15),
            ("REIMBURSED", 5),
        ]
        statuses = []
        for status, percentage in status_distribution:
            statuses.extend([status] * percentage)

        with self.conn.cursor() as cursor:
            for batch_start in range(0, count, batch_size):
                batch_end = min(batch_start + batch_size, count)
                values = []

                for i in range(batch_start, batch_end):
                    stock = random.choice(stock_data)
                    user_id = random.choice(user_ids)
                    deposit_id = random.choice(deposit_ids)
                    venue_id = random.choice(venue_ids)
                    offerer_id = random.choice(offerer_ids)
                    status = random.choice(statuses)
                    token = self.generate_booking_token(booking_counter)
                    booking_counter += 1

                    date_created = self.generate_random_date_recent_bias(
                        self.start_date, self.end_date
                    )

                    cancellation_limit_date = date_created + timedelta(days=random.randint(1, 30))

                    date_used = None
                    cancellation_date = None
                    reimbursement_date = None

                    if status == "USED":
                        date_used = date_created + timedelta(
                            days=random.randint(0, 30)
                        )
                    elif status == "CANCELLED":
                        cancellation_date = date_created + timedelta(
                            days=random.randint(0, 7)
                        )
                    elif status == "REIMBURSED":
                        date_used = date_created + timedelta(
                            days=random.randint(0, 30)
                        )
                        reimbursement_date = date_used + timedelta(
                            days=random.randint(7, 60)
                        )

                    values.append(
                        (
                            stock["id"],
                            user_id,
                            1,
                            stock["price"],
                            date_created,
                            status,
                            offerer_id,
                            venue_id,
                            token,
                            cancellation_limit_date,
                            date_used,
                            cancellation_date,
                            reimbursement_date,
                            deposit_id,
                        )
                    )

                execute_values(
                    cursor,
                    """
                    INSERT INTO booking (
                        "stockId", "userId", quantity, amount, "dateCreated",
                        status, "offererId", "venueId", token, "cancellationLimitDate",
                        "dateUsed", "cancellationDate", "reimbursementDate", "depositId"
                    )
                    VALUES %s
                    RETURNING id
                    """,
                    values,
                    page_size=len(values),
                )
                batch_ids = [row[0] for row in cursor.fetchall()]
                all_ids.extend(batch_ids)

                logger.info(
                    f"  ✓ Batch {batch_start // batch_size + 1}/{(count + batch_size - 1) // batch_size}: "
                    f"Created {len(batch_ids):,} bookings (total: {len(all_ids):,})"
                )

        new_bookings = len(all_ids) - initial_count
        logger.info(f"  ✓ Created {new_bookings:,} new bookings (total: {len(all_ids):,})")
        return all_ids

    def save_state(self):
        logger.info(f"Saving state to {STATE_FILE}...")
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)
        logger.info("✓ State saved")

    def run(self, num_bookings: int, batch_size: int = 10000):
        logger.info("=" * 70)
        logger.info("Step 5: Generating Bookings")
        logger.info("=" * 70)

        self.load_state()
        self.connect()

        self.state["booking_ids"] = self.generate_bookings(num_bookings, batch_size)
        self.save_state()

        logger.info("=" * 70)
        logger.info("✓ Step 5 Complete!")
        logger.info("=" * 70)
        logger.info(f"Total Bookings: {len(self.state['booking_ids']):,}")

        self.conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Step 5: Generate bookings (can be run in consecutive batches)"
    )
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5435)
    parser.add_argument("--database", default="pass_culture")
    parser.add_argument("--user", default="pass_culture")
    parser.add_argument("--password", default="passq")
    parser.add_argument(
        "--num-bookings",
        type=int,
        default=1000000,
        help="Number of bookings to generate in this run",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Number of bookings per database batch",
    )

    args = parser.parse_args()

    generator = BookingGenerator(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password,
    )

    try:
        generator.run(num_bookings=args.num_bookings, batch_size=args.batch_size)
    except Exception as e:
        logger.error(f"✗ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
