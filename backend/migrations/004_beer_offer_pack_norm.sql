-- Pack-size normalisation for beer offers.
-- pack_count: number of drinks in the offer (Can=1, 6 Pack=6, CTN24/Case (24)=24, ...).
-- unit_price: price / pack_count — lets cans, six-packs and cartons compare fairly.
-- Run: psql $DATABASE_URL -f migrations/004_beer_offer_pack_norm.sql

ALTER TABLE beer_merchant_offers ADD COLUMN IF NOT EXISTS pack_count INTEGER;
ALTER TABLE beer_merchant_offers ADD COLUMN IF NOT EXISTS unit_price NUMERIC(10,2);
