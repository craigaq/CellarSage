"""
Geo-gated retailers: retailers whose wines should only be shown to users
within a specified radius of the physical store.

Add entries here when a new store-specific scrape is added. The backend
buy-options and wine-picks endpoints filter by user distance at query time.
"""

from __future__ import annotations
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class GeoRetailer:
    retailer:    str    # matches the retailer field in merchant_offers
    label:       str    # display name shown in the app
    lat:         float  # store latitude
    lng:         float  # store longitude
    radius_km:   float  # visibility radius


GEO_RETAILERS: list[GeoRetailer] = [
    GeoRetailer(
        retailer  = "cellarbrations_sunbury",
        label     = "Cellarbrations",
        lat       = -37.57907399070393,
        lng       = 144.74941778805461,
        radius_km = 15.0,
    ),
]

# Fast lookup: retailer name → GeoRetailer
_BY_RETAILER: dict[str, GeoRetailer] = {g.retailer: g for g in GEO_RETAILERS}


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_geo_retailer(retailer: str) -> bool:
    return retailer in _BY_RETAILER


def retailer_visible(retailer: str, user_lat: float | None, user_lng: float | None) -> bool:
    """Return True if the retailer should be shown to this user.

    For non-geo retailers, always True.
    For geo retailers, True only when user is within the store's radius.
    If user location is unknown, geo retailers are hidden.
    """
    geo = _BY_RETAILER.get(retailer)
    if geo is None:
        return True  # not geo-gated
    if user_lat is None or user_lng is None:
        return False  # location unknown — hide store-specific retailer
    dist = _haversine_km(user_lat, user_lng, geo.lat, geo.lng)
    return dist <= geo.radius_km


def retailer_display_label(retailer: str) -> str:
    """Return the user-facing label for a geo retailer."""
    geo = _BY_RETAILER.get(retailer)
    return geo.label if geo else retailer
