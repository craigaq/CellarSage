-- Run once in Supabase SQL Editor (or any PostgreSQL client) to initialise the sync tables.

CREATE TABLE IF NOT EXISTS wines (
    id         SERIAL PRIMARY KEY,
    name       TEXT    NOT NULL,
    vintage    INTEGER,
    region     TEXT,
    varietal   TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (name, vintage)
);

CREATE TABLE IF NOT EXISTS merchant_offers (
    id           SERIAL PRIMARY KEY,
    wine_id      INTEGER REFERENCES wines (id) ON DELETE CASCADE,
    retailer     TEXT    NOT NULL,
    price        NUMERIC(10, 2),
    url          TEXT,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (wine_id, retailer)
);

-- Index for fast name+vintage lookups during upsert
CREATE INDEX IF NOT EXISTS idx_wines_name_vintage ON wines (name, vintage);
