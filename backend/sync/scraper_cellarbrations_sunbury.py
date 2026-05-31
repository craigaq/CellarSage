"""
Cellarbrations Sunbury scraper — single-store pilot for VIC beta testers.

Store: CELLARBRATIONS AT THE LOCAL SUNBURY
Store ID: 99839
Coordinates: -37.5791, 144.7494
"""

import json
import ssl
import logging
import urllib.parse
import urllib.request
import uuid
from typing import Optional

log = logging.getLogger(__name__)

_GW_BASE   = "https://storefrontgateway.cellarbrations.com.au"
_SITE_BASE = "https://www.cellarbrations.com.au"
_STORE_ID  = "99839"
_STORE_LAT = -37.57907399070393
_STORE_LNG = 144.74941778805461

_QUERIES = ["wine", "port", "sherry", "muscat", "botrytis", "fortified"]

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode    = ssl.CERT_NONE


def _headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":          "application/json, */*",
        "Accept-Language": "en-AU,en;q=0.9",
        "Origin":          _SITE_BASE,
        "Referer":         f"{_SITE_BASE}/wine",
        "X-Shopping-Mode": "22222222-2222-2222-2222-222222222222",
        "X-Site-Host":     _SITE_BASE,
        "X-Correlation-Id":       str(uuid.uuid4()),
        "x-customer-session-id":  f"{_SITE_BASE}|{uuid.uuid4()}",
        "X-Customer-Address-Latitude":  str(_STORE_LAT),
        "X-Customer-Address-Longitude": str(_STORE_LNG),
    }


def _fetch(url: str) -> Optional[dict]:
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=20, context=_ctx) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        log.warning("cellarbrations_sunbury: HTTP %d — %s", e.code, url)
    except Exception as e:
        log.warning("cellarbrations_sunbury: request error — %s", e)
    return None


def scrape_cellarbrations_sunbury() -> list[dict]:
    log.info("cellarbrations_sunbury: scraping store %s ...", _STORE_ID)

    seen_ids: set[str] = set()
    raw_products: list[dict] = []

    for term in _QUERIES:
        url = (
            f"{_GW_BASE}/api/stores/{_STORE_ID}/preview"
            f"?q={urllib.parse.quote(term)}&productsTake=1000"
        )
        data = _fetch(url)
        if not data:
            continue
        for p in data.get("products") or []:
            pid = str(p.get("productId", ""))
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                raw_products.append(p)

    log.info("cellarbrations_sunbury: %d unique products fetched", len(raw_products))

    results: list[dict] = []
    for p in raw_products:
        name = (p.get("name") or "").strip()
        if not name:
            continue

        price_raw = (p.get("price") or "").replace("$", "").strip()
        try:
            price = float(price_raw)
        except ValueError:
            continue
        if price <= 0:
            continue

        # Store-scoped buy URL — takes user directly to this wine at the Sunbury store
        buy_url = (
            f"{_SITE_BASE}/search"
            f"?q={urllib.parse.quote(name)}"
            f"&storeId={_STORE_ID}"
        )

        results.append({
            "name":     name,
            "price":    price,
            "url":      buy_url,
            "retailer": "cellarbrations_sunbury",
            "store_id": _STORE_ID,
            "varietal": None,
            "vendor":   (p.get("brand") or "").strip(),
        })

    log.info("cellarbrations_sunbury: %d wine products ready", len(results))
    return results
