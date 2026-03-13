"""
Local sourcing — finds nearby merchants stocking a given wine.

Sorting formula
---------------
R = D_km × 10 + P_USD

Distance is always the dominant factor. Price is a tiebreaker.
Lower R = better result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Merchant:
    name: str
    address: str
    lat: float
    lng: float
    price_usd: float
    wines: dict[str, str] = field(default_factory=dict)  # variety → brand


@dataclass
class MerchantResult:
    merchant: Merchant
    brand: str
    distance_km: float
    score: float          # R = D_km × 10 + P_USD


# ---------------------------------------------------------------------------
# Mock merchant catalog — Adelaide, South Australia
# (Replace with DB query in production — the Wizard knows this is temporary)
# ---------------------------------------------------------------------------

MERCHANT_CATALOG: list[Merchant] = [
    Merchant(
        name="Vintage Cellars Rundle Mall",
        address="Rundle Mall, Adelaide CBD",
        lat=-34.9214, lng=138.6010,
        price_usd=19.99,
        wines={
            "Sauvignon Blanc": "Shaw + Smith",
            "Chardonnay":      "Leeuwin Estate",
            "Pinot Grigio":    "Grosset",
            "Riesling":        "Henschke",
        },
    ),
    Merchant(
        name="Dan Murphy's Adelaide City",
        address="76 Grote Street, Adelaide CBD",
        lat=-34.9290, lng=138.5986,
        price_usd=14.99,
        wines={
            "Cabernet Sauvignon": "Penfolds Bin 407",
            "Malbec":             "Zuccardi Valle",
            "Syrah/Shiraz":       "Wolf Blass Gold Label",
            "Chardonnay":         "Wolf Blass",
            "Pinot Noir":         "Yering Station",
        },
    ),
    Merchant(
        name="BWS Norwood",
        address="175 The Parade, Norwood",
        lat=-34.9218, lng=138.6302,
        price_usd=12.99,
        wines={
            "Sauvignon Blanc": "Jacob's Creek",
            "Pinot Grigio":    "Banrock Station",
            "Riesling":        "Peter Lehmann",
            "Malbec":          "Angove",
        },
    ),
    Merchant(
        name="Cellar One Unley",
        address="204 Unley Road, Unley",
        lat=-34.9418, lng=138.5987,
        price_usd=24.99,
        wines={
            "Pinot Noir":         "Grosset",
            "Chardonnay":         "Petaluma",
            "Riesling":           "Grosset Polish Hill",
            "Cabernet Sauvignon": "Wynns Coonawarra",
        },
    ),
    Merchant(
        name="First Choice Liquor Glenelg",
        address="Jetty Road, Glenelg",
        lat=-34.9800, lng=138.5161,
        price_usd=16.99,
        wines={
            "Syrah/Shiraz":    "d'Arenberg The Footbolt",
            "Malbec":          "Catena Zapata",
            "Sauvignon Blanc": "Wirra Wirra",
            "Pinot Grigio":    "Banrock Station",
        },
    ),
    Merchant(
        name="Barossa Fine Wines",
        address="Shop 12, Burnside Village",
        lat=-34.9277, lng=138.6598,
        price_usd=29.99,
        wines={
            "Syrah/Shiraz":       "Penfolds RWT",
            "Cabernet Sauvignon": "Penfolds Bin 389",
            "Riesling":           "Yalumba",
            "Chardonnay":         "Petaluma Hanlin Hill",
            "Pinot Noir":         "Bass Phillip Premium",
            "Sauvignon Blanc":    "Dog Point",
            "Pinot Grigio":       "Timo Mayer",
            "Malbec":             "Clos de los Siete",
        },
    ),
    Merchant(
        name="Adelaide Wine Centre",
        address="14 Gouger Street, Adelaide CBD",
        lat=-34.9268, lng=138.5999,
        price_usd=59.99,
        wines={
            "Pinot Noir":         "Henschke Giles",
            "Chardonnay":         "Leeuwin Estate Art Series",
            "Riesling":           "Grosset Polish Hill",
            "Syrah/Shiraz":       "Henschke Hill of Grace",
            "Cabernet Sauvignon": "Penfolds Bin 707",
            "Sauvignon Blanc":    "Shaw + Smith Single Vineyard",
            "Malbec":             "Achaval Ferrer",
            "Pinot Grigio":       "Jermann",
        },
    ),
    Merchant(
        name="Liquorland Prospect",
        address="Prospect Road, Prospect",
        lat=-34.8878, lng=138.5997,
        price_usd=13.99,
        wines={
            "Pinot Noir":      "Squealing Pig",
            "Sauvignon Blanc": "Oyster Bay",
            "Malbec":          "Angove",
            "Pinot Grigio":    "Jacob's Creek",
        },
    ),
    Merchant(
        name="The Wine Collective Henley Beach",
        address="Henley Beach Road, Henley Beach",
        lat=-34.9199, lng=138.4998,
        price_usd=22.99,
        wines={
            "Chardonnay":  "Yalumba",
            "Riesling":    "Jim Barry The Florita",
            "Sauvignon Blanc": "Wirra Wirra Mrs Wigley",
            "Syrah/Shiraz":    "Turkey Flat",
        },
    ),
]


# ---------------------------------------------------------------------------
# Distance + sorting
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two GPS coordinates in kilometres."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearby(
    wine_name: str,
    user_lat: float,
    user_lng: float,
    budget_min: float = 0.0,
    budget_max: float = 9999.0,
) -> list[MerchantResult]:
    """
    Return merchants stocking wine_name within budget, sorted by R = D_km × 10 + P_USD.
    Distance is always the dominant factor.
    """
    results: list[MerchantResult] = []

    for merchant in MERCHANT_CATALOG:
        if wine_name not in merchant.wines:
            continue
        if not (budget_min <= merchant.price_usd <= budget_max):
            continue
        brand = merchant.wines[wine_name]
        d = haversine_km(user_lat, user_lng, merchant.lat, merchant.lng)
        r = d * 10 + merchant.price_usd
        results.append(MerchantResult(merchant=merchant, brand=brand, distance_km=round(d, 2), score=round(r, 2)))

    results.sort(key=lambda x: x.score)
    return results
