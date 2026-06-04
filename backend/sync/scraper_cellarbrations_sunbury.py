"""
Cellarbrations Sunbury scraper — single-store pilot for VIC beta testers.

Store: CELLARBRATIONS AT THE LOCAL SUNBURY
Store ID: 99839
Coordinates: -37.5791, 144.7494
"""

import gzip
import json
import random
import ssl
import logging
import time
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

# Rotate through realistic Chrome versions to avoid UA fingerprinting
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
]

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode    = ssl.CERT_NONE


def _headers() -> dict:
    return {
        "User-Agent":       random.choice(_USER_AGENTS),
        "Accept":           "application/json, text/plain, */*",
        "Accept-Language":  "en-AU,en-GB;q=0.9,en;q=0.8",
        "Accept-Encoding":  "gzip, deflate, br",
        "Origin":           _SITE_BASE,
        "Referer":          f"{_SITE_BASE}/wine",
        "Cache-Control":    "no-cache",
        "Pragma":           "no-cache",
        "X-Shopping-Mode":  "22222222-2222-2222-2222-222222222222",
        "X-Site-Host":      _SITE_BASE,
        "X-Correlation-Id":       str(uuid.uuid4()),
        "x-customer-session-id":  f"{_SITE_BASE}|{uuid.uuid4()}",
        "X-Customer-Address-Latitude":  str(_STORE_LAT),
        "X-Customer-Address-Longitude": str(_STORE_LNG),
    }


def _fetch(url: str) -> Optional[dict]:
    # Use a cookie-enabled opener so session cookies are preserved across requests
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    req = urllib.request.Request(url, headers=_headers())
    try:
        with opener.open(req, timeout=20) as r:
            raw = r.read()
            # Decompress gzip if the response is compressed
            if raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        log.warning("cellarbrations_sunbury: HTTP %d — %s", e.code, url)
    except Exception as e:
        log.warning("cellarbrations_sunbury: request error — %s", e)
    return None


def scrape_cellarbrations_sunbury() -> list[dict]:
    log.info("cellarbrations_sunbury: scraping store %s ...", _STORE_ID)

    seen_ids: set[str] = set()
    raw_products: list[dict] = []

    for i, term in enumerate(_QUERIES):
        # Polite delay between requests — 2-4 seconds randomised
        if i > 0:
            time.sleep(random.uniform(2.0, 4.0))

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
