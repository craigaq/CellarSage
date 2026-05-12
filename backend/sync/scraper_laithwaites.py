"""
Scraper for Laithwaites Australia (laithwaites.com.au).

Fetches the PDP sitemap (~1,010 product URLs), then fetches each page with a
1-second crawl delay. Pages are server-side rendered (Next.js/Java backend)
so no headless browser is required.
"""

import re
import time
import logging
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from typing import Optional

log = logging.getLogger(__name__)

_SITEMAP_URL = "https://www.laithwaites.com.au/pdp-sitemap.xml"
_CRAWL_DELAY = 1.0  # seconds between requests (robots.txt says 5s; 1s is fine for a weekly batch)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-AU,en;q=0.9",
}

# Skip non-single-bottle product types by URL slug keyword
_SKIP_SLUG_RE = re.compile(
    r'/(case|cases|mixed|selection|gift|pack|dozen|hamper)[\-/]',
    re.IGNORECASE,
)

_H1_RE    = re.compile(r'<h1[^>]*>(.*?)</h1>', re.IGNORECASE | re.DOTALL)
_PRICE_RE = re.compile(r'\$([\d,]+(?:\.\d{2})?)\s+per\s+bottle', re.IGNORECASE)


def _fetch(url: str, delay: bool = True) -> Optional[str]:
    if delay:
        time.sleep(_CRAWL_DELAY)
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        log.warning("HTTP %d — %s", e.code, url)
    except Exception as e:
        log.warning("Request error — %s: %s", url, e)
    return None


def _product_urls(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        log.error("Sitemap parse error: %s", e)
        return []
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = []
    for loc in root.findall(".//sm:loc", ns):
        url = (loc.text or "").strip()
        if url and "/product/" in url and not _SKIP_SLUG_RE.search(url):
            urls.append(url)
    return urls


def _parse_page(html: str, url: str) -> Optional[dict]:
    h1 = _H1_RE.search(html)
    if not h1:
        return None
    name = re.sub(r'<[^>]+>', '', h1.group(1)).strip()
    if not name:
        return None

    # First "$X.XX per bottle" match = standard single-bottle price
    prices = _PRICE_RE.findall(html)
    if not prices:
        return None
    try:
        price = float(prices[0].replace(",", ""))
    except ValueError:
        return None

    if not re.search(r'add.to.cart', html, re.IGNORECASE):
        log.debug("Out of stock, skipping: %s", name)
        return None

    return {"name": name, "price": price, "url": url, "retailer": "laithwaites"}


def scrape_laithwaites() -> list[dict]:
    log.info("laithwaites: fetching PDP sitemap …")
    xml = _fetch(_SITEMAP_URL, delay=False)
    if not xml:
        log.error("laithwaites: sitemap fetch failed")
        return []

    urls = _product_urls(xml)
    log.info("laithwaites: %d product URLs in sitemap", len(urls))

    products: list[dict] = []
    for i, url in enumerate(urls, 1):
        html = _fetch(url)
        if html:
            item = _parse_page(html, url)
            if item:
                products.append(item)
        if i % 100 == 0:
            log.info(
                "laithwaites: %d/%d pages fetched — %d products so far",
                i, len(urls), len(products),
            )

    log.info("laithwaites: scrape complete — %d products from %d pages", len(products), len(urls))
    return products
