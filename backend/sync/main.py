"""
Cellar Sage Cloud-Sync Engine — entry point.

Orchestrates the full pipeline for every enabled merchant:
  Apify scrape → normalize → Sage upsert → summary log

Run locally:
    APIFY_API_TOKEN=... DATABASE_URL=... python -m sync.main

Run via GitHub Actions: see .github/workflows/weekly_sync.yml
"""

import logging
import sys

from .config import MERCHANT_REGISTRY
from .models import SyncResult
from .normalizer import normalize
from .scraper import run_actor
from .upsert import upsert_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("sync")


def sync_merchant(merchant: str, cfg: dict) -> SyncResult:
    result = SyncResult(merchant=merchant)

    try:
        raw = run_actor(
            actor_id=cfg["actor_id"],
            actor_input=cfg.get("actor_input", {}),
            max_items=cfg.get("max_items", 50),
        )
        result.scraped = len(raw)

        pairs = normalize(raw, merchant)
        result.normalised = len(pairs)

        wines, offers = upsert_batch(pairs)
        result.wines_upserted  = wines
        result.offers_upserted = offers

    except Exception as exc:
        log.exception("Sync failed for %s: %s", merchant, exc)
        result.errors.append(str(exc))

    return result


def main() -> int:
    log.info("=== Cellar Sage Sync Engine starting ===")
    results: list[SyncResult] = []
    any_error = False

    for merchant, cfg in MERCHANT_REGISTRY.items():
        if not cfg.get("enabled", False):
            log.info("Skipping disabled merchant: %s", merchant)
            continue

        log.info("--- Syncing %s ---", merchant)
        result = sync_merchant(merchant, cfg)
        results.append(result)

        if result.errors:
            any_error = True

    # Summary
    log.info("=== Sync complete ===")
    for r in results:
        status = "ERROR" if r.errors else "OK"
        log.info(
            "[%s] %s — scraped=%d normalised=%d wines=%d offers=%d",
            status, r.merchant,
            r.scraped, r.normalised,
            r.wines_upserted, r.offers_upserted,
        )
        for err in r.errors:
            log.error("  %s", err)

    return 1 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())
