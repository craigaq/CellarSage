-- Australian state of each beer's brewery, for geo-personalised "Local Hero"
-- (beer analogue of wines.state + producer_state.json). NULL = overseas/unknown.
-- Run: psql $DATABASE_URL -f migrations/005_beer_brewery_state.sql

ALTER TABLE beers ADD COLUMN IF NOT EXISTS brewery_state TEXT;
CREATE INDEX IF NOT EXISTS idx_beers_brewery_state ON beers(brewery_state);
