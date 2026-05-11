"""
Maps raw scraped JSON from each merchant into our internal WineRecord +
MerchantOffer schema. Add a new _normalize_<merchant> function for each
new retailer; the dispatch table at the bottom routes automatically.
"""

import json
import pathlib
import re
import logging
from typing import Optional

from .models import WineRecord, MerchantOffer

log = logging.getLogger(__name__)

# ── Country origin markers (checked longest-phrase-first per country) ─────────
# Maps distinctive region/place names to their country. Default is "Australia"
# since Liquorland is an Australian retailer and most unlabelled wines are domestic.
_COUNTRY_MARKERS: list[tuple[str, list[str]]] = [
    ("New Zealand", [
        "new zealand", "marlborough", "hawke's bay", "hawkes bay",
        "central otago", "wairarapa", "martinborough", "gisborne",
    ]),
    ("France", [
        "champagne", "burgundy", "bordeaux", "provence", "alsace",
        "rhone", "rhône", "loire", "languedoc", "beaujolais",
        "chablis", "sancerre",
    ]),
    ("Italy", [
        "tuscany", "tuscan", "barolo", "brunello", "chianti",
        "amarone", "ripasso", "primitivo", "sicilian", "sicily", "gavi",
        # prosecco omitted: widely used as a style name by Australian producers
    ]),
    ("Spain", ["rioja", "ribera del duero", "cava"]),
    ("Portugal", ["douro", "alentejo", "vinho verde"]),
    ("Germany", ["mosel", "rheingau", "pfalz"]),
    ("USA", ["napa valley", "napa", "sonoma", "california"]),
    ("South Africa", ["stellenbosch", "franschhoek"]),
    ("Austria", ["wachau", "kamptal", "burgenland"]),
    ("Argentina", ["mendoza", "lujan de cuyo", "luján de cuyo"]),
    ("Chile", ["maipo", "colchagua", "casablanca valley", "aconcagua"]),
]

# Brand-name → country for well-known imported brands that carry no
# geographic marker in their product names and would otherwise default
# to "Australia". Checked after region lookup, before the Australia fallback.
_BRAND_COUNTRY: list[tuple[str, str]] = [
    # New Zealand
    ("oyster bay",    "New Zealand"),
    ("villa maria",   "New Zealand"),
    ("kim crawford",  "New Zealand"),
    ("selaks",        "New Zealand"),
    ("saint clair",   "New Zealand"),
    ("babich",        "New Zealand"),
    ("cloudy bay",    "New Zealand"),
    ("spy valley",    "New Zealand"),
    ("stoneleigh",    "New Zealand"),
    ("catalina sounds", "New Zealand"),
    ("counting sheep",  "New Zealand"),
    ("giesen",          "New Zealand"),
    ("kamana",          "New Zealand"),
    ("lana's bike",     "New Zealand"),
    ("matua",           "New Zealand"),
    ("nanny goat",      "New Zealand"),
    ("rapaura springs", "New Zealand"),
    ("rochecombe",      "New Zealand"),
    ("rock paper scissors", "New Zealand"),
    ("secret stone",    "New Zealand"),
    ("sheep shape",     "New Zealand"),
    ("squealing pig",   "New Zealand"),
    ("ta ku",           "New Zealand"),
    ("upside down",     "New Zealand"),
    # France
    ("veuve clicquot",  "France"),
    ("champteloup",     "France"),
    ("b francois",      "France"),
    ("tussock jumper",  "France"),
    ("fat bastard",     "France"),
    ("mouton cadet",    "France"),
    # USA
    ("wente",           "USA"),
    ("beringer",        "USA"),
    ("robert mondavi",  "USA"),
    ("barefoot",        "USA"),
    ("bota box",        "USA"),
    # Argentina
    ("alamos",          "Argentina"),
    ("19 crimes",     "Australia"),  # keep as AU — made under licence in AU
]

# Unaccented → accented canonical spellings
_VARIETAL_CANONICAL: dict[str, str] = {
    "gruner veltliner": "Grüner Veltliner",
    "gewurztraminer": "Gewürztraminer",
    "carmenere": "Carménère",
    "mourvedre": "Mourvèdre",
    "airen": "Airén",
    "albarino": "Albariño",
    "torrontes": "Torrontés",
}


# ── Australian producer → state mapping (loaded from producer_state.json) ────
# Longest entries sort first so "jacob's creek" matches before "jacob".
# Add new producers to the JSON file — no code change needed.
_PRODUCER_STATE: list[tuple[str, str]] = sorted(
    [tuple(pair) for pair in json.loads(
        (pathlib.Path(__file__).parent / "producer_state.json").read_text(encoding="utf-8")
    )],
    key=lambda x: -len(x[0]),
)

# Field names that indicate a member/loyalty-only price in scraped data.
_MEMBER_PRICE_KEYS = frozenset({
    "member_price", "loyalty_price", "rewards_price",
    "club_price", "everyday_price", "everyday_rewards_price",
})


def _infer_state_from_producer(name: str) -> str | None:
    """Match the wine name against known Australian producer brands."""
    lower = name.lower()
    for producer, state in _PRODUCER_STATE:
        if lower.startswith(producer) or f" {producer} " in lower:
            return state
    return None


def _infer_country_keywords(name: str) -> str:
    """Keyword fallback for country inference when no region matches."""
    lower = name.lower()
    for country, markers in _COUNTRY_MARKERS:
        if any(m in lower for m in markers):
            return country
    for brand, country in _BRAND_COUNTRY:
        if brand in lower:
            return country
    return "Australia"


def _infer_origin(name: str) -> tuple[str, str | None]:
    """
    Return (country, state) for a wine product name.

    Resolution order:
      1. Region lookup table (place names, most accurate)
      2. Producer-brand lookup (covers brands without region in name)
      3. Country keyword matching
      4. Default to Australia with no state
    """
    from region_lookup import lookup_region
    match = lookup_region(name)
    if match:
        country = match["country"]
        state   = match.get("state") or (
            _infer_state_from_producer(name) if country == "Australia" else None
        )
        return country, state

    country = _infer_country_keywords(name)
    state   = _infer_state_from_producer(name) if country == "Australia" else None
    return country, state


def _infer_varietal(name: str) -> Optional[str]:
    """Extract the best-matching canonical varietal from a product name."""
    lower = name.lower()
    for kw in _CATALOG_KEYWORDS:
        if kw in lower:
            return _VARIETAL_CANONICAL.get(kw, kw.title())
    return None


# ── Known catalog varietal keywords (lowercase) ───────────────────────────────
# Items whose name/varietal don't match any of these are rejected so only
# wines in our known catalog land in the database.
# Sorted longest-first so "cabernet sauvignon" matches before "cabernet".
_CATALOG_KEYWORDS: list[str] = sorted([
    # ── Still reds & whites ──────────────────────────────────────────────────
    "cabernet sauvignon", "cabernet franc", "sauvignon blanc",
    "pinot noir", "pinot grigio", "pinot gris",
    "grüner veltliner", "gruner veltliner",
    "gewürztraminer", "gewurztraminer",
    "nero d'avola", "chenin blanc", "trebbiano",
    "tempranillo", "sangiovese", "carménère", "carmenere",
    "mourvèdre", "mourvedre", "vermentino",
    "chardonnay", "grenache", "viognier", "riesling",
    "marsanne", "semillon", "malbec", "merlot",
    "shiraz", "syrah", "gamay", "fiano", "barbera",
    "nebbiolo", "zinfandel", "moscato", "muscat",
    "airén", "airen", "albariño", "albarino",
    "torrontés", "torrontes", "friulano",
    "cabernet",   # catch-all — must stay after more specific entries
    # ── Sparkling ────────────────────────────────────────────────────────────
    "sparkling shiraz", "champagne", "prosecco", "cava",
    # ── Dessert ──────────────────────────────────────────────────────────────
    "botrytis semillon", "late harvest riesling",
    "botrytis", "late harvest", "sauternes", "trockenbeerenauslese",
    # ── Fortified ────────────────────────────────────────────────────────────
    "rutherglen muscat", "tawny port", "vintage port", "fino sherry",
    "topaque", "tokay",    # alternative names for Rutherglen Muscat
    "amontillado", "oloroso", "manzanilla",  # sherry styles
    "tawny", "sherry", "port",
], key=lambda s: -len(s))


def _matches_catalog(varietal: Optional[str], name: str) -> bool:
    """Return True if this wine maps to a known catalog varietal."""
    haystack = (varietal or "").lower() + " " + name.lower()
    return any(kw in haystack for kw in _CATALOG_KEYWORDS)


# ── Helpers ──────────────────────────────────────────────────────────────────

# Non-750ml size patterns — anything matching this is rejected.
# Standard 750ml bottles often omit the size entirely, so we reject only
# explicit non-standard sizes rather than requiring "750ml" to be present.
_NON_STD_SIZE_RE = re.compile(
    r'(?<![0-9])(375\s?m[lL]|187\s?m[lL]|1[.·]5\s?[lL]|1500\s?m[lL]'
    r'|1\s?[lL](?!\s?[0-9])|1000\s?m[lL]|[2-9]\s?[lL]|[2-9]000\s?m[lL])',
    re.IGNORECASE,
)


def _is_standard_bottle(name: str, item: dict) -> bool:
    """Return False if the product is clearly not a standard 750ml bottle."""
    size_field = str(item.get("size") or item.get("volume") or item.get("pack_size") or "")
    haystack = name + " " + size_field
    return not _NON_STD_SIZE_RE.search(haystack)


def _extract_vintage(text: str) -> Optional[int]:
    """Pull a 4-digit year (1980–2030) out of a product name."""
    if not text:
        return None
    match = re.search(r'\b(19[89]\d|20[012]\d)\b', text)
    return int(match.group()) if match else None


def _coerce_price(raw) -> Optional[float]:
    """Accept int, float, or price strings like '$24.99' / '24,99'."""
    if raw is None:
        return None
    try:
        return float(str(raw).replace(',', '.').replace('$', '').strip())
    except (ValueError, TypeError):
        return None


def _first(*keys, src: dict):
    """Return the value of the first matching key found in src."""
    for k in keys:
        if k in src and src[k] not in (None, '', []):
            return src[k]
    return None


# ── Per-merchant normalizers ──────────────────────────────────────────────────

def _normalize_liquorland(item: dict, retailer: str) -> Optional[tuple[WineRecord, MerchantOffer]]:
    name = _first('title', 'name', 'product_name', src=item)
    if not name:
        return None

    price_raw = _first('price_now', 'currentPrice', 'price', 'salePrice', src=item)
    price = _coerce_price(price_raw)
    if price is None or price <= 0:
        return None

    vintage  = _extract_vintage(name)
    region   = _first('region', 'wine_region', 'area', src=item)
    varietal = _first('varietal', 'variety', 'grape', 'type', src=item)
    url      = _first('source_url', 'url', 'productUrl', 'link', src=item)

    # Rating: prefer top-level field; fall back to attributes.review_stats
    _attrs        = item.get('attributes') or {}
    _review_stats = _attrs.get('review_stats') or {}
    rating_raw    = item.get('rating') or _review_stats.get('average')
    rating        = _coerce_price(rating_raw)
    review_count  = int(item.get('review_count') or _review_stats.get('total') or 0)

    # Member price detection: explicit flag fields take priority; fallback is
    # checking whether price_now < a separately listed standard price, which
    # indicates the scraped price is the member/loyalty rate.
    is_member_price = any(k in item for k in _MEMBER_PRICE_KEYS)
    if not is_member_price and item.get('price_now'):
        _std = _coerce_price(item.get('price') or item.get('was_price') or item.get('rrp'))
        _now = _coerce_price(item['price_now'])
        if _std and _now and _now < _std - 0.01:
            is_member_price = True

    if not _matches_catalog(varietal, name):
        log.debug("liquorland item skipped — not in known catalog: %r", name)
        return None

    if not _is_standard_bottle(name, item):
        log.debug("liquorland item skipped — non-standard bottle size: %r", name)
        return None

    if varietal is None:
        varietal = _infer_varietal(name)

    country, state = _infer_origin(name)
    clean_name     = re.sub(r'\s*\b(19[89]\d|20[012]\d)\b\s*', ' ', name).strip()

    wine  = WineRecord(name=clean_name, vintage=vintage, region=region,
                       varietal=varietal, country=country, state=state)
    offer = MerchantOffer(wine_name=clean_name, vintage=vintage,
                          retailer=retailer, price=price, url=url,
                          rating=rating, review_count=review_count,
                          is_member_price=is_member_price)
    return wine, offer


def _normalize_cellarbrations(item: dict, retailer: str) -> Optional[tuple[WineRecord, MerchantOffer]]:
    name = _first("name", src=item)
    if not name:
        return None

    price = _coerce_price(_first("priceNumeric", "wholePrice", "price", src=item))
    if price is None or price <= 0:
        return None

    if not _is_standard_bottle(name, item):
        log.debug("cellarbrations item skipped — non-standard bottle size: %r", name)
        return None

    # Varietal from the API's category data
    def_cats = item.get("defaultCategory") or []
    varietal_raw = def_cats[0].get("category") if def_cats else None
    varietal = _first("varietal", src=item) or varietal_raw
    if varietal and varietal.lower() in ("grocery", "alcohol", "wine"):
        varietal = None

    if not _matches_catalog(varietal, name):
        log.debug("cellarbrations item skipped — not in known catalog: %r", name)
        return None

    vintage    = _extract_vintage(name)
    clean_name = re.sub(r'\s*\b(19[89]\d|20[012]\d)\b\s*', ' ', name).strip()
    url        = item.get("url")
    country, state = _infer_origin(clean_name)

    if varietal is None:
        varietal = _infer_varietal(clean_name)

    wine  = WineRecord(name=clean_name, vintage=vintage, varietal=varietal,
                       country=country, state=state)
    offer = MerchantOffer(wine_name=clean_name, vintage=vintage,
                          retailer=retailer, price=price, url=url)
    return wine, offer


def _normalize_danmurphys(item: dict, retailer: str) -> Optional[tuple[WineRecord, MerchantOffer]]:
    name = _first('name', 'title', 'productName', src=item)
    if not name:
        return None

    price = _coerce_price(_first('price', 'currentPrice', 'priceValue', src=item))
    if price is None or price <= 0:
        return None

    vintage  = _extract_vintage(name)
    clean_name = re.sub(r'\s*\b(19[89]\d|20[012]\d)\b\s*', ' ', name).strip()
    region   = _first('region', 'wine_region', src=item)
    varietal = _first('varietal', 'variety', 'type', src=item)
    url      = _first('url', 'link', src=item)

    if not _matches_catalog(varietal, name):
        log.debug("danmurphys item skipped — not in known catalog: %r", name)
        return None

    if not _is_standard_bottle(name, item):
        log.debug("danmurphys item skipped — non-standard bottle size: %r", name)
        return None

    wine  = WineRecord(name=clean_name, vintage=vintage, region=region, varietal=varietal)
    offer = MerchantOffer(wine_name=clean_name, vintage=vintage,
                          retailer=retailer, price=price, url=url)
    return wine, offer


# ── Dispatch ──────────────────────────────────────────────────────────────────

_NORMALIZERS = {
    "liquorland":           _normalize_liquorland,
    "liquorland_fortified": _normalize_liquorland,
    "liquorland_dessert":   _normalize_liquorland,
    "cellarbrations":       _normalize_cellarbrations,
    "portersliquor":        _normalize_cellarbrations,  # same WYNSHOP format
    "bottleo":              _normalize_cellarbrations,  # same WYNSHOP format
    "danmurphys":           _normalize_danmurphys,
}


# Maps composite merchant keys → the canonical retailer name stored in the DB.
# Keeps DB retailer values consistent regardless of how many scrape configs
# a single retailer has (e.g. liquorland + liquorland_fortified → "liquorland").
_MERCHANT_TO_RETAILER: dict[str, str] = {
    "liquorland_fortified": "liquorland",
    "liquorland_dessert":   "liquorland",
}


def normalize(items: list[dict], merchant: str) -> list[tuple[WineRecord, MerchantOffer]]:
    """
    Normalize a list of raw scraped items for a given merchant.
    Skips and logs any item that can't be mapped cleanly.
    """
    fn = _NORMALIZERS.get(merchant)
    if not fn:
        raise ValueError(f"No normalizer registered for merchant: {merchant!r}")
    retailer = _MERCHANT_TO_RETAILER.get(merchant, merchant)

    results = []
    for item in items:
        try:
            pair = fn(item, retailer)
            if pair:
                results.append(pair)
        except Exception as exc:
            log.warning("Normalizer skipped item for %s: %s — %r", merchant, exc, item)

    log.info("Normalised %d/%d items for %s", len(results), len(items), merchant)
    return results
