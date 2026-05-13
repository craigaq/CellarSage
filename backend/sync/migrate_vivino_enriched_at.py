"""
One-time migration: add vivino_enriched_at column to the wines table.

Tracks when each wine was last enriched from Vivino so the weekly sync
can re-enrich stale records (older than 3 months) in addition to new ones.

Run once from backend/ directory:
    DATABASE_URL=... python -m sync.migrate_vivino_enriched_at

Re-running is harmless (IF NOT EXISTS).
"""

import logging
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("migrate_vivino_enriched_at")


def run() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL not set")
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE wines ADD COLUMN IF NOT EXISTS vivino_enriched_at TIMESTAMPTZ;"
            )
        conn.commit()
        log.info("Migration complete — vivino_enriched_at column added to wines table.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
