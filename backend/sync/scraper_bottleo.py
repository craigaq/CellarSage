"""The Bottle-O scraper — thin wrapper around the generic WYNSHOP scraper.

The Bottle-O is a click-and-collect chain (no delivery). Its store list is
returned in one call via /api/stores rather than the delivery-scoped endpoint.
"""

from .scraper_wynshop import scrape_wynshop

_GW_BASE   = "https://storefrontgateway.thebottle-o.com.au"
_SITE_BASE = "https://www.thebottle-o.com.au"


def scrape_bottleo() -> list[dict]:
    return scrape_wynshop(
        gateway_base=_GW_BASE,
        site_base=_SITE_BASE,
        retailer="bottleo",
        all_stores=True,
    )
