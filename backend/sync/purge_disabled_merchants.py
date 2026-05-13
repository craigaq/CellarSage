"""
One-time cleanup: remove offers and orphaned wines for disabled merchants.

Disabled merchants (cellarbrations, portersliquor, bottleo) were scraped
historically but are no longer synced. Their offers have stale URLs and their
wines bloat the Vivino enrichment queue.

Safe: any wine also sold by an active merchant (liquorland, laithwaites) keeps
its active offers and is NOT deleted.

Dry run (preview only — no changes):
    DATABASE_URL=... python -m sync.purge_disabled_merchants --dry-run

Live run:
    DATABASE_URL=... python -m sync.purge_disabled_merchants
"""

import logging
import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("purge_disabled_merchants")

_DISABLED = ('cellarbrations', 'portersliquor', 'bottleo')


def run(dry_run: bool) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL not set")

    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            # Count offers to be deleted
            cur.execute(
                "SELECT COUNT(*) FROM merchant_offers WHERE retailer IN %s",
                (_DISABLED,),
            )
            offer_count = cur.fetchone()[0]

            # Count wines that would become orphans after offer deletion
            cur.execute(
                """
                SELECT COUNT(*) FROM wines w
                WHERE NOT EXISTS (
                    SELECT 1 FROM merchant_offers mo
                    WHERE mo.wine_id = w.id
                      AND mo.retailer NOT IN %s
                )
                """,
                (_DISABLED,),
            )
            wine_count = cur.fetchone()[0]

            # Count wines that are shared with active merchants (will be kept)
            cur.execute(
                """
                SELECT COUNT(DISTINCT w.id) FROM wines w
                JOIN merchant_offers mo ON mo.wine_id = w.id
                WHERE mo.retailer IN %s
                  AND EXISTS (
                    SELECT 1 FROM merchant_offers mo2
                    WHERE mo2.wine_id = w.id
                      AND mo2.retailer NOT IN %s
                  )
                """,
                (_DISABLED, _DISABLED),
            )
            shared_count = cur.fetchone()[0]

            log.info("Offers to delete:          %d (from cellarbrations, portersliquor, bottleo)", offer_count)
            log.info("Orphaned wines to delete:  %d", wine_count)
            log.info("Shared wines kept:         %d (also sold by active merchant)", shared_count)

            if dry_run:
                log.info("DRY RUN — no changes made. Re-run without --dry-run to apply.")
                return

            # Delete offers from disabled merchants
            cur.execute(
                "DELETE FROM merchant_offers WHERE retailer IN %s",
                (_DISABLED,),
            )
            deleted_offers = cur.rowcount
            log.info("Deleted %d offers.", deleted_offers)

            # Delete orphaned wines (no remaining offers)
            cur.execute(
                """
                DELETE FROM wines
                WHERE NOT EXISTS (
                    SELECT 1 FROM merchant_offers mo WHERE mo.wine_id = wines.id
                )
                """
            )
            deleted_wines = cur.rowcount
            log.info("Deleted %d orphaned wines.", deleted_wines)

        conn.commit()
        log.info("Purge complete.")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run(dry_run=dry_run)
