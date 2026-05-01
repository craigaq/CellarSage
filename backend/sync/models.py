"""
Internal data models. All scraped data is coerced into these before
hitting the database — the schema is the contract.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class WineRecord:
    """Static wine attributes — deduped by (name, vintage)."""
    name: str
    vintage: Optional[int] = None
    region: Optional[str] = None
    varietal: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None


@dataclass
class MerchantOffer:
    """Volatile price/availability data — one row per (wine, retailer)."""
    wine_name: str
    vintage: Optional[int]
    retailer: str
    price: float
    url: Optional[str]
    rating: Optional[float] = None
    review_count: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SyncResult:
    """Summary returned by the sync pipeline for logging."""
    merchant: str
    scraped: int = 0
    normalised: int = 0
    wines_upserted: int = 0
    offers_upserted: int = 0
    errors: list = field(default_factory=list)
