"""
One-time migration: add vivino_url column to the wines table.

Stores the direct Vivino wine page URL captured during enrichment,
enabling deep links from the app back to Vivino ("Good Citizen" strategy).

Run once from backend/ directory:
    DATABASE_URL=... python -m sync.migrate_vivino_url

Re-running is harmless (IF NOT EXISTS).
"""

import logging
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("migrate_vivino_url")


def run() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL not set")
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE wines ADD COLUMN IF NOT EXISTS vivino_url TEXT;"
            )
        conn.commit()
        log.info("Migration complete — vivino_url column added to wines table.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
