"""
Generic scraper for retailers running on the mi9cloud/WYNSHOP platform.

Any retailer using storefrontgateway.<domain>/api exposes the same
unauthenticated /preview endpoint. Pass the gateway base URL and the
retailer's public site URL to scrape_wynshop().

Confirmed retailers:
  - Cellarbrations  (storefrontgateway.cellarbrations.com.au)
  - Porters Liquor  (storefrontgateway.portersliquor.com.au)
  - The Bottle-O    (storefrontgateway.thebottle-o.com.au) — store discovery
                    needs regional coordinates; pending verification
"""

import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Optional

log = logging.getLogger(__name__)

_CITY_COORDS: list[tuple[float, float, str]] = [
    (-33.8688, 151.2093, "Sydney NSW"),
    (-37.8136, 144.9631, "Melbourne VIC"),
    (-27.4698, 153.0251, "Brisbane QLD"),
    (-31.9505, 115.8605, "Perth WA"),
    (-34.9285, 138.6007, "Adelaide SA"),
    (-35.2809, 149.1300, "Canberra ACT"),
    (-42.8821, 147.3272, "Hobart TAS"),
    (-12.4634, 130.8456, "Darwin NT"),
]

# Additional search terms to capture dessert and fortified wines that the
# generic "wine" query misses (these categories are catalogued separately).
EXTRA_QUERIES: list[str] = [
    "port", "sherry", "muscat", "botrytis", "fortified",
    "tokay", "topaque",
]

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _headers(lat: float, lng: float, site_base: str) -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, */*",
        "Accept-Language": "en-AU,en;q=0.9",
        "Origin": site_base,
        "Referer": f"{site_base}/wine",
        "X-Shopping-Mode": "22222222-2222-2222-2222-222222222222",
        "X-Site-Host": site_base,
        "X-Site-Location": "HeadersBuilderInterceptor",
        "X-Correlation-Id": str(uuid.uuid4()),
        "x-customer-session-id": f"{site_base}|{uuid.uuid4()}",
        "X-Customer-Address-Latitude": str(lat),
        "X-Customer-Address-Longitude": str(lng),
    }


def _get(url: str, lat: float, lng: float, site_base: str) -> Optional[dict]:
    req = urllib.request.Request(url, headers=_headers(lat, lng, site_base))
    try:
        with urllib.request.urlopen(req, timeout=20, context=_ctx) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        log.warning("HTTP %d for %s", e.code, url)
    except Exception as e:
        log.warning("Request failed for %s: %s", url, e)
    return None


def _get_stores(gateway_base: str, site_base: str) -> list[dict]:
    """Return one representative store per Australian state."""
    seen: set[str] = set()
    stores: list[dict] = []

    for lat, lng, label in _CITY_COORDS:
        url = f"{gateway_base}/api/delivery/stores"
        data = _get(url, lat, lng, site_base)
        if not data:
            continue
        for s in data.get("items", []):
            sid = s.get("retailerStoreId")
            if sid and sid not in seen:
                seen.add(sid)
                stores.append(s)
                log.info(
                    "Found store %s — %s (%s) [via %s]",
                    sid, s.get("name"), s.get("countyProvinceState"), label,
                )

    log.info("Total unique stores: %d", len(stores))
    return stores


def _get_wines_for_store(
    store_id: str,
    gateway_base: str,
    site_base: str,
    lat: float = -33.8688,
    lng: float = 151.2093,
) -> list[dict]:
    """Fetch all wine products for a store, deduplicating by productId."""
    seen_ids: set[str] = set()
    all_products: list[dict] = []

    for term in ["wine"] + EXTRA_QUERIES:
        url = f"{gateway_base}/api/stores/{store_id}/preview?q={term}&productsTake=1000"
        data = _get(url, lat, lng, site_base)
        if not data:
            continue
        for p in data.get("products") or []:
            pid = str(p.get("productId", ""))
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_products.append(p)

    log.info(
        "Store %s: %d unique products fetched (wine + fortified/dessert queries)",
        store_id, len(all_products),
    )
    return all_products


def scrape_wynshop(
    gateway_base: str,
    site_base: str,
    retailer: str,
) -> list[dict]:
    """
    Scrape all unique wine products across all stores for a WYNSHOP retailer.

    Returns a flat list of raw product dicts, each enriched with
    'retailer', 'url', and 'store_id' keys for the normalizer.
    """
    stores = _get_stores(gateway_base, site_base)
    if not stores:
        log.error("No stores found for %s — aborting scrape", retailer)
        return []

    # One store per state to avoid duplicate pricing
    stores_by_state: dict[str, dict] = {}
    for s in stores:
        state = s.get("countyProvinceState", "UNK")
        if state not in stores_by_state:
            stores_by_state[state] = s
            log.info(
                "Using store %s as representative for %s",
                s.get("retailerStoreId"), state,
            )

    all_products: dict[str, dict] = {}
    for state, store in stores_by_state.items():
        store_id = store.get("retailerStoreId")
        lat = store.get("latitude", -33.8688)
        lng = store.get("longitude", 151.2093)

        products = _get_wines_for_store(store_id, gateway_base, site_base, lat, lng)
        for prod in products:
            pid = str(prod.get("productId", ""))
            if pid and pid not in all_products:
                name = prod.get("name", "")
                all_products[pid] = {
                    **prod,
                    "retailer": retailer,
                    "url": f"{site_base}/search?q={urllib.parse.quote(name)}",
                    "store_id": store_id,
                }

    result = list(all_products.values())
    log.info("%s scrape complete: %d unique products", retailer, len(result))
    return result
