"""
One-time migration: add Vivino enrichment columns to the wines table.

Run once from backend/ directory before the first enrichment pass:
    DATABASE_URL=... python -m sync.migrate_vivino

All columns use IF NOT EXISTS so re-running is harmless.
"""

import logging
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("migrate_vivino")

_SQL = """
ALTER TABLE wines
  ADD COLUMN IF NOT EXISTS vivino_rating       NUMERIC(3,1),
  ADD COLUMN IF NOT EXISTS vivino_review_count  INTEGER,
  ADD COLUMN IF NOT EXISTS acidity              NUMERIC(3,1),
  ADD COLUMN IF NOT EXISTS tannin               NUMERIC(3,1),
  ADD COLUMN IF NOT EXISTS body                 NUMERIC(3,1),
  ADD COLUMN IF NOT EXISTS sweetness            NUMERIC(3,1),
  ADD COLUMN IF NOT EXISTS fruit_intensity      NUMERIC(3,1),
  ADD COLUMN IF NOT EXISTS flavor_notes         JSONB;
"""


def run() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL not set")
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(_SQL)
        conn.commit()
        log.info("Migration complete — Vivino columns added to wines table.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
