-- ── Critic score migration ────────────────────────────────────────────────────
-- Run once in the Supabase SQL Editor to add critic columns to the wines table.
-- Safe to re-run — IF NOT EXISTS prevents errors on an already-migrated DB.

ALTER TABLE wines ADD COLUMN IF NOT EXISTS critic_score     NUMERIC(4,1);
ALTER TABLE wines ADD COLUMN IF NOT EXISTS critic_source    TEXT;
ALTER TABLE wines ADD COLUMN IF NOT EXISTS community_rating NUMERIC(3,1);
ALTER TABLE wines ADD COLUMN IF NOT EXISTS match_confidence NUMERIC(5,2);

-- Optional: index for fast filtering of scored wines in the ranking query
CREATE INDEX IF NOT EXISTS wines_critic_score_idx ON wines (critic_score)
    WHERE critic_score IS NOT NULL;
