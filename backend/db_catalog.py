"""
Live pricing layer — queries Supabase for the cheapest merchant offer per
catalog varietal. Results are cached for 1 hour so the DB is not hit on
every API request. Falls back silently to an empty dict when DATABASE_URL
is not set (local dev) or the query fails.
"""

import os
import time
import logging

log = logging.getLogger(__name__)

_TTL_SECONDS    = 3600
MIN_PRICE_AUD   = 10.0   # filter out bulk/cask wines below this threshold

# Module-level cache: retailer → {"data": dict, "ts": float}
_CACHE: dict[str, dict] = {}

# Maps lowercase keywords (longest first) → canonical catalog varietal name.
# Must stay sorted longest-first so "cabernet sauvignon" wins over "cabernet".
_VARIETAL_KEYWORDS: list[tuple[str, str]] = sorted([
    ("cabernet sauvignon",  "Cabernet Sauvignon"),
    ("cabernet franc",      "Cabernet Franc"),
    ("sauvignon blanc",     "Sauvignon Blanc"),
    ("pinot noir",          "Pinot Noir"),
    ("pinot grigio",        "Pinot Grigio"),
    ("pinot gris",          "Pinot Grigio"),
    ("grüner veltliner",    "Grüner Veltliner"),
    ("gruner veltliner",    "Grüner Veltliner"),
    ("gewürztraminer",      "Gewürztraminer (Dry)"),
    ("gewurztraminer",      "Gewürztraminer (Dry)"),
    ("nero d'avola",        "Nero d'Avola"),
    ("chenin blanc",        "Chenin Blanc"),
    ("trebbiano",           "Trebbiano Toscano"),
    ("tempranillo",         "Tempranillo"),
    ("sangiovese",          "Sangiovese"),
    ("carménère",           "Carménère"),
    ("carmenere",           "Carménère"),
    ("mourvèdre",           "Mourvèdre"),
    ("mourvedre",           "Mourvèdre"),
    ("vermentino",          "Vermentino"),
    ("chardonnay",          "Chardonnay"),
    ("grenache",            "Grenache"),
    ("viognier",            "Viognier (Dry)"),
    ("riesling",            "Riesling"),
    ("marsanne",            "Marsanne"),
    ("semillon",            "Semillon"),
    ("malbec",              "Malbec"),
    ("merlot",              "Merlot"),
    ("shiraz",              "Syrah/Shiraz"),
    ("syrah",               "Syrah/Shiraz"),
    ("gamay",               "Gamay"),
    ("fiano",               "Fiano"),
    ("barbera",             "Barbera"),
    ("nebbiolo",            "Nebbiolo"),
    ("zinfandel",           "Zinfandel"),
    ("moscato",             "Moscato"),
    ("muscat",              "Moscato"),
    ("airén",               "Airén"),
    ("airen",               "Airén"),
    ("albariño",            "Albariño"),
    ("albarino",            "Albariño"),
    ("torrontés",           "Torrontés"),
    ("torrontes",           "Torrontés"),
    ("friulano",            "Sauvignonasse/Friulano"),
    ("cabernet",            "Cabernet Sauvignon"),  # catch-all — keep last
], key=lambda x: -len(x[0]))


def _infer_varietal(varietal: str | None, name: str) -> str | None:
    """Map a scraped varietal/name to a canonical catalog varietal name."""
    haystack = ((varietal or "") + " " + name).lower()
    for keyword, canonical in _VARIETAL_KEYWORDS:
        if keyword in haystack:
            return canonical
    return None


def _connection():
    try:
        import psycopg2
        import psycopg2.extras
        url = os.environ.get("DATABASE_URL")
        if not url:
            return None
        return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as exc:
        log.warning("db_catalog: connection failed — %s", exc)
        return None


def get_cheapest_by_varietal(retailer: str = "liquorland") -> dict[str, dict]:
    """
    Return the cheapest offer per catalog varietal for a given retailer.

    Result shape: { "Cabernet Sauvignon": {"price": 18.99, "url": "...", "name": "..."} }

    Returns an empty dict when the DB is unreachable — callers fall back to
    hardcoded prices in that case.
    """
    cached = _CACHE.get(retailer)
    if cached and (time.time() - cached["ts"]) < _TTL_SECONDS:
        return cached["data"]

    conn = _connection()
    if not conn:
        return _CACHE.get(retailer, {}).get("data", {})

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT w.name, w.varietal, mo.price, mo.url
                FROM merchant_offers mo
                JOIN wines w ON w.id = mo.wine_id
                WHERE mo.retailer = %s
                  AND mo.price IS NOT NULL
                  AND mo.price >= %s
                ORDER BY mo.price ASC
                """,
                (retailer, MIN_PRICE_AUD),
            )
            rows = cur.fetchall()
    except Exception as exc:
        log.warning("db_catalog: query failed — %s", exc)
        return _CACHE.get(retailer, {}).get("data", {})
    finally:
        conn.close()

    result: dict[str, dict] = {}
    for row in rows:
        canonical = _infer_varietal(row["varietal"], row["name"])
        if canonical and canonical not in result:
            result[canonical] = {
                "price": float(row["price"]),
                "url":   row["url"] or "",
                "name":  row["name"],
            }

    _CACHE[retailer] = {"data": result, "ts": time.time()}
    log.info("db_catalog: loaded %d live prices for retailer=%s", len(result), retailer)
    return result
