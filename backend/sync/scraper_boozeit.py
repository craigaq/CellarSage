"""
Scraper for Boozeit (boozeit.com.au) — Australian online liquor retailer.

Uses Shopify's public product JSON API — no auth or headless browser required.
Paginates /collections/wine/products.json until an empty page is returned.
"""

import re
import json
import time
import logging
import urllib.request
import urllib.error
from typing import Optional

log = logging.getLogger(__name__)

_BASE_URL    = "https://www.boozeit.com.au"
_COLLECTION  = "wines"
_PAGE_SIZE   = 250
_CRAWL_DELAY = 0.5  # seconds between pages

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json",
    "Accept-Language": "en-AU,en;q=0.9",
}

_SKIP_TITLE_RE = re.compile(
    r'\b(case|dozen|mixed\s+pack|gift\s+set|hamper|\d+\s*x\s*\d+|\d+\s*pack)\b',
    re.IGNORECASE,
)


def _fetch_page(page: int) -> Optional[list]:
    url = (
        f"{_BASE_URL}/collections/{_COLLECTION}/products.json"
        f"?limit={_PAGE_SIZE}&page={page}"
    )
    if page > 1:
        time.sleep(_CRAWL_DELAY)
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data.get("products", [])
    except urllib.error.HTTPError as e:
        log.warning("boozeit: HTTP %d — page %d", e.code, page)
    except Exception as e:
        log.warning("boozeit: request error page %d: %s", page, e)
    return None


def scrape_boozeit() -> list[dict]:
    log.info("boozeit: starting Shopify product API scrape …")
    all_products: list[dict] = []
    page = 1

    while True:
        log.info("boozeit: fetching page %d", page)
        items = _fetch_page(page)
        if not items:
            log.info("boozeit: empty page %d — done", page)
            break
        all_products.extend(items)
        log.info(
            "boozeit: page %d → %d items (running total: %d)",
            page, len(items), len(all_products),
        )
        if len(items) < _PAGE_SIZE:
            break
        page += 1

    results: list[dict] = []
    for p in all_products:
        title = (p.get("title") or "").strip()
        if not title or _SKIP_TITLE_RE.search(title):
            continue

        variants = p.get("variants") or []
        if not variants:
            continue
        try:
            price = float(variants[0].get("price", "0"))
        except (ValueError, TypeError):
            continue
        if price <= 0:
            continue

        handle = p.get("handle", "")
        url = f"{_BASE_URL}/products/{handle}" if handle else None

        results.append({
            "name":     title,
            "price":    price,
            "url":      url,
            "retailer": "boozeit",
            "varietal": (p.get("product_type") or "").strip() or None,
            "vendor":   (p.get("vendor") or "").strip(),
        })

    # Deduplicate by name — keep lowest price
    seen: dict[str, dict] = {}
    for r in results:
        key = r["name"].lower()
        if key not in seen or r["price"] < seen[key]["price"]:
            seen[key] = r
    deduped = list(seen.values())

    log.info(
        "boozeit: scrape complete — %d products (%d dupes removed)",
        len(deduped), len(results) - len(deduped),
    )
    return deduped
