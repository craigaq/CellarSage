"""
Enrich beers with Untappd ratings — beer analogue of sync/enrich_vivino.py.

For each beer without a rating yet, searches Untappd (lulzasaur/untappd-scraper,
search mode), matches the best result to the beer, and stores the rating, URL
and (bonus) real per-beer IBU.

Matching guard: the beer's BRAND token must appear in the candidate and the
candidate must cover most of the beer's name tokens — stops a generic
"Pale Ale" search grabbing some unrelated brewery's pale ale.

Run:
  python -m sync.enrich_untappd            # all un-enriched beers
  python -m sync.enrich_untappd --limit 10 # first N (spot check)
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time

from .scraper import run_actor

log = logging.getLogger(__name__)

_ACTOR_ID = "lulzasaur/untappd-scraper"
_DELAY_S = 2.5      # gap between searches — Untappd rate-limits rapid calls
_RETRIES = 1        # one retry (after a cooldown) before giving up on a beer


def _search(query: str) -> list[dict]:
    """Search Untappd with one retry + cooldown to ride out rate-limiting."""
    for attempt in range(_RETRIES + 1):
        try:
            return run_actor(_ACTOR_ID, {"mode": "search", "query": query, "maxResults": 5}, max_items=5)
        except Exception as e:  # noqa: BLE001
            if attempt < _RETRIES:
                time.sleep(15)  # cooldown then retry once
                continue
            raise e

# Tokens that don't identify a specific beer — ignored when checking the brand.
_GENERIC = frozenset({
    "pale", "ale", "lager", "ipa", "xpa", "stout", "porter", "beer", "premium",
    "dry", "original", "the", "co", "brewing", "company", "brewery", "hazy",
    "pilsner", "pils", "golden", "amber", "draught", "session", "summer",
    "bright", "low", "carb", "zero", "mid", "light", "strong", "extra",
    "blonde", "wheat", "sour", "red", "new", "lite", "crisp", "block", "cans",
    "bottle", "375ml", "of", "and", "&",
})


def _tokens(s: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]", " ", s.lower()).split())


def _match(beer_name: str, results: list[dict]) -> dict | None:
    """Best Untappd result for a beer, or None if nothing matches confidently."""
    q = _tokens(beer_name)
    brand_tokens = {t for t in q if t not in _GENERIC and len(t) >= 3}
    best, best_cov = None, 0.0
    for r in results:
        if not r.get("rating"):
            continue
        cand = _tokens(f"{r.get('brewery', '')} {r.get('beerName', '')}")
        # A distinctive (brand) token must be shared, else it's a generic match.
        if brand_tokens and not (brand_tokens & cand):
            continue
        coverage = len(q & cand) / len(q) if q else 0.0
        if coverage >= 0.55 and coverage > best_cov:
            best, best_cov = r, coverage
    return best


def enrich_untappd(limit: int | None = None) -> tuple[int, int]:
    """Enrich un-rated beers. Returns (matched, processed)."""
    import psycopg2
    import psycopg2.extras
    from dotenv import load_dotenv

    load_dotenv()
    conn = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name FROM beers WHERE untappd_enriched_at IS NULL ORDER BY id"
        + (f" LIMIT {int(limit)}" if limit else "")
    )
    beers = cur.fetchall()
    log.info("enrich_untappd: %d beers to process", len(beers))

    matched = 0
    for i, b in enumerate(beers, 1):
        if i > 1:
            time.sleep(_DELAY_S)  # throttle to avoid Untappd rate-limiting
        try:
            results = _search(b["name"])
        except Exception as e:  # noqa: BLE001
            log.warning("untappd search failed for %r: %s", b["name"], e)
            continue

        hit = _match(b["name"], results)
        if hit:
            ibu = hit.get("ibu")
            cur.execute(
                """UPDATE beers
                   SET untappd_rating = %s, untappd_url = %s, untappd_ibu = %s,
                       untappd_enriched_at = NOW()
                   WHERE id = %s""",
                (round(float(hit["rating"]), 2), hit.get("url") or "",
                 int(ibu) if ibu else None, b["id"]),
            )
            matched += 1
            log.info("[%d/%d] MATCH %.2f* %-30s -> %s %s",
                     i, len(beers), hit["rating"], b["name"][:30],
                     hit.get("brewery", ""), hit.get("beerName", ""))
        else:
            # Mark as processed (enriched_at set) so we don't re-query endlessly.
            cur.execute("UPDATE beers SET untappd_enriched_at = NOW() WHERE id = %s", (b["id"],))
            log.info("[%d/%d] no match  %s", i, len(beers), b["name"][:40])
        conn.commit()

    conn.close()
    return matched, len(beers)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    matched, processed = enrich_untappd(limit=limit)
    log.info("DONE: matched %d / %d beers", matched, processed)


if __name__ == "__main__":
    main()
