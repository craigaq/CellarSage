"""Porters Liquor scraper — thin wrapper around the generic WYNSHOP scraper."""

from .scraper_wynshop import scrape_wynshop

_GW_BASE   = "https://storefrontgateway.portersliquor.com.au"
_SITE_BASE = "https://www.portersliquor.com.au"


def scrape_portersliquor() -> list[dict]:
    return scrape_wynshop(
        gateway_base=_GW_BASE,
        site_base=_SITE_BASE,
        retailer="portersliquor",
    )
