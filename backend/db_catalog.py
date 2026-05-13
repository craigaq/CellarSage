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

# Canonical names that ARE sparkling — excluded from the sparkling bleed filter.
_SPARKLING_CANONICALS = frozenset({
    "champagne", "prosecco", "cava", "sparkling shiraz",
    "crémant", "cremant", "pétillant naturel", "petillant naturel",
})


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
    # ── Still reds & whites ─────────────────────────────────────────────────
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
    ("cabernet",            "Cabernet Sauvignon"),  # catch-all — keep after specific Cab entries

    # ── Sparkling ───────────────────────────────────────────────────────────
    # Multi-word compound entries MUST appear before their component keywords
    # (sorted longest-first guarantees this) so "sparkling pinot noir" is
    # matched before "pinot noir" can steal the result.
    ("trockenbeerenauslese","Botrytis Semillon"),   # 20 chars — longest; checked first
    ("sparkling pinot noir", "Champagne"),           # 20 — prevents bleed into Pinot Noir
    ("sparkling chardonnay", "Champagne"),           # 20 — prevents bleed into Chardonnay
    ("methode champenoise",  "Champagne"),           # 19
    ("méthode champenoise",  "Champagne"),           # 19
    ("late harvest riesling","Late Harvest Riesling"), # 21
    ("sparkling shiraz",     "Sparkling Shiraz"),    # 16 — before bare "shiraz"
    ("sparkling rosé",       "Champagne"),           # 14
    ("sparkling rose",       "Champagne"),           # 13
    ("sparkling white",      "Champagne"),           # 14
    ("sparkling red",        "Sparkling Shiraz"),    # 13
    ("rutherglen muscat",    "Rutherglen Muscat"),   # 17 — before bare "muscat"
    ("botrytis semillon",    "Botrytis Semillon"),   # 17 — before bare "semillon"
    ("muscat liqueur",       "Rutherglen Muscat"),   # 14
    ("pétillant naturel",    "Champagne"),           # 17
    ("petillant naturel",    "Champagne"),           # 17
    ("vintage port",         "Vintage Port"),        # 12 — before bare "port"
    ("fino sherry",          "Fino Sherry"),         # 11 — before bare "sherry"
    ("amontillado",          "Fino Sherry"),         # 11
    ("manzanilla",           "Fino Sherry"),         # 10
    ("beerenauslese",        "Botrytis Semillon"),   # 13
    ("late harvest",         "Late Harvest Riesling"), # 12 — generic late harvest
    ("tawny port",           "Tawny Port"),          # 10 — before bare "port"
    ("noble rot",            "Botrytis Semillon"),   # 9
    ("sauternes",            "Botrytis Semillon"),   # 9
    ("champagne",            "Champagne"),           # 9
    ("prosecco",             "Prosecco"),            # 8
    ("crémant",              "Champagne"),           # 7 (accented)
    ("cremant",              "Champagne"),           # 7
    ("botrytis",             "Botrytis Semillon"),   # 8
    ("ice wine",             "Late Harvest Riesling"), # 8
    ("icewine",              "Late Harvest Riesling"), # 7
    ("auslese",              "Late Harvest Riesling"), # 7
    ("topaque",              "Rutherglen Muscat"),   # 7
    ("madeira",              "Tawny Port"),          # 7
    ("oloroso",              "Tawny Port"),          # 7
    ("sparkling",            "Champagne"),           # 8 — generic catch-all (checked after compounds)
    ("sherry",               "Fino Sherry"),         # 6
    ("tawny",                "Tawny Port"),          # 5
    ("tokay",                "Rutherglen Muscat"),   # 5
    ("port",                 "Tawny Port"),          # 4
    ("cava",                 "Cava"),                # 4
    ("fino",                 "Fino Sherry"),         # 4
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

# Strip varietal keywords from Cellarbrations search queries — retailer search
# returns "not found" when the varietal name is appended to the wine name.
_VARIETAL_STRIP_RE = re.compile(
    r'\b(' + '|'.join(re.escape(kw) for kw, _ in _VARIETAL_KEYWORDS) + r')\b',
    re.IGNORECASE,
)

def _cellarbrations_search_url(varietal: str) -> str:
    import urllib.parse
    return f"https://www.cellarbrations.com.au/results?q={urllib.parse.quote(varietal.lower())}"


def _liquorland_search_url(wine_name: str) -> str:
    import urllib.parse
    return f"https://www.liquorland.com.au/search?q={urllib.parse.quote(wine_name)}"


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

    # Match on varietal column first; fall back to name only when varietal is
    # NULL. This prevents blend wines (e.g. "Cabernet Merlot" stored as
    # varietal="Cabernet Sauvignon") from leaking into the wrong category.
    like_clauses = " OR ".join(
        f"(w.varietal IS NOT NULL AND LOWER(w.varietal) LIKE %s)"
        f" OR (w.varietal IS NULL AND LOWER(w.name) LIKE %s)"
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
            "url": (
                _cellarbrations_search_url(varietal) if (row.get("retailer") or "") == "cellarbrations"
                else _liquorland_search_url(row["name"]) if (row.get("retailer") or "") == "liquorland" and not (row["url"] or "")
                else (row["url"] or "")
            ),
            "retailer": row["retailer"] or "",
            "price_is_stale": bool(row.get("last_updated") and row["last_updated"] < cutoff),
        }
        for row in rows
    ]
    # Exclude sparkling wines when the requested varietal is not a sparkling type.
    if varietal.lower() not in _SPARKLING_CANONICALS:
        result = [
            r for r in result
            if "sparkling" not in r["name"].lower()
            and "sparkling" not in (r.get("varietal") or "").lower()
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
        f"(w.varietal IS NOT NULL AND LOWER(w.varietal) LIKE %s)"
        f" OR (w.varietal IS NULL AND LOWER(w.name) LIKE %s)"
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
                       w.vivino_rating, w.vivino_review_count,
                       w.body, w.acidity, w.tannin, w.sweetness,
                       w.fruit_intensity, w.flavor_notes,
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

    # Exclude sparkling wines when the requested varietal is not a sparkling type.
    if varietal.lower() not in _SPARKLING_CANONICALS:
        all_rows = [
            r for r in all_rows
            if "sparkling" not in r.get("name", "").lower()
            and "sparkling" not in (r.get("varietal") or "").lower()
        ]

    # Only surface wines with a meaningful rating signal — keeps "where to buy"
    # focused and avoids flooding users with unvetted listings.
    # Vivino requires ≥10 reviews to filter out noise; critic score alone is enough.
    all_rows = [
        r for r in all_rows
        if (r.get("vivino_rating") is not None and int(r.get("vivino_review_count") or 0) >= 10)
        or r.get("critic_score") is not None
    ]

    def _sort_key(r):
        vivino_rating = r.get("vivino_rating")
        vivino_count  = int(r.get("vivino_review_count") or 0)
        ret_rating    = r.get("rating")
        ret_count     = int(r.get("review_count") or 0)
        critic        = r.get("critic_score")
        price         = float(r.get("price") or 9999)

        # Tier 0: Vivino community data (global, high-volume signal)
        # Cap at 500 reviews so a 15k-review wine doesn't dominate a 200-review wine.
        if vivino_rating is not None and vivino_count >= 10:
            base  = (float(vivino_rating) * min(vivino_count, 500) / 500) / math.log1p(price)
            boost = max(0.0, (float(critic) - 85.0) / 15.0) if critic else 0.0
            return (0, -(base + boost))

        # Tier 0 fallback: retailer rating (low volume — cap at 30)
        if ret_rating is not None and ret_count >= 3:
            base  = (float(ret_rating) * min(ret_count, 30) / 30) / math.log1p(price)
            boost = max(0.0, (float(critic) - 85.0) / 15.0) if critic else 0.0
            return (0, -(base + boost))

        # Tier 0 fallback: critic score only, no community signal
        if critic is not None:
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
        flavor = r.get("flavor_notes")
        return {
            "tier": tier, "tier_label": label,
            "name": r["name"], "country": r.get("country"),
            "state": r.get("state"), "region": r.get("region"),
            "varietal": r.get("varietal"),
            "price": float(r["price"]),
            "url": (
                _cellarbrations_search_url(r.get("varietal") or "wine") if (r.get("retailer") or "") == "cellarbrations"
                else _liquorland_search_url(r["name"]) if (r.get("retailer") or "") == "liquorland" and not (r.get("url") or "")
                else (r.get("url") or "")
            ),
            "retailer": r.get("retailer") or "",
            "price_is_stale": stale,
            "is_member_price": bool(r.get("is_member_price")),
            "rating": float(r["rating"]) if r.get("rating") is not None else None,
            "review_count": int(r.get("review_count") or 0),
            "critic_score": float(r["critic_score"]) if r.get("critic_score") is not None else None,
            "vivino_rating": float(r["vivino_rating"]) if r.get("vivino_rating") is not None else None,
            "vivino_review_count": int(r.get("vivino_review_count") or 0),
            "body": float(r["body"]) if r.get("body") is not None else None,
            "acidity": float(r["acidity"]) if r.get("acidity") is not None else None,
            "tannin": float(r["tannin"]) if r.get("tannin") is not None else None,
            "sweetness": float(r["sweetness"]) if r.get("sweetness") is not None else None,
            "fruit_intensity": float(r["fruit_intensity"]) if r.get("fruit_intensity") is not None else None,
            "flavor_notes": list(flavor) if flavor else [],
        }

    # Tier 1 — best-value wine from the user's own state ("The Local Hero").
    # Only awarded when the wine is genuinely from the user's state.
    # Falls back to skipping Tier 1 (non-local wines are promoted to Tier 2 instead).
    tier1_awarded = False
    if user_state:
        state_upper = user_state.upper()
        state_rows  = [r for r in au_rows if (r.get("state") or "").upper() == state_upper]
        if state_rows:
            r = state_rows[0]
            picks.append(_row_to_pick(r, 1, "The Local Hero"))
            seen.add(r["name"])
            tier1_awarded = True
    else:
        # No location known — award Tier 1 to the best-value Australian wine.
        if au_rows:
            r = au_rows[0]
            picks.append(_row_to_pick(r, 1, "The Local Hero"))
            seen.add(r["name"])
            tier1_awarded = True

    # Tier 2 — best-value wine from a DIFFERENT Australian state ("The National Contender").
    # Prefer cross-state wines so the label is always accurate.
    # Falls back to a same-state wine only if no cross-state options exist,
    # in which case the label changes to "The Local Alternative".
    _state_upper = (user_state or "").upper()
    _other_au = [r for r in au_rows if r["name"] not in seen
                 and (_state_upper == "" or (r.get("state") or "").upper() != _state_upper)]
    _same_au  = [r for r in au_rows if r["name"] not in seen and r not in _other_au]
    _t2_pool  = _other_au or _same_au
    if _t2_pool:
        r  = _t2_pool[0]
        t2_label = "The National Contender" if _other_au else "The Local Alternative"
        picks.append(_row_to_pick(r, 2, t2_label))
        seen.add(r["name"])

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


