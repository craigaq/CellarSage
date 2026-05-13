"""
Backfills the `state` column for Australian wines where it is NULL,
using the producer → state mapping in producer_state.json.

Also emits a gap report so new producers can be added to the JSON
before the next weekly sync — no wine will silently fall back to
"National Contender" without it appearing in the sync log first.

Runs automatically at the end of the weekly sync pipeline, or manually:
    python -m sync.backfill_producer_state
"""

import html
import json
import logging
import os
import pathlib
import sys

import psycopg2

log = logging.getLogger(__name__)

_JSON_PATH = pathlib.Path(__file__).parent / "producer_state.json"


def _load_mapping() -> list[tuple[str, str]]:
    pairs = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
    # Longest-first so "shaw and smith" matches before "shaw"
    return sorted([tuple(p) for p in pairs], key=lambda x: -len(x[0]))


def _resolve_state(name: str, mapping: list[tuple[str, str]]) -> str | None:
    lower = html.unescape(name).lower()
    for producer, state in mapping:
        if lower.startswith(producer) or f" {producer} " in lower:
            return state
    return None


def backfill_producer_state(conn=None) -> tuple[int, list[str]]:
    """
    Resolves state for Australian wines with state IS NULL.

    Returns (updated_count, gap_wine_names).
    gap_wine_names are wines still unresolved after the backfill —
    these need a new entry in producer_state.json.
    """
    mapping  = _load_mapping()
    own_conn = conn is None

    if own_conn:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            log.warning("DATABASE_URL not set — skipping producer state backfill")
            return 0, []
        conn = psycopg2.connect(db_url)

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name FROM wines WHERE state IS NULL AND country = 'Australia'"
            )
            rows = cur.fetchall()

        if not rows:
            log.info("Producer state backfill: no Australian wines with NULL state — nothing to do")
            return 0, []

        updates: list[tuple[str, int]] = []
        gaps:    list[str]             = []

        for wine_id, name in rows:
            state = _resolve_state(name, mapping)
            if state:
                updates.append((state, wine_id))
            else:
                gaps.append(name)

        if updates:
            with conn.cursor() as cur:
                cur.executemany("UPDATE wines SET state = %s WHERE id = %s", updates)
            conn.commit()

        log.info(
            "Producer state backfill: %d updated, %d unresolved",
            len(updates), len(gaps),
        )

        if gaps:
            log.warning("Producer state gaps — add these producers to producer_state.json:")
            seen: set[str] = set()
            for name in gaps:
                # Deduplicate by first two words (approximate producer key)
                key = " ".join(name.lower().split()[:2])
                if key not in seen:
                    seen.add(key)
                    log.warning("  [GAP] %s", name)

        return len(updates), gaps

    finally:
        if own_conn:
            conn.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )
    from dotenv import load_dotenv
    load_dotenv()

    updated, gaps = backfill_producer_state()

    print(f"\nUpdated : {updated}")
    print(f"Gaps    : {len(gaps)}")

    if gaps:
        print("\nProducers not yet in producer_state.json (add and re-run):")
        seen: set[str] = set()
        for name in gaps:
            key = " ".join(name.lower().split()[:2])
            if key not in seen:
                seen.add(key)
                print(f"  {name}")
        # Exit 2 signals gaps exist without failing CI
        sys.exit(2)
