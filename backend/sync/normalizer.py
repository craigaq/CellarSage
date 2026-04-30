"""
Maps raw scraped JSON from each merchant into our internal WineRecord +
MerchantOffer schema. Add a new _normalize_<merchant> function for each
new retailer; the dispatch table at the bottom routes automatically.
"""

import re
import logging
from typing import Optional

from .models import WineRecord, MerchantOffer

log = logging.getLogger(__name__)

# ── Known catalog varietal keywords (lowercase) ───────────────────────────────
# Items whose name/varietal don't match any of these are rejected so only
# wines in our known catalog land in the database.
# Sorted longest-first so "cabernet sauvignon" matches before "cabernet".
_CATALOG_KEYWORDS: list[str] = sorted([
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
    r'\b(375\s?m[lL]|187\s?m[lL]|1[.·]5\s?[lL]|1500\s?m[lL]'
    r'|[2-9]\s?[lL]|[2-9]000\s?m[lL])\b',
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
    url      = _first('url', 'productUrl', 'link', src=item)

    if not _matches_catalog(varietal, name):
        log.debug("liquorland item skipped — not in known catalog: %r", name)
        return None

    if not _is_standard_bottle(name, item):
        log.debug("liquorland item skipped — non-standard bottle size: %r", name)
        return None

    clean_name = re.sub(r'\s*\b(19[89]\d|20[012]\d)\b\s*', ' ', name).strip()

    wine  = WineRecord(name=clean_name, vintage=vintage, region=region, varietal=varietal)
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
    "liquorland": _normalize_liquorland,
    "danmurphys": _normalize_danmurphys,
}


def normalize(items: list[dict], merchant: str) -> list[tuple[WineRecord, MerchantOffer]]:
    """
    Normalize a list of raw scraped items for a given merchant.
    Skips and logs any item that can't be mapped cleanly.
    """
    fn = _NORMALIZERS.get(merchant)
    if not fn:
        raise ValueError(f"No normalizer registered for merchant: {merchant!r}")

    results = []
    for item in items:
        try:
            pair = fn(item, merchant)
            if pair:
                results.append(pair)
        except Exception as exc:
            log.warning("Normalizer skipped item for %s: %s — %r", merchant, exc, item)

    log.info("Normalised %d/%d items for %s", len(results), len(items), merchant)
    return results
