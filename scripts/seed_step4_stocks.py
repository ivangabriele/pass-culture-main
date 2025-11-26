#!/usr/bin/env python3
"""
Step 4: Generate stocks.
Loads state from previous steps, generates stocks, updates state file.
"""

import argparse
import json
import logging
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "seed_state.json"


class StockGenerator:
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
        logger.info(f"  Offers: {len(self.state.get('offer_ids', [])):,}")

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

    def generate_stocks(self, count: int):
        logger.info(f"Generating {count:,} stocks...")

        offer_ids = self.state["offer_ids"]
        all_stock_data = []
        batch_size = 10000

        with self.conn.cursor() as cursor:
            for batch_start in range(0, count, batch_size):
                batch_end = min(batch_start + batch_size, count)
                values = []

                for i in range(batch_start, batch_end):
                    offer_id = random.choice(offer_ids)
                    price = Decimal(random.choice([5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 50.0, 100.0]))
                    date_created = self.generate_random_date(self.start_date, self.end_date)
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
                    all_stock_data.append({"id": stock_id, "offerId": offer_id, "price": float(price)})

        logger.info(f"  ✓ Created {len(all_stock_data):,} stocks")
        return all_stock_data

    def save_state(self):
        logger.info(f"Saving state to {STATE_FILE}...")
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)
        logger.info("✓ State saved")

    def run(self, num_stocks: int):
        logger.info("=" * 70)
        logger.info("Step 4: Generating Stocks")
        logger.info("=" * 70)

        self.load_state()
        self.connect()

        self.state["stock_data"] = self.generate_stocks(num_stocks)
        self.save_state()

        logger.info("=" * 70)
        logger.info("✓ Step 4 Complete!")
        logger.info("=" * 70)
        logger.info(f"Stocks: {len(self.state['stock_data']):,}")

        self.conn.close()


def main():
    parser = argparse.ArgumentParser(description="Step 4: Generate stocks")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5435)
    parser.add_argument("--database", default="pass_culture")
    parser.add_argument("--user", default="pass_culture")
    parser.add_argument("--password", default="passq")
    parser.add_argument("--num-stocks", type=int, default=5000000)

    args = parser.parse_args()

    generator = StockGenerator(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password,
    )

    try:
        generator.run(num_stocks=args.num_stocks)
    except Exception as e:
        logger.error(f"✗ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
