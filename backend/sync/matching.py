"""
matching.py — Critic score backfill via fuzzy matching.

Loads the Wine Enthusiast Kaggle dataset (winemag-data-130k-v2.csv),
fuzzy-matches every wine in our DB using RapidFuzz, and writes the
critic_score + match metadata back to the wines table.

Usage:
    python -m sync.matching --csv path/to/winemag-data-130k-v2.csv
    python -m sync.matching --csv wine_reviews.csv --threshold 88 --dry-run
    python -m sync.matching --csv wine_reviews.csv --limit 50 --dry-run  # quick test

Requirements (add to backend/requirements.txt if not present):
    rapidfuzz>=3.0.0
    pandas>=2.0.0
"""

import argparse
import logging
import os
import re

import pandas as pd
import psycopg2
import psycopg2.extras
from rapidfuzz import fuzz, process

log = logging.getLogger(__name__)

# ── Text normalisation ────────────────────────────────────────────────────────

_YEAR_RE   = re.compile(r'\b(19[89]\d|20[012]\d)\b')
_REGION_RE = re.compile(r'\s*\([^)]*\)')          # removes "(Etna)", "(Napa Valley)" etc.
_WS_RE     = re.compile(r'\s+')


def _clean_we_title(title: str) -> str:
    """Normalise a Wine Enthusiast title for comparison.

    Input:  "Nicosia 2013 Vulkà Bianco (Etna)"
    Output: "nicosia vulkà bianco"
    """
    title = _REGION_RE.sub('', title)
    title = _YEAR_RE.sub('', title)
    return _WS_RE.sub(' ', title).strip().lower()


def _clean_db_name(name: str) -> str:
    """Normalise a wine name from our DB (vintage already stripped by scraper)."""
    return _WS_RE.sub(' ', name).strip().lower()


# ── Database ──────────────────────────────────────────────────────────────────

def _connect():
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise EnvironmentError('DATABASE_URL environment variable not set')
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


def _load_unscored_wines(conn) -> list[dict]:
    """Fetch wines that have not yet been matched to a critic score."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, vintage, varietal
            FROM   wines
            WHERE  critic_score IS NULL
            ORDER  BY id
        """)
        return list(cur.fetchall())


def _write_match(conn, wine_id: int, score: float, source: str, confidence: float) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE wines
               SET critic_score     = %s,
                   critic_source    = %s,
                   match_confidence = %s
             WHERE id = %s
        """, (score, source, confidence, wine_id))


# ── Index builder ─────────────────────────────────────────────────────────────

def _build_index(df: pd.DataFrame) -> tuple[list[str], list[float], pd.DataFrame]:
    """Return (cleaned_titles, points, original_df) for the WE dataset."""
    df = df.copy()
    df['_key'] = df['title'].apply(_clean_we_title)
    return df['_key'].tolist(), df['points'].tolist(), df


# ── Core matching logic ───────────────────────────────────────────────────────

def match_wines(
    csv_path: str,
    threshold: float = 85.0,
    dry_run: bool = False,
    limit: int | None = None,
) -> None:
    log.info('Loading Wine Enthusiast dataset: %s', csv_path)
    raw = pd.read_csv(csv_path, usecols=['title', 'points', 'variety', 'winery'])
    raw = raw.dropna(subset=['title', 'points'])
    raw['points'] = pd.to_numeric(raw['points'], errors='coerce')
    raw = raw.dropna(subset=['points']).reset_index(drop=True)
    log.info('WE dataset loaded: %d rows', len(raw))

    we_keys, we_points, we_df = _build_index(raw)

    conn = _connect()
    try:
        wines = _load_unscored_wines(conn)
        if limit:
            wines = wines[:limit]
        log.info('Wines to match: %d  (threshold: %.0f%%)', len(wines), threshold)

        matched = skipped = 0

        for wine in wines:
            query = _clean_db_name(wine['name'])

            result = process.extractOne(
                query,
                we_keys,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=threshold,
            )

            if result is None:
                skipped += 1
                log.debug('NO MATCH  %r', wine['name'])
                continue

            _match_key, confidence, idx = result
            score  = float(we_points[idx])
            we_row = we_df.iloc[idx]

            log.info(
                'MATCH  %-45s → %-45s  conf=%.0f%%  pts=%.1f',
                wine['name'], we_row['title'], confidence, score,
            )

            if not dry_run:
                _write_match(conn, wine['id'], score, 'wine_enthusiast', confidence)
            matched += 1

        if not dry_run:
            conn.commit()
            log.info('Changes committed.')
        else:
            log.info('Dry run — no changes written.')

        log.info('Finished. matched=%d  skipped=%d', matched, skipped)

    finally:
        conn.close()


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s  %(message)s',
    )

    parser = argparse.ArgumentParser(
        description='Fuzzy-match CellarSage wines to Wine Enthusiast critic scores',
    )
    parser.add_argument(
        '--csv', required=True,
        help='Path to winemag-data-130k-v2.csv (download from Kaggle)',
    )
    parser.add_argument(
        '--threshold', type=float, default=85.0,
        help='Minimum RapidFuzz similarity to accept a match (default: 85)',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Run matching and log results without writing to the database',
    )
    parser.add_argument(
        '--limit', type=int, default=None,
        help='Only process the first N wines — useful for a quick sanity check',
    )
    args = parser.parse_args()

    match_wines(
        csv_path=args.csv,
        threshold=args.threshold,
        dry_run=args.dry_run,
        limit=args.limit,
    )
