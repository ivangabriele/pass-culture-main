-- TimescaleDB Initialization Script
-- This script is automatically executed when the TimescaleDB container starts for the first time

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Enable utility extensions first (required by PostGIS extensions)
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Enable PostGIS extensions (same as main database)
-- Note: fuzzystrmatch must be installed before postgis_tiger_geocoder
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'TimescaleDB and all required extensions have been initialized successfully';
END
$$;
