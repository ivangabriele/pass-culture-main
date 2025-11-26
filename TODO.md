# TimescaleDB Experimentation for Booking Queries

## Problem
Some queries are currently so slow and heavy that we don't even load them by default when the end-user load the page that should list them.
They first have to set their filters and then click on "Afficher" in order to see those lists.
A good example of such a query is `get_bookings_pro` in `api/src/pcapi/routes/pro/bookings.py`.

## Context
In my last (unrelated) project, we successfully used [TimescaleDB](https://github.com/timescale/timescaledb) (by TigerData) to massively improve period-based queries.
Period-based queries seem to be a perfect match for our needs regarding bookings and offers (even in the Backoffice which is mainly used by the Support and Finance teams).

## Task
Try implementing and testing TimescaleDB with a focus on `booking` table to see if you can improve the queries related to that table in a meaningful way.
For now, focusing on `get_bookings_pro` call queries should be enough for a first experimentation.

## Requirements
- Before (without TimescaleDB) VS After analyses in terms of performance and resource usage
- Explore multiple TimescaleDB strategies from simpler to more complex ones
- Custom seed script to generate large realistic dataset (hundreds of thousands to millions of bookings)

## Decisions
- **Setup**: Separate TimescaleDB container service (for easy comparison and reproducibility)
- **Metrics**: Query execution time, Memory usage, Disk I/O, CPU usage
- **Approach**: Side-by-side comparison (keep original PostgreSQL, create TimescaleDB instance with replicated data)

## Reproducibility
All setup and testing must be reproducible via simple commands to demonstrate findings to other developers.
