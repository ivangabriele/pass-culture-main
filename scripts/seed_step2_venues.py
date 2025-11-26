#!/usr/bin/env python3
"""
Step 2: Generate venues.
Loads state from step 1, generates venues, updates state file.
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


class VenueGenerator:
    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self.conn_str = f"host={host} port={port} dbname={database} user={user} password={password}"
        self.conn = None
        self.start_date = datetime(2020, 1, 1)
        self.end_date = datetime(2025, 1, 1)
        self.state = {}

    def load_state(self):
        logger.info(f"Loading state from {STATE_FILE}...")
        if not STATE_FILE.exists():
            logger.error(f"State file not found! Run step 1 first.")
            sys.exit(1)

        with open(STATE_FILE, "r") as f:
            self.state = json.load(f)

        logger.info("✓ State loaded")
        logger.info(f"  Users: {len(self.state.get('user_ids', [])):,}")
        logger.info(f"  Offerers: {len(self.state.get('offerer_ids', [])):,}")
        logger.info(f"  Offerer Addresses: {len(self.state.get('offerer_address_ids', [])):,}")

    def connect(self):
        logger.info("Connecting to database...")
        self.conn = psycopg2.connect(self.conn_str)
        self.conn.autocommit = True
        logger.info("✓ Connected")

    def generate_random_date(self, start: datetime, end: datetime) -> datetime:
        time_between = end - start
        days_between = time_between.days
        random_days = random.randint(0, days_between)
        random_date = start + timedelta(days=random_days)
        random_seconds = random.randint(0, 86400)
        return random_date + timedelta(seconds=random_seconds)

    def generate_venues(self, count: int):
        logger.info(f"Generating {count:,} venues...")

        offerer_ids = self.state["offerer_ids"]
        offerer_address_ids = self.state["offerer_address_ids"]
        num_offerers = len(offerer_ids)

        dms_token_base = random.randint(100000000, 999999999)
        all_ids = []
        batch_size = 10000

        with self.conn.cursor() as cursor:
            for batch_start in range(0, count, batch_size):
                batch_end = min(batch_start + batch_size, count)
                values = []

                for i in range(batch_start, batch_end):
                    offerer_id = offerer_ids[i % num_offerers]
                    offerer_address_id = offerer_address_ids[i % num_offerers]
                    siret = f"{20000000000000 + i:014d}"
                    values.append(
                        (
                            f"Venue {i}",
                            offerer_id,
                            f"{10000 + (i % 90000):05d}",
                            f"{i} Test Street",
                            "Paris",
                            self.generate_random_date(self.start_date, self.end_date),
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

        logger.info(f"  ✓ Created {len(all_ids):,} venues")
        return all_ids

    def save_state(self):
        logger.info(f"Saving state to {STATE_FILE}...")
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)
        logger.info("✓ State saved")

    def run(self, num_venues: int):
        logger.info("=" * 70)
        logger.info("Step 2: Generating Venues")
        logger.info("=" * 70)

        self.load_state()
        self.connect()

        self.state["venue_ids"] = self.generate_venues(num_venues)
        self.save_state()

        logger.info("=" * 70)
        logger.info("✓ Step 2 Complete!")
        logger.info("=" * 70)
        logger.info(f"Venues: {len(self.state['venue_ids']):,}")

        self.conn.close()


def main():
    parser = argparse.ArgumentParser(description="Step 2: Generate venues")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5435)
    parser.add_argument("--database", default="pass_culture")
    parser.add_argument("--user", default="pass_culture")
    parser.add_argument("--password", default="passq")
    parser.add_argument("--num-venues", type=int, default=200000)

    args = parser.parse_args()

    generator = VenueGenerator(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password,
    )

    try:
        generator.run(num_venues=args.num_venues)
    except Exception as e:
        logger.error(f"✗ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
