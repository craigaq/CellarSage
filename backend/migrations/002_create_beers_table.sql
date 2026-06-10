-- Create beers table (parallel to wines table)
-- Run with: psql $DATABASE_URL -f migrations/002_create_beers_table.sql

CREATE TABLE IF NOT EXISTS beers (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    created_at          TIMESTAMP DEFAULT NOW(),

    -- Beer-specific technical attributes
    ibu_bitterness      FLOAT DEFAULT 20.0,           -- IBUs (0–100+)
    body                FLOAT DEFAULT 3.0,             -- 1-5 expert rating
    malt_sweetness      INTEGER DEFAULT 2,             -- 1-5 scale
    hop_intensity       INTEGER DEFAULT 3,             -- 1-10 scale
    abv_percentage      FLOAT DEFAULT 5.0,             -- Alcohol by volume
    carbonation_level   INTEGER DEFAULT 3,             -- 1-5 scale
    beer_style          VARCHAR(100) DEFAULT 'Lager',  -- IPA, Stout, Porter, etc.

    -- Indexing and metadata
    sku_id              VARCHAR(100),
    location_tag        VARCHAR(50),  -- "Local" | "National" | "International"

    CONSTRAINT beers_name_nonempty CHECK (name != '')
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_beers_style ON beers(beer_style);
CREATE INDEX IF NOT EXISTS idx_beers_location ON beers(location_tag);
CREATE INDEX IF NOT EXISTS idx_beers_name ON beers(name);

-- Add foreign key from merchant_offers to beers (future enhancement)
-- ALTER TABLE merchant_offers ADD COLUMN beer_id INTEGER REFERENCES beers(id) ON DELETE CASCADE;
