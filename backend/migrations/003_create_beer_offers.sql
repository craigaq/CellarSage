-- Beer merchant offers — parallel to merchant_offers (wine), kept as a
-- separate table so wine queries that assume wine_id semantics are untouched.
-- Run with: psql $DATABASE_URL -f migrations/003_create_beer_offers.sql

CREATE TABLE IF NOT EXISTS beer_merchant_offers (
    id           SERIAL PRIMARY KEY,
    beer_id      INTEGER NOT NULL REFERENCES beers (id) ON DELETE CASCADE,
    retailer     TEXT    NOT NULL,
    price        NUMERIC(10, 2),
    url          TEXT,
    package_info TEXT,              -- e.g. "6 Pack", "Case of 24", "Single 375ml"
    in_stock     BOOLEAN DEFAULT TRUE,
    scraped_at   TIMESTAMP DEFAULT NOW(),

    UNIQUE (beer_id, retailer)
);

CREATE INDEX IF NOT EXISTS idx_beer_offers_beer ON beer_merchant_offers(beer_id);
CREATE INDEX IF NOT EXISTS idx_beer_offers_retailer ON beer_merchant_offers(retailer);
