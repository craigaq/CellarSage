-- Untappd ratings enrichment for beers (beer analogue of wines.vivino_rating).
-- Run: psql $DATABASE_URL -f migrations/006_beer_untappd_ratings.sql

ALTER TABLE beers ADD COLUMN IF NOT EXISTS untappd_rating       NUMERIC(3,2);
ALTER TABLE beers ADD COLUMN IF NOT EXISTS untappd_url          TEXT;
ALTER TABLE beers ADD COLUMN IF NOT EXISTS untappd_enriched_at  TIMESTAMP;
-- Real per-beer IBU from Untappd (overrides the style-inferred estimate when present).
ALTER TABLE beers ADD COLUMN IF NOT EXISTS untappd_ibu          INTEGER;
