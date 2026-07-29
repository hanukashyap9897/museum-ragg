-- ====================================================================
-- Migration: MongoDB museum_data collection -> Postgres museum_units table
-- Assam Regiment Digital Museum API
-- ====================================================================

-- Mirrors the exact shape of the old Mongo document:
--   { "_id": "<unit_id>", "data": {...UnitData...}, "updatedAt": <epoch_ms> }
--
-- id         <- Mongo's _id (e.g. "ARC", "AR", "AS", "RR", "TA")
-- data       <- Mongo's "data" field (the full UnitData JSON blob), stored as JSONB
-- updated_at <- Mongo's "updatedAt" (epoch milliseconds), kept as BIGINT to match exactly

CREATE TABLE IF NOT EXISTS museum_units (
    id VARCHAR PRIMARY KEY,
    data JSONB NOT NULL,
    updated_at BIGINT NOT NULL
);

-- Optional: speeds up any future queries that filter/search inside the JSON
CREATE INDEX IF NOT EXISTS museum_units_data_gin_idx
ON museum_units USING gin (data);