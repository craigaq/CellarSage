"""
Direct API scraper for Cellarbrations (mi9cloud/WYNSHOP platform).

No Apify, no browser — pure HTTP to the storefrontgateway API.
The preview endpoint returns full product data without authentication.

Auth discovery notes:
  - STS: sts.cellarbrations.com.au (IdentityServer, authorization_code only)
  - client_id: mwg.ecm.storefrontui  client_secret: secret
  - Product items require Bearer token; /preview does not
  - Gateway: storefrontgateway.cellarbrations.com.au/api/stores/{storeId}/...
"""

import json
import logging
import ssl
import uuid
from typing import Optional
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

GW_BASE = "https://storefrontgateway.cellarbrations.com.au"

# City coordinates used to discover stores in each state.
# The /api/delivery/stores endpoint returns the 3–5 nearest stores.
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

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _headers(lat: float, lng: float) -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, */*",
        "Accept-Language": "en-AU,en;q=0.9",
        "Origin": "https://www.cellarbrations.com.au",
        "Referer": "https://www.cellarbrations.com.au/wine",
        "X-Shopping-Mode": "22222222-2222-2222-2222-222222222222",
        "X-Site-Host": "https://www.cellarbrations.com.au",
        "X-Site-Location": "HeadersBuilderInterceptor",
        "X-Correlation-Id": str(uuid.uuid4()),
        "x-customer-session-id": f"https://www.cellarbrations.com.au|{uuid.uuid4()}",
        "X-Customer-Address-Latitude": str(lat),
        "X-Customer-Address-Longitude": str(lng),
    }


def _get(url: str, lat: float = -33.8688, lng: float = 151.2093) -> Optional[dict]:
    req = urllib.request.Request(url, headers=_headers(lat, lng))
    try:
        with urllib.request.urlopen(req, timeout=20, context=_ctx) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        log.warning("HTTP %d for %s", e.code, url)
    except Exception as e:
        log.warning("Request failed for %s: %s", url, e)
    return None


def _get_stores() -> list[dict]:
    """Return unique stores across Australia by querying each capital city."""
    seen: set[str] = set()
    stores: list[dict] = []

    for lat, lng, label in _CITY_COORDS:
        url = f"{GW_BASE}/api/delivery/stores"
        data = _get(url, lat=lat, lng=lng)
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

    log.info("Total unique Cellarbrations stores: %d", len(stores))
    return stores


# Additional search terms to capture dessert and fortified wines that the
# generic "wine" query misses (Cellarbrations categorises them separately).
_EXTRA_QUERIES = ["port", "sherry", "muscat", "botrytis", "fortified", "tokay", "topaque"]


def _get_wines_for_store(store_id: str, lat: float = -33.8688, lng: float = 151.2093) -> list[dict]:
    """
    Return all wine products for a store using the /preview endpoint.
    Runs the generic "wine" query plus targeted dessert/fortified queries,
    deduplicating by productId so no item appears twice.
    """
    seen_ids: set[str] = set()
    all_products: list[dict] = []

    for term in ["wine"] + _EXTRA_QUERIES:
        url = f"{GW_BASE}/api/stores/{store_id}/preview?q={term}&productsTake=1000"
        data = _get(url, lat=lat, lng=lng)
        if not data:
            continue
        for p in data.get("products") or []:
            pid = str(p.get("productId", ""))
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_products.append(p)

    log.info("Store %s: %d unique products fetched (wine + fortified/dessert queries)", store_id, len(all_products))
    return all_products


def _product_url(product: dict, store_id: str) -> str:
    """Construct a Cellarbrations search URL for the product name.

    Direct product URLs require a store session context and reliably 404
    without one. A search URL always resolves and surfaces the correct product.
    """
    import urllib.parse
    name = product.get("name", "")
    return f"https://www.cellarbrations.com.au/search?q={urllib.parse.quote(name)}"


def scrape_cellarbrations() -> list[dict]:
    """
    Fetch all unique wine products across all Cellarbrations stores.

    Returns a flat list of raw product dicts, each enriched with
    'retailer', 'url', and 'store_id' keys for the normalizer.
    """
    stores = _get_stores()
    if not stores:
        log.error("No Cellarbrations stores found — aborting scrape")
        return []

    # Pick one store per state to avoid duplicate pricing data
    stores_by_state: dict[str, dict] = {}
    for s in stores:
        state = s.get("countyProvinceState", "UNK")
        if state not in stores_by_state:
            stores_by_state[state] = s
            log.info("Using store %s as representative for %s", s.get("retailerStoreId"), state)

    # Collect products — deduplicate by productId across states
    all_products: dict[str, dict] = {}
    for state, store in stores_by_state.items():
        store_id = store.get("retailerStoreId")
        lat = store.get("latitude", -33.8688)
        lng = store.get("longitude", 151.2093)

        products = _get_wines_for_store(store_id, lat=lat, lng=lng)
        for prod in products:
            pid = str(prod.get("productId", ""))
            if pid and pid not in all_products:
                all_products[pid] = {
                    **prod,
                    "retailer": "cellarbrations",
                    "url": _product_url(prod, store_id),
                    "store_id": store_id,
                }

    result = list(all_products.values())
    log.info("Cellarbrations scrape complete: %d unique products", len(result))
    return result
