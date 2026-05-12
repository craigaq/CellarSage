"""
enrich_vivino.py — Vivino community data enrichment.

Queries wines without Vivino data, batches them through the
mrbridge/vivino-wine-data-scraper Apify actor, fuzzy-matches results,
and writes vivino_rating, vivino_review_count, body, acidity, tannin,
sweetness, fruit_intensity, and flavor_notes back to the wines table.

Initial full enrichment (run once after migrate_vivino.py):
    DATABASE_URL=... APIFY_API_TOKEN=... python -m sync.enrich_vivino

The weekly sync calls enrich_vivino(limit=100) so only newly-upserted
wines are enriched each run. After 8 weeks all 790 existing wines will
have been enriched; subsequent runs take ~2-5 minutes.
"""

import json
import logging
import os
import re
import sys

import psycopg2
import psycopg2.extras
from rapidfuzz import fuzz, process

from .scraper import run_actor

log = logging.getLogger(__name__)

_ACTOR_ID         = "mrbridge/vivino-wine-data-scraper"
_BATCH_SIZE       = 20    # wine names per actor call
_MAX_RESULTS      = 3     # Vivino results per search term
_THRESHOLD_AUTO   = 90.0  # auto-accept above this confidence
_THRESHOLD_ACCEPT = 75.0  # accept only when it's the sole candidate

_YEAR_RE = re.compile(r'\b(19[89]\d|20[012]\d)\b')

_FRUIT_KEYWORDS = frozenset({
    'blackberry', 'plum', 'cherry', 'raspberry', 'strawberry',
    'blueberry', 'fig', 'currant', 'peach', 'apricot',
    'citrus', 'lemon', 'lime', 'apple', 'pear',
    'passion fruit', 'mango', 'tropical', 'redcurrant',
})

_STOPWORDS = frozenset({'the', 'a', 'an', 'de', 'le', 'la', 'les', 'du', 'van', 'von'})


# ── Text helpers ──────────────────────────────────────────────────────────────

def _clean(name: str) -> str:
    """Strip vintage years and normalise whitespace for fuzzy comparison."""
    name = _YEAR_RE.sub('', name)
    return ' '.join(name.lower().split())


def _vivino_label(item: dict) -> str:
    """Combine winery + wine name into a single comparable string."""
    winery = (item.get('winery') or '').strip()
    name   = (item.get('name')   or '').strip()
    return _clean(f"{winery} {name}" if winery else name)


def _brand_token(name: str) -> str:
    tokens = name.lower().split()
    return next((t for t in tokens if t not in _STOPWORDS), tokens[0] if tokens else '')


def _fruit_intensity(sweetness, flavor_notes) -> float | None:
    if sweetness is None:
        return None
    notes = {n.lower() for n in (flavor_notes or [])}
    boost = 1.0 if notes & _FRUIT_KEYWORDS else 0.0
    return min(5.0, float(sweetness) + boost)


# ── Database ──────────────────────────────────────────────────────────────────

def _connect():
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise EnvironmentError('DATABASE_URL not set')
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


def _load_wines_to_enrich(conn, limit: int | None) -> list[dict]:
    with conn.cursor() as cur:
        sql = "SELECT id, name, vintage FROM wines WHERE vivino_rating IS NULL ORDER BY id"
        if limit:
            sql += f" LIMIT {limit}"
        cur.execute(sql)
        return list(cur.fetchall())


def _write_vivino(conn, wine_id: int, data: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE wines
               SET vivino_rating       = %s,
                   vivino_review_count = %s,
                   body                = %s,
                   acidity             = %s,
                   tannin              = %s,
                   sweetness           = %s,
                   fruit_intensity     = %s,
                   flavor_notes        = %s
             WHERE id = %s
            """,
            (
                data.get('vivino_rating'),
                data.get('vivino_review_count'),
                data.get('body'),
                data.get('acidity'),
                data.get('tannin'),
                data.get('sweetness'),
                data.get('fruit_intensity'),
                json.dumps(data.get('flavor_notes') or []),
                wine_id,
            ),
        )


# ── Matching ──────────────────────────────────────────────────────────────────

def _match_wine(db_wine: dict, candidates: list[dict]) -> dict | None:
    """
    Return the best-matching Vivino candidate for a DB wine, or None.

    Rules (from product brief):
      ≥ 90%  → auto-accept
      75–90% → accept only when it's the sole candidate
      < 75%  → discard
    Brand guard: the first non-stopword token of our wine name must appear
    in the Vivino label to prevent cross-brand false positives.
    """
    if not candidates:
        return None

    query  = _clean(db_wine['name'])
    labels = [_vivino_label(c) for c in candidates]

    result = process.extractOne(query, labels, scorer=fuzz.token_sort_ratio)
    if result is None:
        return None

    _label, confidence, idx = result
    best = candidates[idx]

    brand = _brand_token(query)
    if brand and brand not in labels[idx]:
        log.debug("BRAND MISS  %r → %r", db_wine['name'], best.get('name'))
        return None

    if confidence >= _THRESHOLD_AUTO:
        return best

    if confidence >= _THRESHOLD_ACCEPT and len(candidates) == 1:
        return best

    log.debug("LOW CONF (%.0f%%, %d candidates)  %r", confidence, len(candidates), db_wine['name'])
    return None


def _extract(item: dict) -> dict:
    """Pull fields we need from a raw Vivino actor result item."""
    tp           = item.get('taste_profile') or {}
    flavor_notes = tp.get('flavor_notes') or []
    sweetness    = tp.get('sweetness')
    return {
        'vivino_rating':       item.get('average_rating'),
        'vivino_review_count': item.get('ratings_count'),
        'body':                tp.get('body'),
        'acidity':             tp.get('acidity'),
        'tannin':              tp.get('tannins'),   # Vivino spells it "tannins"
        'sweetness':           sweetness,
        'fruit_intensity':     _fruit_intensity(sweetness, flavor_notes),
        'flavor_notes':        flavor_notes,
        '_vivino_vintage':     item.get('vintage'),  # used only for vintage-trap logging
    }


# ── Actor call ────────────────────────────────────────────────────────────────

def _call_actor(wine_names: list[str]) -> list[dict]:
    return run_actor(
        actor_id=_ACTOR_ID,
        actor_input={
            'wineNames':           wine_names,
            'searchMode':          'name_and_vintage',
            'maxResultsPerSearch': _MAX_RESULTS,
            'includeTasteProfile': True,
            'includeReviews':      False,
            'countryCode':         'AU',
            'shipTo':              'AU',
        },
        max_items=len(wine_names) * _MAX_RESULTS,
    )


# ── Main enrichment function ──────────────────────────────────────────────────

def enrich_vivino(limit: int | None = None) -> int:
    """
    Enrich wines that have no Vivino data yet.

    Args:
        limit: cap on wines processed this call (None = all unenriched wines).

    Returns:
        Number of wines successfully enriched.
    """
    conn = _connect()
    try:
        wines = _load_wines_to_enrich(conn, limit)
        if not wines:
            log.info("enrich_vivino: all wines already have Vivino data — nothing to do")
            return 0

        log.info("enrich_vivino: %d wines to enrich (batch_size=%d)", len(wines), _BATCH_SIZE)
        enriched = 0

        for i in range(0, len(wines), _BATCH_SIZE):
            batch = wines[i : i + _BATCH_SIZE]
            names = [w['name'] for w in batch]

            log.info(
                "enrich_vivino: batch %d–%d / %d",
                i + 1, i + len(batch), len(wines),
            )

            try:
                results = _call_actor(names)
            except Exception as exc:
                log.warning("enrich_vivino: actor call failed — %s", exc)
                continue

            # Adelaide Local Edge: among multiple AU candidates at similar
            # confidence, sort AU wines first (by ratings_count desc) so the
            # RapidFuzz picker sees the best local option first.
            results_sorted = sorted(
                results,
                key=lambda r: (
                    0 if (r.get('country') or '').lower() == 'australia' else 1,
                    -(r.get('ratings_count') or 0),
                ),
            )

            for db_wine in batch:
                matched = _match_wine(db_wine, results_sorted)
                if matched is None:
                    log.debug("NO MATCH  %r", db_wine['name'])
                    continue

                data = _extract(matched)

                # Vintage Year Trap: vintages may differ (e.g. we have 2021,
                # Vivino matched the 2019) — still take the taste profile because
                # retail wines don't swing wildly year-to-year.
                db_vintage = db_wine.get('vintage')
                vv = data.pop('_vivino_vintage', None)
                if db_vintage and vv:
                    try:
                        gap = abs(int(db_vintage) - int(vv))
                        if gap > 3:
                            log.info(
                                "VINTAGE TRAP  %r  db=%s vivino=%s (gap=%d) — taking taste profile anyway",
                                db_wine['name'], db_vintage, vv, gap,
                            )
                    except (ValueError, TypeError):
                        pass

                _write_vivino(conn, db_wine['id'], data)
                enriched += 1
                log.info(
                    "ENRICHED  %-50s  rating=%.1f  reviews=%d",
                    db_wine['name'],
                    data.get('vivino_rating') or 0,
                    data.get('vivino_review_count') or 0,
                )

            conn.commit()

        log.info("enrich_vivino: complete — %d / %d wines enriched", enriched, len(wines))
        return enriched

    finally:
        conn.close()


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s — %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%SZ',
    )
    sys.exit(0 if enrich_vivino() >= 0 else 1)
