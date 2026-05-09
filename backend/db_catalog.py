"""
Live pricing layer — queries Supabase for the cheapest merchant offer per
catalog varietal. Results are cached for 1 hour so the DB is not hit on
every API request. Falls back silently to an empty dict when DATABASE_URL
is not set (local dev) or the query fails.
"""

import json
import os
import math
import re
import pathlib
import time
import logging
from datetime import datetime, timezone, timedelta

_STALE_DAYS = 8

log = logging.getLogger(__name__)

_TTL_SECONDS    = 3600
MIN_PRICE_AUD   = 10.0   # filter out bulk/cask wines below this threshold

# ── Producer → state (loaded from sync/producer_state.json) ──────────────────
# Applied at query time for rows upserted before this mapping existed.
# To add producers, edit the JSON file — no code change needed.
_PRODUCER_STATE: list[tuple[str, str]] = sorted(
    [tuple(pair) for pair in json.loads(
        (pathlib.Path(__file__).parent / "sync" / "producer_state.json").read_text(encoding="utf-8")
    )],
    key=lambda x: -len(x[0]),
)

# Sweet varietal/style keywords used to filter Tier 4 when pref_dry=True.
_SWEET_KEYWORDS = frozenset({"moscato", "muscat", "dessert", "sweet", "demi-sec", "doux"})


def _producer_state(name: str) -> str | None:
    lower = name.lower()
    for producer, state in _PRODUCER_STATE:
        if lower.startswith(producer) or f" {producer} " in lower:
            return state
    return None

# Module-level cache: key → {"data": dict, "ts": float}
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


def _keywords_for_canonical(canonical: str) -> list[str]:
    """Return all keyword strings that reverse-map to a given canonical varietal."""
    return [kw for kw, can in _VARIETAL_KEYWORDS if can == canonical]


# Module-level cache for buy-options and picks queries
_BUY_CACHE: dict[tuple, dict] = {}
_PICKS_CACHE: dict[tuple, dict] = {}


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


_SEARCH_STRIP_RE = re.compile(
    r'\s*\b(\d+\s*m[lL]|[Bb]ottle[s]?|[Bb][Vv][Ss]?|[Cc][Ll][Rr])\b',
    re.IGNORECASE,
)

def _cellarbrations_search_url(name: str) -> str:
    import urllib.parse
    query = _SEARCH_STRIP_RE.sub('', name).strip()
    return f"https://www.cellarbrations.com.au/search?q={urllib.parse.quote(query)}"


def get_buy_options(
    varietal: str,
    budget_min_aud: float = 0.0,
    budget_max_aud: float = 9999.0,
) -> list[dict]:
    """
    Return all matching offers (all retailers) for a canonical varietal name,
    one row per wine showing the cheapest available price and its retailer.

    Result shape: [{"name": "...", "price": 18.99, "url": "...", "retailer": "..."}]
    """
    effective_min = max(MIN_PRICE_AUD, budget_min_aud)
    cache_key = (varietal, effective_min, budget_max_aud)
    cached = _BUY_CACHE.get(cache_key)
    if cached and (time.time() - cached["ts"]) < _TTL_SECONDS:
        return cached["data"]

    keywords = _keywords_for_canonical(varietal)

    if not keywords:
        canonical = _infer_varietal(None, varietal) or varietal
        keywords  = _keywords_for_canonical(canonical)
    if not keywords:
        log.warning("db_catalog: no keywords found for canonical='%s'", varietal)
        return []

    conn = _connection()
    if not conn:
        return _BUY_CACHE.get(cache_key, {}).get("data", [])

    like_clauses = " OR ".join(
        f"LOWER(w.varietal) LIKE %s OR LOWER(w.name) LIKE %s"
        for _ in keywords
    )
    params: list = [effective_min, budget_max_aud]
    for kw in keywords:
        params.extend([f"%{kw}%", f"%{kw}%"])

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH cheapest AS (
                    SELECT DISTINCT ON (wine_id)
                        wine_id, price, url, retailer, last_updated
                    FROM merchant_offers
                    WHERE price IS NOT NULL
                      AND price >= %s
                      AND price <= %s
                    ORDER BY wine_id, price ASC
                )
                SELECT w.name, c.price, c.url, c.retailer, c.last_updated
                FROM cheapest c
                JOIN wines w ON w.id = c.wine_id
                WHERE ({like_clauses})
                ORDER BY c.price ASC
                LIMIT 20
                """,
                params,
            )
            rows = cur.fetchall()
    except Exception as exc:
        log.warning("db_catalog: get_buy_options query failed — %s", exc)
        return _BUY_CACHE.get(cache_key, {}).get("data", [])
    finally:
        conn.close()

    cutoff = datetime.now(timezone.utc) - timedelta(days=_STALE_DAYS)
    result = [
        {
            "name": row["name"],
            "price": float(row["price"]),
            "url": _cellarbrations_search_url(row["name"]) if (row.get("retailer") or "") == "cellarbrations" else (row["url"] or ""),
            "retailer": row["retailer"] or "",
            "price_is_stale": bool(row.get("last_updated") and row["last_updated"] < cutoff),
        }
        for row in rows
    ]
    _BUY_CACHE[cache_key] = {"data": result, "ts": time.time()}
    log.info("db_catalog: get_buy_options varietal='%s' → %d results", varietal, len(result))
    return result


def get_wine_picks(
    varietal: str,
    user_state: str | None = None,
    budget_min: float = 0.0,
    budget_max: float = 9999.0,
    pref_dry: bool = False,
) -> list[dict]:
    """
    Return up to 4 tiered wine picks for a canonical varietal, filtered to budget_max.
    - Tier 1 (Local Hero): best-value Australian, state-filtered when user_state provided
    - Tier 2 (National Contender): next best-value distinct Australian wine
    - Tier 3 (Internationalist): best-value non-Australian wine
    - Tier 4 (The Deal): absolute cheapest, subject to quality floor and dry guard
    """
    effective_min = max(MIN_PRICE_AUD, budget_min)
    cache_key = (varietal, user_state, effective_min, budget_max, pref_dry)
    cached = _PICKS_CACHE.get(cache_key)
    if cached and (time.time() - cached["ts"]) < _TTL_SECONDS:
        return cached["data"]

    # Accept either a canonical name ("Syrah/Shiraz") or a common alias ("Shiraz").
    keywords = _keywords_for_canonical(varietal)
    if not keywords:
        canonical = _infer_varietal(None, varietal) or varietal
        keywords  = _keywords_for_canonical(canonical)
    if not keywords:
        log.warning("get_wine_picks: no keywords for canonical='%s'", varietal)
        return []

    conn = _connection()
    if not conn:
        return _PICKS_CACHE.get(cache_key, {}).get("data", [])

    like_clauses = " OR ".join(
        f"LOWER(w.varietal) LIKE %s OR LOWER(w.name) LIKE %s"
        for _ in keywords
    )
    params: list = [effective_min, budget_max]
    for kw in keywords:
        params.extend([f"%{kw}%", f"%{kw}%"])

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH cheapest AS (
                    SELECT DISTINCT ON (wine_id)
                        wine_id, price, url, retailer, rating, review_count, is_member_price, last_updated
                    FROM merchant_offers
                    WHERE price IS NOT NULL
                      AND price >= %s
                      AND price <= %s
                      AND url IS NOT NULL
                      AND url != ''
                    ORDER BY wine_id, price ASC
                )
                SELECT w.name, w.country, w.state, w.region, w.varietal,
                       w.critic_score,
                       c.price, c.url, c.retailer, c.rating, c.review_count,
                       c.is_member_price, c.last_updated
                FROM cheapest c
                JOIN wines w ON w.id = c.wine_id
                WHERE ({like_clauses})
                ORDER BY c.price ASC
                LIMIT 100
                """,
                params,
            )
            all_rows = cur.fetchall()
    except Exception as exc:
        log.warning("get_wine_picks: query failed — %s", exc)
        return _PICKS_CACHE.get(cache_key, {}).get("data", [])
    finally:
        conn.close()

    # Convert to mutable dicts and backfill missing state from producer lookup.
    # Rows from the DB may have state=null for wines upserted before the
    # producer mapping existed; this fixes Tier 1 state filtering at query time.
    all_rows = [dict(r) for r in all_rows]
    for r in all_rows:
        if not r.get("state") and (r.get("country") or "").lower() == "australia":
            r["state"] = _producer_state(r["name"])

    def _sort_key(r):
        rating       = r.get("rating")
        review_count = int(r.get("review_count") or 0)
        price        = float(r.get("price") or 9999)
        critic       = r.get("critic_score")

        has_community = rating is not None and review_count >= 3
        has_critic    = critic is not None

        if has_community:
            # log1p dampens price so a $100 rated wine doesn't dominate a
            # well-reviewed $25 wine — the gap shrinks from 4x to ~1.6x.
            base  = (float(rating) * min(review_count, 30) / 30) / math.log1p(price)
            # Critic bonus: maps 85-100 pts → 0.0-0.15 additive boost
            boost = max(0.0, (float(critic) - 85.0) / 15.0) if has_critic else 0.0
            return (0, -(base + boost))

        if has_critic:
            # No community rating but we have a professional score —
            # still rank ahead of completely unscored wines, dampened by price.
            base = (float(critic) / 100.0) / math.log1p(price)
            return (0, -base)

        return (1, price)

    au_rows  = sorted(
        [r for r in all_rows if (r.get("country") or "").lower() == "australia"],
        key=_sort_key,
    )
    int_rows = sorted(
        [r for r in all_rows if (r.get("country") or "").lower() != "australia"],
        key=_sort_key,
    )

    picks: list[dict] = []
    seen: set[str]    = set()

    def _row_to_pick(r, tier: int, label: str) -> dict:
        lu = r.get("last_updated")
        stale = bool(lu and lu < datetime.now(timezone.utc) - timedelta(days=_STALE_DAYS))
        return {
            "tier": tier, "tier_label": label,
            "name": r["name"], "country": r.get("country"),
            "state": r.get("state"), "region": r.get("region"),
            "varietal": r.get("varietal"),
            "price": float(r["price"]),
            "url": _cellarbrations_search_url(r["name"]) if (r.get("retailer") or "") == "cellarbrations" else (r.get("url") or ""),
            "retailer": r.get("retailer") or "",
            "price_is_stale": stale,
            "is_member_price": bool(r.get("is_member_price")),
            "rating": float(r["rating"]) if r.get("rating") is not None else None,
            "review_count": int(r.get("review_count") or 0),
            "critic_score": float(r["critic_score"]) if r.get("critic_score") is not None else None,
        }

    # Tier 1 — best-value Australian, preferring wines from user's state when known.
    # Falls back to any Australian wine if no state match exists.
    tier1_pool = au_rows
    if user_state:
        state_upper = user_state.upper()
        state_rows  = [r for r in au_rows if (r.get("state") or "").upper() == state_upper]
        if state_rows:
            tier1_pool = state_rows + [r for r in au_rows if r not in state_rows]

    if tier1_pool:
        r = tier1_pool[0]
        picks.append(_row_to_pick(r, 1, "The Local Hero"))
        seen.add(r["name"])

    # Tier 2 — next best-value distinct Australian
    for r in au_rows:
        if r["name"] not in seen:
            picks.append(_row_to_pick(r, 2, "The National Contender"))
            seen.add(r["name"])
            break

    # Tier 3 — best-value non-Australian
    for r in int_rows:
        if r["name"] not in seen:
            picks.append(_row_to_pick(r, 3, "The Internationalist"))
            seen.add(r["name"])
            break

    # Tier 4 — The Deal: cheapest wine that clears the quality floor AND is
    # genuinely cheaper than every pick already selected. If nothing is cheaper
    # than the existing picks (e.g. the cheapest bottle already became T1),
    # suppress T4 rather than showing a "deal" that costs more.
    cheapest_picked = min((float(p["price"]) for p in picks), default=9999.0)
    deal_pool = sorted(all_rows, key=lambda r: float(r.get("price") or 9999))
    for r in deal_pool:
        if r["name"] in seen:
            continue
        if float(r.get("price") or 9999) >= cheapest_picked:
            break  # pool is price-sorted; nothing cheaper exists
        _rating  = r.get("rating")
        _reviews = int(r.get("review_count") or 0)
        if _rating is not None and _reviews >= 3 and float(_rating) < 3.0:
            continue
        if pref_dry:
            _name_lower = r.get("name", "").lower()
            _var_lower  = (r.get("varietal") or "").lower()
            if any(kw in _name_lower or kw in _var_lower for kw in _SWEET_KEYWORDS):
                continue
        picks.append(_row_to_pick(r, 4, "The Deal"))
        break

    _PICKS_CACHE[cache_key] = {"data": picks, "ts": time.time()}
    log.info("get_wine_picks: varietal='%s' → %d picks", varietal, len(picks))
    return picks


