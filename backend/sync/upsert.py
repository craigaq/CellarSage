"""
Database upsert logic.
Connects to PostgreSQL (Supabase or any Postgres) via DATABASE_URL.
Uses "Sage Upsert" strategy: find-or-create Wine by (name, vintage),
then upsert MerchantOffer so price + timestamp are always current.
"""

import os
import logging
from typing import Optional

import psycopg2
import psycopg2.extras

from .models import WineRecord, MerchantOffer

log = logging.getLogger(__name__)


def _connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise EnvironmentError("DATABASE_URL environment variable not set")
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)


def _upsert_wine(cur, wine: WineRecord) -> int:
    """
    Insert wine if it doesn't exist, or update region/varietal/country if they were
    previously NULL. Returns the wine's id.
    """
    cur.execute(
        """
        INSERT INTO wines (name, vintage, region, varietal, country, state)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (name, vintage) DO UPDATE
            SET region   = COALESCE(wines.region,   EXCLUDED.region),
                varietal = COALESCE(wines.varietal, EXCLUDED.varietal),
                country  = COALESCE(EXCLUDED.country, wines.country),
                state    = COALESCE(EXCLUDED.state,   wines.state)
        RETURNING id
        """,
        (wine.name, wine.vintage, wine.region, wine.varietal, wine.country, wine.state),
    )
    row = cur.fetchone()
    return row["id"]


def _upsert_offer(cur, wine_id: int, offer: MerchantOffer) -> None:
    """
    Insert merchant offer, or update price + last_updated if it already exists.
    """
    cur.execute(
        """
        INSERT INTO merchant_offers (wine_id, retailer, price, url, rating, review_count, last_updated)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (wine_id, retailer) DO UPDATE
            SET price        = COALESCE(EXCLUDED.price,        merchant_offers.price),
                url          = COALESCE(EXCLUDED.url,          merchant_offers.url),
                rating       = COALESCE(EXCLUDED.rating,       merchant_offers.rating),
                review_count = GREATEST(EXCLUDED.review_count, merchant_offers.review_count),
                last_updated = EXCLUDED.last_updated
        """,
        (wine_id, offer.retailer, offer.price, offer.url,
         offer.rating, offer.review_count, offer.last_updated),
    )


def upsert_batch(pairs: list[tuple[WineRecord, MerchantOffer]]) -> tuple[int, int]:
    """
    Upsert a list of (WineRecord, MerchantOffer) pairs in a single transaction.

    Returns:
        (wines_touched, offers_touched)
    """
    if not pairs:
        return 0, 0

    wines_touched = offers_touched = 0

    with _connection() as conn:
        with conn.cursor() as cur:
            for wine, offer in pairs:
                wine_id = _upsert_wine(cur, wine)
                _upsert_offer(cur, wine_id, offer)
                wines_touched  += 1
                offers_touched += 1
        conn.commit()

    log.info("Upserted %d wines, %d offers", wines_touched, offers_touched)
    return wines_touched, offers_touched
