"""
Local sourcing — finds nearby merchants stocking a given wine.

Unicorn Vintage Trap ranking formula
--------------------------------------
avg  = average price across all catalog merchants stocking the wine
ceil = avg × 1.25  (25% price variance ceiling)

If price ≤ ceil  →  R = D_km × 10  + P_AUD              (distance dominant)
If price > ceil  →  R = D_km × 1   + P_AUD + (P/avg)×50  (greed penalty kicks in)

Lower R = better result.

Triple-Region Tier system
--------------------------
Every wine bottle is classified into one of three geographic tiers based on
its production region.  The middleware uses these tiers to surface one best
match per tier for every recommendation.

  Tier 1 — The Local Hero      Adelaide Hills, McLaren Vale, Barossa Valley (SA)
  Tier 2 — The National Rival  Yarra Valley, Margaret River, Hunter Valley (interstate AU)
  Tier 3 — The Global Icon     France, Italy, USA, NZ, Argentina, Spain … (international)

Pricing Precedent (enforced by the interceptor):
  Tier 3 is suppressed when its cheapest option exceeds 5× the cheapest Tier 1 price,
  unless the user explicitly requests it via show_global_tier=True.

Commercial Group system
------------------------
Every merchant belongs to a commercial_group:
  "endeavour"   — Dan Murphy's, BWS  (Endeavour Group ASX: EDV)
  "coles_liquor"— Liquorland, Liquorland Cellars, Liquorland Warehouse (Coles Group)
  "independent" — East End Cellars, Fassina Liquor, Cellarbrations
  "online"      — Vinomofo, Naked Wines, The Wine Collective, Wine Selectors, etc.

When a preferred_partner is set in PARTNER_CONFIG, that group's results are
boosted in ranking and competitor group results are filtered out.  All boosted
results carry a [Partner] badge in the UI (disclosed to users).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from db_catalog import get_cheapest_by_varietal

log = logging.getLogger("cellar_sage.sourcing")


# ---------------------------------------------------------------------------
# Partner configuration — set commercial_group to activate boost + exclusion
# ---------------------------------------------------------------------------
# Leave preferred_partner as None for neutral / no-deal operation.
# Set to "endeavour" or "coles_liquor" when a commercial agreement is active.
# "independent" and "online" groups are never excluded (they have no competitor
# relationship with retail chains and their presence improves result quality).
#
PARTNER_CONFIG: dict = {
    "preferred_partner": None,      # None | "endeavour" | "coles_liquor"
    "partner_rank_boost": 0.25,     # Subtract from rank score (lower = better)
    "exclude_rival_group": True,    # When True, rival chain group is hidden
}

# Map of rival pairs — when one group is preferred, the other is excluded
_RIVAL_GROUPS: dict[str, str] = {
    "endeavour":   "coles_liquor",
    "coles_liquor": "endeavour",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class WineProduct:
    """A specific wine bottle stocked by a merchant.

    brand     : Producer / label name  (e.g., "Penfolds RWT").
    region    : Wine's production region (e.g., "Barossa Valley, SA").
                Used to classify the bottle into a geographic tier.
    price_aud : Actual retail price of this specific wine.  Overrides the
                merchant's flat price_aud when set.  0.0 = use merchant default.
    """
    brand:     str
    region:    str
    price_aud: float = 0.0


@dataclass
class Merchant:
    name:               str
    address:            str
    lat:                float
    lng:                float
    price_aud:          float
    commercial_group:   str   = "independent"  # endeavour | coles_liquor | independent | online
    search_url_template: str  = ""             # URL with {brand} placeholder for deep-linking
    affiliate_url_template: str = ""           # Full affiliate tracking URL — overrides search_url_template
                                               # when set. Populated per merchant once affiliate
                                               # credentials are obtained. Supports {brand} placeholder.
    wines: dict[str, WineProduct] = field(default_factory=dict)  # variety → WineProduct
    data_source:        str   = "Scraped_Data" # Direct_API | Manual_Upload | Scraped_Data
    last_updated_hours: float = 48.0           # Hours since inventory feed was last refreshed
    is_online_only:     bool  = False          # True for delivery-only retailers


@dataclass
class MerchantResult:
    merchant:    Merchant
    brand:       str
    region:      str    # wine production region (from WineProduct)
    tier:        int    # 1 | 2 | 3 — geographic tier
    distance_km: float
    price_aud:   float = 0.0   # Resolved wine price: WineProduct.price_aud if set, else merchant default
    is_partner:  bool  = False  # True when merchant belongs to preferred_partner group
    # Fields below are populated by the middleware interceptor
    score:             float = 0.0
    confidence_score:  float = 0.0
    needs_verification: bool = False


# ---------------------------------------------------------------------------
# Geographic tier classification
# ---------------------------------------------------------------------------

TIER_LABELS: dict[int, str] = {
    1: "The Local Hero",
    2: "The Interstater",
    3: "The Global Icon",
}

TIER_REGION_HINTS: dict[int, str] = {
    1: "Adelaide Hills, McLaren Vale, Barossa Valley",
    2: "Yarra Valley (VIC), Margaret River (WA), Hunter Valley (NSW)",
    3: "France (Rhône/Bordeaux), Italy (Piedmont), USA (Napa/Oregon)",
}


def get_region_tier(region: str) -> int:
    """Return the geographic tier (1–3) for a wine's production region."""
    r = region.lower()
    if any(k in r for k in (
        "adelaide hills", "mclaren vale", "barossa", "clare valley",
        "eden valley", "coonawarra", "langhorne creek", "riverland",
        "padthaway", "wrattonbully", "south australia", ", sa",
    )):
        return 1
    if any(k in r for k in (
        "yarra valley", "mornington", "gippsland", "king valley",
        "grampians", "heathcote", "victoria", ", vic",
        "margaret river", "great southern", "swan valley",
        "western australia", ", wa",
        "hunter valley", "mudgee", "riverina", "orange",
        "new south wales", ", nsw",
        "canberra", "tasmania", ", tas",
        ", aus",
    )):
        return 2
    return 3


# ---------------------------------------------------------------------------
# Merchant catalog — Adelaide, South Australia
#
# Groups:
#   endeavour    — Dan Murphy's (9 SA stores), BWS (24 SA metro stores)
#   coles_liquor — Liquorland, Liquorland Cellars (ex-Vintage Cellars),
#                  Liquorland Warehouse (ex-First Choice)
#   independent  — East End Cellars, Fassina Liquor, Cellarbrations
#   online       — Vinomofo, Naked Wines, The Wine Collective, Wine Selectors,
#                  Just Wines, Laithwaites AU
#
# NOTE: All prices and stock are PLACEHOLDER values pending validator scrape.
#       The merchant_validator.py layer will replace price_aud with live values
#       and mark each entry as validated=True when confirmed on the merchant site.
# ---------------------------------------------------------------------------

MERCHANT_CATALOG: list[Merchant] = [

    # =========================================================================
    # ENDEAVOUR GROUP — Dan Murphy's
    # =========================================================================

    Merchant(
        name="Dan Murphy's Adelaide City",
        address="76 Grote Street, Adelaide CBD, SA 5000",
        lat=-34.9290, lng=138.5986,
        price_aud=23.99,
        commercial_group="endeavour",
        search_url_template="https://www.danmurphys.com.au/search?searchTerm={brand}",
        wines={
            "Cabernet Sauvignon": WineProduct("Penfolds Bin 407",              "Barossa Valley, SA",  price_aud=68.00),
            "Malbec":             WineProduct("Zuccardi Valle",                "Mendoza, Argentina",  price_aud=28.00),
            "Syrah/Shiraz":       WineProduct("Wolf Blass Gold Label",         "Barossa Valley, SA",  price_aud=28.00),
            "Chardonnay":         WineProduct("Wolf Blass",                    "Barossa Valley, SA",  price_aud=18.00),
            "Pinot Noir":         WineProduct("Yering Station",                "Yarra Valley, VIC",   price_aud=38.00),
            "Merlot":             WineProduct("Penfolds Thomas Hyland",        "Barossa Valley, SA",  price_aud=25.00),
            "Grenache":           WineProduct("d'Arenberg The Stump Jump",     "McLaren Vale, SA",    price_aud=20.00),
            "Red Blend":          WineProduct("d'Arenberg The Stump Jump GSM", "McLaren Vale, SA",    price_aud=20.00),
            "Zinfandel":          WineProduct("Ravenswood Vintners Blend",     "Sonoma, USA",         price_aud=22.00),
        },
        data_source="Direct_API",
        last_updated_hours=0.25,
    ),

    Merchant(
        name="Dan Murphy's Marion",
        address="297 Diagonal Road, Oaklands Park, SA 5046",
        lat=-35.0140, lng=138.5504,
        price_aud=23.99,
        commercial_group="endeavour",
        search_url_template="https://www.danmurphys.com.au/search?searchTerm={brand}",
        wines={
            "Cabernet Sauvignon":    WineProduct("Penfolds Bin 407",           "Barossa Valley, SA",          price_aud=68.00),
            "Syrah/Shiraz":          WineProduct("Penfolds RWT",               "Barossa Valley, SA",          price_aud=175.00),
            "Chardonnay":            WineProduct("Petaluma",                   "Adelaide Hills, SA",          price_aud=32.00),
            "Pinot Noir":            WineProduct("Yering Station",             "Yarra Valley, VIC",           price_aud=38.00),
            "Malbec":                WineProduct("Zuccardi Valle",             "Mendoza, Argentina",          price_aud=28.00),
            "Sauvignon Blanc":       WineProduct("Shaw + Smith",               "Adelaide Hills, SA",          price_aud=32.00),
            "Riesling":              WineProduct("Henschke",                   "Eden Valley, SA",             price_aud=32.00),
            "Red Blend":             WineProduct("Penfolds Bin 138 GSM",       "Barossa Valley, SA",          price_aud=32.00),
            "Grenache":              WineProduct("d'Arenberg The Stump Jump",  "McLaren Vale, SA",            price_aud=20.00),
            "Tempranillo":           WineProduct("Bodegas Muga Rioja Reserva", "Rioja, Spain",                price_aud=38.00),
            "Sangiovese":            WineProduct("Antinori Tignanello",        "Tuscany, Italy",              price_aud=130.00),
            "Zinfandel":             WineProduct("Ravenswood Vintners Blend",  "Sonoma, USA",                 price_aud=22.00),
            "Gewürztraminer (Dry)":  WineProduct("Trimbach Alsace",            "Alsace, France",              price_aud=42.00),
            "Grüner Veltliner":      WineProduct("Domäne Wachau Federspiel",   "Wachau, Austria",             price_aud=32.00),
            "Chenin Blanc (Dry)":    WineProduct("Ken Forrester Petit Chenin", "Stellenbosch, South Africa",  price_aud=22.00),
        },
        data_source="Direct_API",
        last_updated_hours=0.5,
    ),

    Merchant(
        name="Dan Murphy's Torrensville",
        address="38A South Road, Torrensville, SA 5031",
        lat=-34.9380, lng=138.5620,
        price_aud=23.99,
        commercial_group="endeavour",
        search_url_template="https://www.danmurphys.com.au/search?searchTerm={brand}",
        wines={
            "Cabernet Sauvignon": WineProduct("Wynns Black Label",            "Coonawarra, SA",              price_aud=42.00),
            "Syrah/Shiraz":       WineProduct("Penfolds St Henri",            "Barossa Valley, SA",          price_aud=95.00),
            "Pinot Noir":         WineProduct("Stonier Reserve",              "Mornington Peninsula, VIC",   price_aud=38.00),
            "Sauvignon Blanc":    WineProduct("Shaw + Smith",                 "Adelaide Hills, SA",          price_aud=32.00),
            "Chardonnay":         WineProduct("Leeuwin Estate Art Series",    "Margaret River, WA",          price_aud=95.00),
            "Riesling":           WineProduct("Grosset Polish Hill",          "Clare Valley, SA",            price_aud=65.00),
            "Merlot":             WineProduct("Penfolds Thomas Hyland",       "Barossa Valley, SA",          price_aud=25.00),
            "Red Blend":          WineProduct("Penfolds Bin 138 GSM",         "Barossa Valley, SA",          price_aud=32.00),
            "Tempranillo":        WineProduct("Torres Gran Sangre de Toro",   "Catalunya, Spain",            price_aud=22.00),
            "Viognier (Dry)":     WineProduct("Yalumba Eden Valley Viognier", "Eden Valley, SA",             price_aud=22.00),
        },
        data_source="Direct_API",
        last_updated_hours=1.0,
    ),

    Merchant(
        name="Dan Murphy's Marden",
        address="9 Lower Portrush Road, Marden, SA 5070",
        lat=-34.9050, lng=138.6410,
        price_aud=23.99,
        commercial_group="endeavour",
        search_url_template="https://www.danmurphys.com.au/search?searchTerm={brand}",
        wines={
            "Cabernet Sauvignon": WineProduct("Katnook Estate",               "Coonawarra, SA",              price_aud=32.00),
            "Syrah/Shiraz":       WineProduct("Langmeil Freedom",             "Barossa Valley, SA",          price_aud=38.00),
            "Grenache":           WineProduct("Yangarra Old Vine",            "McLaren Vale, SA",            price_aud=38.00),
            "Sauvignon Blanc":    WineProduct("Wirra Wirra Mrs Wigley",       "McLaren Vale, SA",            price_aud=22.00),
            "Chardonnay":         WineProduct("Grosset Piccadilly",           "Adelaide Hills, SA",          price_aud=50.00),
            "Pinot Grigio":       WineProduct("Heemskerk",                    "Tasmania, TAS",               price_aud=22.00),
            "Malbec":             WineProduct("Achaval Ferrer",               "Mendoza, Argentina",          price_aud=38.00),
            "Sangiovese":         WineProduct("Coriole",                      "McLaren Vale, SA",            price_aud=28.00),
        },
        data_source="Direct_API",
        last_updated_hours=1.5,
    ),

    Merchant(
        name="Dan Murphy's Gilles Plains",
        address="575 North East Road, Gilles Plains, SA 5086",
        lat=-34.8500, lng=138.6500,
        price_aud=23.99,
        commercial_group="endeavour",
        search_url_template="https://www.danmurphys.com.au/search?searchTerm={brand}",
        wines={
            "Cabernet Sauvignon": WineProduct("Penfolds Bin 407",             "Barossa Valley, SA",  price_aud=68.00),
            "Syrah/Shiraz":       WineProduct("Wolf Blass Gold Label",        "Barossa Valley, SA",  price_aud=28.00),
            "Pinot Noir":         WineProduct("Yering Station",               "Yarra Valley, VIC",   price_aud=38.00),
            "Sauvignon Blanc":    WineProduct("Shaw + Smith",                 "Adelaide Hills, SA",  price_aud=32.00),
            "Chardonnay":         WineProduct("Wolf Blass",                   "Barossa Valley, SA",  price_aud=18.00),
            "Riesling":           WineProduct("Henschke",                     "Eden Valley, SA",     price_aud=32.00),
            "Grenache":           WineProduct("d'Arenberg The Stump Jump",    "McLaren Vale, SA",    price_aud=20.00),
            "Malbec":             WineProduct("Zuccardi Valle",               "Mendoza, Argentina",  price_aud=28.00),
        },
        data_source="Direct_API",
        last_updated_hours=2.0,
    ),

    # =========================================================================
    # ENDEAVOUR GROUP — BWS
    # =========================================================================

    Merchant(
        name="BWS Norwood",
        address="175 The Parade, Norwood, SA 5067",
        lat=-34.9218, lng=138.6302,
        price_aud=20.99,
        commercial_group="endeavour",
        search_url_template="https://www.bws.com.au/search?q={brand}",
        wines={
            "Sauvignon Blanc":   WineProduct("Jacob's Creek",                      "Barossa Valley, SA",  price_aud=14.00),
            "Pinot Grigio":      WineProduct("Banrock Station",                    "Riverland, SA",       price_aud=12.00),
            "Riesling":          WineProduct("Peter Lehmann",                      "Barossa Valley, SA",  price_aud=19.00),
            "Malbec":            WineProduct("Angove",                             "McLaren Vale, SA",    price_aud=18.00),
            "Merlot":            WineProduct("Jacob's Creek Classic",              "Barossa Valley, SA",  price_aud=14.00),
            "Tempranillo":       WineProduct("Angove Long Row",                    "McLaren Vale, SA",    price_aud=15.00),
            "Carménère":         WineProduct("Concha y Toro Casillero del Diablo", "Maipo Valley, Chile", price_aud=16.00),
            "Trebbiano Toscano": WineProduct("Berton Vineyard",                    "Riverina, NSW",       price_aud=14.00),
        },
        data_source="Direct_API",
        last_updated_hours=2.0,
    ),

    Merchant(
        name="BWS Burnside",
        address="447 Portrush Road, Burnside, SA 5066",
        lat=-34.9277, lng=138.6598,
        price_aud=22.99,
        commercial_group="endeavour",
        search_url_template="https://www.bws.com.au/search?q={brand}",
        wines={
            "Syrah/Shiraz":       WineProduct("Penfolds Koonunga Hill",         "Barossa Valley, SA",  price_aud=20.00),
            "Cabernet Sauvignon": WineProduct("Wolf Blass Yellow Label",        "Barossa Valley, SA",  price_aud=18.00),
            "Riesling":           WineProduct("Yalumba",                        "Eden Valley, SA",     price_aud=18.00),
            "Chardonnay":         WineProduct("Wolf Blass Yellow Label",        "Barossa Valley, SA",  price_aud=18.00),
            "Pinot Noir":         WineProduct("Squealing Pig",                  "Marlborough, NZ",     price_aud=18.00),
            "Sauvignon Blanc":    WineProduct("Jacob's Creek",                  "Barossa Valley, SA",  price_aud=14.00),
            "Pinot Grigio":       WineProduct("Banrock Station",                "Riverland, SA",       price_aud=12.00),
            "Malbec":             WineProduct("Angove",                         "McLaren Vale, SA",    price_aud=18.00),
            "Red Blend":          WineProduct("19 Crimes",                      "Victoria, AUS",       price_aud=18.00),
            "Grenache":           WineProduct("d'Arenberg The Stump Jump",      "McLaren Vale, SA",    price_aud=20.00),
        },
        data_source="Direct_API",
        last_updated_hours=3.0,
    ),

    Merchant(
        name="BWS Unley",
        address="204 Unley Road, Unley, SA 5061",
        lat=-34.9418, lng=138.5987,
        price_aud=20.99,
        commercial_group="endeavour",
        search_url_template="https://www.bws.com.au/search?q={brand}",
        wines={
            "Sauvignon Blanc":    WineProduct("Jacob's Creek",             "Barossa Valley, SA",  price_aud=14.00),
            "Chardonnay":         WineProduct("Wolf Blass Yellow Label",   "Barossa Valley, SA",  price_aud=18.00),
            "Pinot Grigio":       WineProduct("Banrock Station",           "Riverland, SA",       price_aud=12.00),
            "Merlot":             WineProduct("Jacob's Creek Classic",     "Barossa Valley, SA",  price_aud=14.00),
            "Cabernet Sauvignon": WineProduct("Wolf Blass Yellow Label",   "Barossa Valley, SA",  price_aud=18.00),
            "Riesling":           WineProduct("Peter Lehmann",             "Barossa Valley, SA",  price_aud=19.00),
            "Pinot Noir":         WineProduct("Squealing Pig",             "Marlborough, NZ",     price_aud=18.00),
        },
        data_source="Direct_API",
        last_updated_hours=4.0,
    ),

    Merchant(
        name="BWS Glenelg",
        address="Bayside Village, 1 Colley Terrace, Glenelg, SA 5045",
        lat=-34.9802, lng=138.5154,
        price_aud=20.99,
        commercial_group="endeavour",
        search_url_template="https://www.bws.com.au/search?q={brand}",
        wines={
            "Sauvignon Blanc":    WineProduct("Jacob's Creek",            "Barossa Valley, SA",  price_aud=14.00),
            "Pinot Grigio":       WineProduct("Banrock Station",          "Riverland, SA",       price_aud=12.00),
            "Merlot":             WineProduct("Jacob's Creek Classic",    "Barossa Valley, SA",  price_aud=14.00),
            "Cabernet Sauvignon": WineProduct("Wolf Blass Yellow Label",  "Barossa Valley, SA",  price_aud=18.00),
            "Riesling":           WineProduct("Peter Lehmann",            "Barossa Valley, SA",  price_aud=19.00),
            "Syrah/Shiraz":       WineProduct("Penfolds Koonunga Hill",   "Barossa Valley, SA",  price_aud=20.00),
            "Grenache":           WineProduct("d'Arenberg The Stump Jump","McLaren Vale, SA",    price_aud=20.00),
        },
        data_source="Direct_API",
        last_updated_hours=4.0,
    ),

    Merchant(
        name="BWS North Adelaide",
        address="86 O'Connell Street, North Adelaide, SA 5006",
        lat=-34.9058, lng=138.5941,
        price_aud=20.99,
        commercial_group="endeavour",
        search_url_template="https://www.bws.com.au/search?q={brand}",
        wines={
            "Pinot Noir":         WineProduct("Squealing Pig",            "Marlborough, NZ",     price_aud=18.00),
            "Chardonnay":         WineProduct("Wolf Blass Yellow Label",  "Barossa Valley, SA",  price_aud=18.00),
            "Sauvignon Blanc":    WineProduct("Oyster Bay",               "Marlborough, NZ",     price_aud=18.00),
            "Riesling":           WineProduct("Peter Lehmann",            "Barossa Valley, SA",  price_aud=19.00),
            "Cabernet Sauvignon": WineProduct("Wynns Coonawarra",         "Coonawarra, SA",      price_aud=22.00),
            "Syrah/Shiraz":       WineProduct("Penfolds Koonunga Hill",   "Barossa Valley, SA",  price_aud=20.00),
            "Malbec":             WineProduct("Angove",                   "McLaren Vale, SA",    price_aud=18.00),
        },
        data_source="Direct_API",
        last_updated_hours=3.0,
    ),

    # =========================================================================
    # COLES LIQUOR GROUP — Liquorland
    # =========================================================================

    Merchant(
        name="Liquorland Prospect",
        address="253 Prospect Road, Prospect, SA 5082",
        lat=-34.8878, lng=138.5997,
        price_aud=21.99,
        commercial_group="coles_liquor",
        search_url_template="https://www.liquorland.com.au/search?q={brand}",
        wines={
            "Pinot Noir":             WineProduct("Squealing Pig",                      "Marlborough, NZ",     price_aud=18.00),
            "Sauvignon Blanc":        WineProduct("Oyster Bay",                         "Marlborough, NZ",     price_aud=18.00),
            "Malbec":                 WineProduct("Angove",                             "McLaren Vale, SA",    price_aud=18.00),
            "Pinot Grigio":           WineProduct("Jacob's Creek",                      "Barossa Valley, SA",  price_aud=14.00),
            "Merlot":                 WineProduct("Lindeman's Bin 40",                  "Coonawarra, SA",      price_aud=14.00),
            "Red Blend":              WineProduct("19 Crimes",                          "Victoria, AUS",       price_aud=18.00),
        },
        data_source="Direct_API",
        last_updated_hours=6.0,
    ),

    Merchant(
        name="Liquorland Unley",
        address="204 Unley Road, Unley, SA 5061",
        lat=-34.9418, lng=138.5987,
        price_aud=21.99,
        commercial_group="coles_liquor",
        search_url_template="https://www.liquorland.com.au/search?q={brand}",
        wines={
            "Pinot Noir":         WineProduct("Squealing Pig",          "Marlborough, NZ",     price_aud=18.00),
            "Chardonnay":         WineProduct("Wolf Blass Yellow Label", "Barossa Valley, SA",  price_aud=18.00),
            "Riesling":           WineProduct("Peter Lehmann",           "Barossa Valley, SA",  price_aud=19.00),
            "Cabernet Sauvignon": WineProduct("Wynns Coonawarra",        "Coonawarra, SA",      price_aud=22.00),
            "Sauvignon Blanc":    WineProduct("Oyster Bay",              "Marlborough, NZ",     price_aud=18.00),
            "Syrah/Shiraz":       WineProduct("Penfolds Koonunga Hill",  "Barossa Valley, SA",  price_aud=20.00),
        },
        data_source="Direct_API",
        last_updated_hours=6.0,
    ),

    Merchant(
        name="Liquorland Marion",
        address="Westfield Marion, 297 Diagonal Road, Oaklands Park, SA 5046",
        lat=-35.0130, lng=138.5510,
        price_aud=21.99,
        commercial_group="coles_liquor",
        search_url_template="https://www.liquorland.com.au/search?q={brand}",
        wines={
            "Cabernet Sauvignon": WineProduct("Wynns Black Label",       "Coonawarra, SA",      price_aud=42.00),
            "Syrah/Shiraz":       WineProduct("Geoff Merrill",           "McLaren Vale, SA",    price_aud=28.00),
            "Sauvignon Blanc":    WineProduct("Oyster Bay",              "Marlborough, NZ",     price_aud=18.00),
            "Chardonnay":         WineProduct("Squealing Pig",           "Marlborough, NZ",     price_aud=18.00),
            "Pinot Noir":         WineProduct("Squealing Pig",           "Marlborough, NZ",     price_aud=18.00),
            "Merlot":             WineProduct("Lindeman's Bin 40",       "Coonawarra, SA",      price_aud=14.00),
            "Grenache":           WineProduct("d'Arenberg The Stump Jump","McLaren Vale, SA",   price_aud=20.00),
            "Riesling":           WineProduct("Wolf Blass Yellow Label",  "Barossa Valley, SA", price_aud=18.00),
        },
        data_source="Direct_API",
        last_updated_hours=8.0,
    ),

    # =========================================================================
    # COLES LIQUOR GROUP — Liquorland Cellars (ex-Vintage Cellars, rebranded 2025)
    # =========================================================================

    Merchant(
        name="Liquorland Cellars Hutt Street",
        address="143 Hutt Street, Adelaide SA 5000",
        lat=-34.9311, lng=138.6078,
        price_aud=33.99,
        commercial_group="coles_liquor",
        search_url_template="https://www.liquorland.com.au/search?q={brand}",
        wines={
            "Chardonnay":            WineProduct("Yalumba",                    "Eden Valley, SA",             price_aud=25.00),
            "Riesling":              WineProduct("Jim Barry The Florita",      "Clare Valley, SA",            price_aud=55.00),
            "Sauvignon Blanc":       WineProduct("Wirra Wirra Mrs Wigley",     "McLaren Vale, SA",            price_aud=22.00),
            "Syrah/Shiraz":          WineProduct("Turkey Flat",                "Barossa Valley, SA",          price_aud=38.00),
            "Pinot Noir":            WineProduct("Leeuwin Estate Art Series",  "Margaret River, WA",          price_aud=95.00),
            "Merlot":                WineProduct("Duckhorn Napa Valley Merlot", "Napa Valley, USA",            price_aud=65.00),
            "Malbec":                WineProduct("Achaval Ferrer",             "Mendoza, Argentina",          price_aud=38.00),
            "Pinot Grigio":          WineProduct("Jermann",                    "Friuli, Italy",               price_aud=45.00),
            "Gewürztraminer (Dry)":  WineProduct("Zind-Humbrecht Alsace",      "Alsace, France",              price_aud=65.00),
            "Grüner Veltliner":      WineProduct("Nikolaihof Wachau Reserve",  "Wachau, Austria",             price_aud=55.00),
            "Chenin Blanc (Dry)":    WineProduct("Champalou Vouvray Sec",      "Loire Valley, France",        price_aud=38.00),
            "Chenin Blanc":          WineProduct("Mullineux Old Vines",        "Swartland, South Africa",     price_aud=45.00),
            "Tempranillo":           WineProduct("Torres Gran Coronas Reserva", "Penedès, Spain",             price_aud=35.00),
            "Sangiovese":            WineProduct("Antinori Chianti Classico Riserva", "Tuscany, Italy",       price_aud=55.00),
            "Zinfandel":             WineProduct("Ridge Three Valleys Zinfandel", "Sonoma, USA",              price_aud=45.00),
            "Carménère":             WineProduct("Casa Lapostolle Cuvée Alexandre", "Colchagua Valley, Chile", price_aud=35.00),
            "Viognier (Dry)":        WineProduct("Yalumba Eden Valley Viognier","Eden Valley, SA",            price_aud=22.00),
        },
        data_source="Direct_API",
        last_updated_hours=4.0,
    ),

    Merchant(
        name="Liquorland Cellars North Adelaide",
        address="70 O'Connell Street, North Adelaide, SA 5006",
        lat=-34.9060, lng=138.5935,
        price_aud=31.99,
        commercial_group="coles_liquor",
        search_url_template="https://www.liquorland.com.au/search?q={brand}",
        wines={
            "Sauvignon Blanc":    WineProduct("Shaw + Smith",          "Adelaide Hills, SA",          price_aud=32.00),
            "Chardonnay":         WineProduct("Leeuwin Estate",        "Margaret River, WA",          price_aud=55.00),
            "Pinot Grigio":       WineProduct("Jermann Pinot Grigio",  "Friuli, Italy",               price_aud=45.00),
            "Riesling":           WineProduct("Henschke",              "Eden Valley, SA",             price_aud=32.00),
            "Moscato":            WineProduct("Brown Brothers Moscato","King Valley, VIC",            price_aud=15.00),
            "Pinot Noir":         WineProduct("Bass Phillip Premium",  "Gippsland, VIC",             price_aud=90.00),
            "Cabernet Sauvignon": WineProduct("Katnook Estate",        "Coonawarra, SA",              price_aud=32.00),
            "Syrah/Shiraz":       WineProduct("Langmeil Freedom",      "Barossa Valley, SA",          price_aud=38.00),
        },
        data_source="Direct_API",
        last_updated_hours=4.0,
    ),

    # =========================================================================
    # COLES LIQUOR GROUP — Liquorland Warehouse (ex-First Choice Liquor)
    # =========================================================================

    Merchant(
        name="Liquorland Warehouse Hindmarsh",
        address="Corner South Road & Port Road, Hindmarsh, SA 5007",
        lat=-34.9080, lng=138.5720,
        price_aud=26.99,
        commercial_group="coles_liquor",
        search_url_template="https://www.liquorland.com.au/search?q={brand}",
        wines={
            "Syrah/Shiraz":    WineProduct("Best's Great Western Shiraz", "Grampians, VIC",              price_aud=38.00),
            "Malbec":          WineProduct("Catena Zapata",               "Mendoza, Argentina",          price_aud=42.00),
            "Sauvignon Blanc": WineProduct("Wirra Wirra",                 "McLaren Vale, SA",            price_aud=22.00),
            "Pinot Grigio":    WineProduct("Banrock Station",             "Riverland, SA",               price_aud=12.00),
            "Sangiovese":      WineProduct("Ruffino Chianti",             "Tuscany, Italy",              price_aud=22.00),
            "Carménère":       WineProduct("Undurraga Carménère",         "Colchagua Valley, Chile",     price_aud=18.00),
            "Chenin Blanc":    WineProduct("Indaba Chenin Blanc",         "Western Cape, South Africa",  price_aud=15.00),
            "Airén":           WineProduct("Bodegas Lozano La Mancha",    "La Mancha, Spain",            price_aud=14.00),
            "Riesling":        WineProduct("Wolf Blass Yellow Label",     "Barossa Valley, SA",          price_aud=18.00),
            "Grenache":        WineProduct("d'Arenberg The Stump Jump",   "McLaren Vale, SA",            price_aud=20.00),
        },
        data_source="Direct_API",
        last_updated_hours=1.0,
    ),

    Merchant(
        name="Liquorland Warehouse Unley",
        address="245 Unley Road, Unley, SA 5061",
        lat=-34.9430, lng=138.5975,
        price_aud=26.99,
        commercial_group="coles_liquor",
        search_url_template="https://www.liquorland.com.au/search?q={brand}",
        wines={
            "Cabernet Sauvignon": WineProduct("Penfolds Bin 407",          "Barossa Valley, SA",  price_aud=68.00),
            "Syrah/Shiraz":       WineProduct("Wolf Blass Gold Label",     "Barossa Valley, SA",  price_aud=28.00),
            "Pinot Noir":         WineProduct("Yering Station",            "Yarra Valley, VIC",   price_aud=38.00),
            "Chardonnay":         WineProduct("Petaluma",                  "Adelaide Hills, SA",  price_aud=32.00),
            "Sauvignon Blanc":    WineProduct("Shaw + Smith",              "Adelaide Hills, SA",  price_aud=32.00),
            "Riesling":           WineProduct("Henschke Julius",           "Eden Valley, SA",     price_aud=25.00),
            "Merlot":             WineProduct("Penfolds Thomas Hyland",    "Barossa Valley, SA",  price_aud=25.00),
            "Grenache":           WineProduct("Yangarra Old Vine",         "McLaren Vale, SA",    price_aud=38.00),
            "Tempranillo":        WineProduct("Bodegas Muga Rioja Reserva","Rioja, Spain",        price_aud=38.00),
            "Viognier (Dry)":     WineProduct("Yalumba Eden Valley Viognier","Eden Valley, SA",   price_aud=22.00),
        },
        data_source="Direct_API",
        last_updated_hours=1.5,
    ),

    # =========================================================================
    # INDEPENDENT — East End Cellars (premium specialist, ships nationally)
    # =========================================================================

    Merchant(
        name="East End Cellars",
        address="25 Vardon Avenue, Adelaide CBD, SA 5000",
        lat=-34.9230, lng=138.6095,
        price_aud=45.00,
        commercial_group="independent",
        search_url_template="https://www.eastendcellars.com.au/search?q={brand}",
        wines={
            "Cabernet Sauvignon":   WineProduct("Penfolds Grange",              "Barossa Valley, SA",          price_aud=850.00),
            "Syrah/Shiraz":         WineProduct("Henschke Hill of Grace",        "Eden Valley, SA",             price_aud=850.00),
            "Pinot Noir":           WineProduct("Bass Phillip Premium",          "Gippsland, VIC",             price_aud=90.00),
            "Chardonnay":           WineProduct("Leeuwin Estate Art Series",     "Margaret River, WA",          price_aud=95.00),
            "Riesling":             WineProduct("Grosset Polish Hill",           "Clare Valley, SA",            price_aud=65.00),
            "Sauvignon Blanc":      WineProduct("Shaw + Smith",                  "Adelaide Hills, SA",          price_aud=32.00),
            "Grenache":             WineProduct("Yangarra High Sands",           "McLaren Vale, SA",            price_aud=55.00),
            "Malbec":               WineProduct("Achaval Ferrer Malbec",         "Mendoza, Argentina",          price_aud=38.00),
            "Tempranillo":          WineProduct("Vega Sicilia Unico",            "Ribera del Duero, Spain",     price_aud=350.00),
            "Sangiovese":           WineProduct("Sassicaia Bolgheri",            "Tuscany, Italy",              price_aud=280.00),
            "Gewürztraminer (Dry)": WineProduct("Zind-Humbrecht Alsace",         "Alsace, France",              price_aud=65.00),
            "Chenin Blanc (Dry)":   WineProduct("Clos Rougeard Saumur Blanc",    "Loire Valley, France",        price_aud=85.00),
            "Viognier (Dry)":       WineProduct("Château Grillet",               "Rhône Valley, France",        price_aud=180.00),
            "Grüner Veltliner":     WineProduct("Nikolaihof Wachau Reserve",     "Wachau, Austria",             price_aud=55.00),
            "Pinot Grigio":         WineProduct("Jermann Pinot Grigio",          "Friuli, Italy",               price_aud=45.00),
            "Moscato":              WineProduct("Vietti Moscato d'Asti",         "Piedmont, Italy",             price_aud=35.00),
            "Zinfandel":            WineProduct("Ridge Monte Bello",             "Santa Cruz Mountains, USA",   price_aud=200.00),
            "Carménère":            WineProduct("Almaviva Puente Alto",          "Maipo Valley, Chile",         price_aud=130.00),
        },
        data_source="Manual_Upload",
        last_updated_hours=24.0,
    ),

    # =========================================================================
    # INDEPENDENT — Fassina Liquor (Adelaide family chain, 8 stores)
    # =========================================================================

    Merchant(
        name="Fassina Liquor Walkerville",
        address="89 Walkerville Terrace, Walkerville, SA 5081",
        lat=-34.8970, lng=138.6170,
        price_aud=28.99,
        commercial_group="independent",
        search_url_template="https://www.fassina.com.au/search?q={brand}",
        wines={
            "Cabernet Sauvignon": WineProduct("Wynns Black Label",       "Coonawarra, SA",              price_aud=42.00),
            "Syrah/Shiraz":       WineProduct("Turkey Flat",             "Barossa Valley, SA",          price_aud=38.00),
            "Grenache":           WineProduct("Yangarra Old Vine",       "McLaren Vale, SA",            price_aud=38.00),
            "Pinot Noir":         WineProduct("Stonier Reserve",         "Mornington Peninsula, VIC",   price_aud=38.00),
            "Chardonnay":         WineProduct("Grosset Piccadilly",      "Adelaide Hills, SA",          price_aud=50.00),
            "Riesling":           WineProduct("Grosset Polish Hill",     "Clare Valley, SA",            price_aud=65.00),
            "Sauvignon Blanc":    WineProduct("Shaw + Smith",            "Adelaide Hills, SA",          price_aud=32.00),
            "Malbec":             WineProduct("Zuccardi Valle",          "Mendoza, Argentina",          price_aud=28.00),
            "Viognier (Dry)":     WineProduct("Yalumba Eden Valley Viognier","Eden Valley, SA",         price_aud=22.00),
        },
        data_source="Manual_Upload",
        last_updated_hours=48.0,
    ),

    Merchant(
        name="Fassina Liquor Somerton Park",
        address="786 Anzac Highway, Somerton Park, SA 5044",
        lat=-34.9840, lng=138.5290,
        price_aud=28.99,
        commercial_group="independent",
        search_url_template="https://www.fassina.com.au/search?q={brand}",
        wines={
            "Cabernet Sauvignon": WineProduct("Penfolds Bin 407",            "Barossa Valley, SA",          price_aud=68.00),
            "Syrah/Shiraz":       WineProduct("Wolf Blass Gold Label",       "Barossa Valley, SA",          price_aud=28.00),
            "Grenache":           WineProduct("d'Arenberg The Stump Jump",   "McLaren Vale, SA",            price_aud=20.00),
            "Sauvignon Blanc":    WineProduct("Wirra Wirra Mrs Wigley",      "McLaren Vale, SA",            price_aud=22.00),
            "Chardonnay":         WineProduct("Petaluma Hanlin Hill",        "Adelaide Hills, SA",          price_aud=32.00),
            "Riesling":           WineProduct("Henschke",                    "Eden Valley, SA",             price_aud=32.00),
            "Pinot Noir":         WineProduct("Stonier Reserve",             "Mornington Peninsula, VIC",   price_aud=38.00),
            "Malbec":             WineProduct("Angove",                      "McLaren Vale, SA",            price_aud=18.00),
        },
        data_source="Manual_Upload",
        last_updated_hours=48.0,
    ),

    # =========================================================================
    # ONLINE — Vinomofo (SA roots, national delivery)
    # =========================================================================

    Merchant(
        name="Vinomofo",
        address="Online — delivers Australia-wide",
        lat=-34.9285, lng=138.6007,   # Adelaide CBD centroid for distance calc
        price_aud=35.00,
        commercial_group="online",
        is_online_only=True,
        search_url_template="https://www.vinomofo.com/wines/search?q={brand}",
        wines={
            "Cabernet Sauvignon": WineProduct("Penfolds Bin 407",          "Barossa Valley, SA",  price_aud=68.00),
            "Syrah/Shiraz":       WineProduct("Langmeil Freedom",          "Barossa Valley, SA",  price_aud=38.00),
            "Grenache":           WineProduct("Yangarra Old Vine",         "McLaren Vale, SA",    price_aud=38.00),
            "Pinot Noir":         WineProduct("Yering Station",            "Yarra Valley, VIC",   price_aud=38.00),
            "Chardonnay":         WineProduct("Grosset Piccadilly",        "Adelaide Hills, SA",  price_aud=50.00),
            "Sauvignon Blanc":    WineProduct("Shaw + Smith",              "Adelaide Hills, SA",  price_aud=32.00),
            "Riesling":           WineProduct("Grosset Polish Hill",       "Clare Valley, SA",    price_aud=65.00),
            "Malbec":             WineProduct("Zuccardi Valle",            "Mendoza, Argentina",  price_aud=28.00),
            "Sangiovese":         WineProduct("Antinori Chianti Classico", "Tuscany, Italy",      price_aud=35.00),
            "Tempranillo":        WineProduct("Bodegas Muga Rioja",        "Rioja, Spain",        price_aud=35.00),
            "Viognier (Dry)":     WineProduct("Yalumba Eden Valley Viognier","Eden Valley, SA",   price_aud=22.00),
        },
        data_source="Scraped_Data",
        last_updated_hours=24.0,
    ),

    # =========================================================================
    # ONLINE — The Wine Collective (absorbed Cracka Wines)
    # =========================================================================

    Merchant(
        name="The Wine Collective",
        address="Online — delivers Australia-wide",
        lat=-34.9285, lng=138.6007,
        price_aud=32.00,
        commercial_group="online",
        is_online_only=True,
        search_url_template="https://www.thewinecollective.com.au/search?q={brand}",
        wines={
            "Cabernet Sauvignon": WineProduct("Wynns Black Label",        "Coonawarra, SA",      price_aud=42.00),
            "Syrah/Shiraz":       WineProduct("Turkey Flat",              "Barossa Valley, SA",  price_aud=38.00),
            "Pinot Noir":         WineProduct("Grosset",                  "Tasmania, TAS",       price_aud=65.00),
            "Chardonnay":         WineProduct("Petaluma",                 "Adelaide Hills, SA",  price_aud=32.00),
            "Sauvignon Blanc":    WineProduct("Wirra Wirra",              "McLaren Vale, SA",    price_aud=22.00),
            "Riesling":           WineProduct("Jim Barry The Florita",    "Clare Valley, SA",    price_aud=55.00),
            "Grenache":           WineProduct("d'Arenberg The Stump Jump","McLaren Vale, SA",    price_aud=20.00),
            "Malbec":             WineProduct("Catena Zapata",            "Mendoza, Argentina",  price_aud=42.00),
            "Tempranillo":        WineProduct("Torres Gran Sangre de Toro","Catalunya, Spain",   price_aud=22.00),
            "Sangiovese":         WineProduct("Ruffino Chianti",          "Tuscany, Italy",      price_aud=22.00),
            "Viognier (Dry)":     WineProduct("Yalumba Eden Valley Viognier","Eden Valley, SA",  price_aud=22.00),
        },
        data_source="Scraped_Data",
        last_updated_hours=24.0,
    ),

    # =========================================================================
    # ONLINE — Wine Selectors (Australia's largest independent direct marketer)
    # =========================================================================

    Merchant(
        name="Wine Selectors",
        address="Online — delivers Australia-wide",
        lat=-34.9285, lng=138.6007,
        price_aud=38.00,
        commercial_group="online",
        is_online_only=True,
        search_url_template="https://www.wineselectors.com.au/wine-shop/search?q={brand}",
        wines={
            "Cabernet Sauvignon": WineProduct("Katnook Estate",          "Coonawarra, SA",      price_aud=32.00),
            "Syrah/Shiraz":       WineProduct("Langmeil Freedom",        "Barossa Valley, SA",  price_aud=38.00),
            "Grenache":           WineProduct("Yangarra Old Vine",       "McLaren Vale, SA",    price_aud=38.00),
            "Chardonnay":         WineProduct("Leeuwin Estate",          "Margaret River, WA",  price_aud=55.00),
            "Sauvignon Blanc":    WineProduct("Shaw + Smith",            "Adelaide Hills, SA",  price_aud=32.00),
            "Riesling":           WineProduct("Henschke",                "Eden Valley, SA",     price_aud=32.00),
            "Pinot Noir":         WineProduct("Leeuwin Estate Art Series","Margaret River, WA",  price_aud=95.00),
            "Malbec":             WineProduct("Achaval Ferrer",          "Mendoza, Argentina",  price_aud=38.00),
            "Viognier (Dry)":     WineProduct("Yalumba Eden Valley Viognier","Eden Valley, SA",  price_aud=22.00),
            "Chenin Blanc (Dry)": WineProduct("Domaine Huet Vouvray Sec","Loire Valley, France", price_aud=65.00),
        },
        data_source="Scraped_Data",
        last_updated_hours=24.0,
    ),
]


# ---------------------------------------------------------------------------
# Inventory Ghost — confidence scoring
# ---------------------------------------------------------------------------

_SOURCE_CONFIDENCE: dict[str, float] = {
    "Direct_API":    0.95,
    "Manual_Upload": 0.60,
    "Scraped_Data":  0.40,
}

_VERIFICATION_THRESHOLD = 0.70


def get_stock_certainty(data_source: str, last_updated_hours: float) -> tuple[float, bool]:
    """Return (confidence_score, needs_verification) for a merchant's inventory data."""
    base = _SOURCE_CONFIDENCE.get(data_source, 0.40)
    time_decay = last_updated_hours * 0.05
    score = max(0.10, base - time_decay)
    return round(score, 3), score < _VERIFICATION_THRESHOLD


# ---------------------------------------------------------------------------
# Partner boost / rival exclusion
# ---------------------------------------------------------------------------

def _apply_partner_filter(candidates: list[MerchantResult]) -> list[MerchantResult]:
    """
    When a preferred_partner is configured:
      1. Mark partner merchants with is_partner=True
      2. Exclude rival group merchants entirely (if exclude_rival_group=True)

    Independent and online groups are never excluded.
    """
    partner = PARTNER_CONFIG.get("preferred_partner")
    if not partner:
        return candidates

    rival = _RIVAL_GROUPS.get(partner)
    exclude_rival = PARTNER_CONFIG.get("exclude_rival_group", True)

    filtered = []
    for c in candidates:
        group = c.merchant.commercial_group
        if exclude_rival and rival and group == rival:
            log.info(
                "[Partner] EXCLUDED  %-35s  group=%s  (rival of partner=%s)",
                c.merchant.name, group, partner,
            )
            continue
        if group == partner:
            c.is_partner = True
        filtered.append(c)

    return filtered


def _apply_partner_boost(candidates: list[MerchantResult]) -> None:
    """Subtract rank_boost from partner merchant scores (lower = better rank)."""
    boost = PARTNER_CONFIG.get("partner_rank_boost", 0.25)
    partner = PARTNER_CONFIG.get("preferred_partner")
    if not partner:
        return
    for c in candidates:
        if c.is_partner:
            original = c.score
            c.score = max(0.0, round(c.score - boost, 2))
            log.info(
                "[Partner] BOOSTED   %-35s  score %.2f → %.2f  (-%s boost)",
                c.merchant.name, original, c.score, boost,
            )


# ---------------------------------------------------------------------------
# Distance + ranking
# ---------------------------------------------------------------------------

def _avg_market_price(wine_name: str) -> float:
    """Average per-wine price across every catalog merchant that stocks wine_name."""
    prices = []
    for m in MERCHANT_CATALOG:
        if wine_name in m.wines:
            p = m.wines[wine_name]
            prices.append(p.price_aud if p.price_aud > 0.0 else m.price_aud)
    return sum(prices) / len(prices) if prices else 0.0


def calculate_merchant_rank(distance: float, price: float, avg_market_price: float) -> float:
    """Unicorn Vintage Trap ranking — lower score = better result."""
    if avg_market_price <= 0:
        return distance * 10 + price
    price_ceiling = avg_market_price * 1.25
    if price > price_ceiling:
        adjusted_wd   = 1.0
        penalty_score = (price / avg_market_price) * 50
    else:
        adjusted_wd   = 10.0
        penalty_score = 0.0
    return distance * adjusted_wd + price * 1.0 + penalty_score


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


def find_raw_candidates(
    wine_name: str,
    user_lat: float,
    user_lng: float,
    budget_min: float = 0.0,
    budget_max: float = 9999.0,
) -> list[MerchantResult]:
    """Return merchants stocking wine_name within budget, with distance, tier,
    and partner flag populated.  Partner filter and boost are applied here
    before results reach the middleware interceptor."""
    results: list[MerchantResult] = []
    live_prices = get_cheapest_by_varietal("liquorland")

    for merchant in MERCHANT_CATALOG:
        if wine_name not in merchant.wines:
            continue
        product    = merchant.wines[wine_name]
        wine_price = product.price_aud if product.price_aud > 0.0 else merchant.price_aud

        # Override with live scraped price for Coles Liquor Group merchants
        if merchant.commercial_group == "coles_liquor" and wine_name in live_prices:
            live = live_prices[wine_name]
            log.info(
                "[LivePrice] %-35s  %s  $%.2f → $%.2f (scraped)",
                merchant.name, wine_name, wine_price, live["price"],
            )
            wine_price = live["price"]

        if not (budget_min <= wine_price <= budget_max):
            log.info(
                "[Budget Gate] EXCLUDED  %-35s  $%.2f outside budget $%.2f–$%.2f",
                merchant.name, wine_price, budget_min, budget_max,
            )
            continue
        tier = get_region_tier(product.region)
        d    = haversine_km(user_lat, user_lng, merchant.lat, merchant.lng)
        log.info(
            "[Budget Gate] PASSED     %-35s  $%.2f  %.2f km  tier=%d  group=%s  region=%s",
            merchant.name, wine_price, d, tier,
            merchant.commercial_group, product.region,
        )
        results.append(MerchantResult(
            merchant=merchant,
            brand=product.brand,
            region=product.region,
            tier=tier,
            distance_km=round(d, 2),
            price_aud=wine_price,
        ))

    # Apply partner filter (exclude rival group) and mark partner merchants
    results = _apply_partner_filter(results)
    return results
