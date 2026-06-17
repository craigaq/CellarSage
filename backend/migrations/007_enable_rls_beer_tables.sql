-- Security: enable Row-Level Security on the beer tables so they aren't exposed
-- via Supabase's anon/PostgREST Data API (flagged by Supabase advisor
-- 'rls_disabled_in_public'). No policies = default-deny for anon/authenticated;
-- the backend connects as the `postgres` owner (BYPASSRLS) so it is unaffected.
-- wines/merchant_offers already had RLS enabled.
-- Run: psql $DATABASE_URL -f migrations/007_enable_rls_beer_tables.sql

ALTER TABLE public.beers                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.beer_merchant_offers ENABLE ROW LEVEL SECURITY;
