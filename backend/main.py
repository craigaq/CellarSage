import logging
from dotenv import load_dotenv
load_dotenv()  # loads backend/.env in local dev; no-op in production

from fastapi import FastAPI, HTTPException, Query, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
# Show per-criterion Middle Ground debug lines from the interceptor
logging.getLogger("cellar_sage.interceptor").setLevel(logging.DEBUG)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional

import dataclasses
import urllib.parse

from recommendation_service import (
    RecommendationService, WineProfile, UserPreferences,
    BeerRecommendationService, BeerProfile, ScoredBeer,
    check_food_pairing_conflicts,
    resolve_pairing_conflict,
)
from wine_catalog import load_catalog_from_db
from term_mapping import TECHNICAL_TO_UI
from interceptor import run_recommendation_middleware, run_merchant_middleware, TieredMerchantResults
from local_sourcing import TIER_LABELS, TIER_REGION_HINTS
from currency import convert_from_aud, convert_to_aud, lat_lng_to_currency, get_info as get_currency_info
from affiliate_config import build_affiliate_url

app = FastAPI(title="Cellar Sage API")

# Rate limiting — 60 requests/minute per IP across all endpoints
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.on_event("startup")
async def startup_event():
    """Warm the merchant validation cache on startup."""
    from merchant_validator import validate_all_catalog
    summary = await validate_all_catalog()
    logging.getLogger("cellar_sage").info(
        "[Startup] Merchant validation complete: %s", summary
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://cellarsage.com.au",
        "https://cellarsage.app",
        "http://localhost:8080",   # local landing page dev
        "http://localhost:3000",   # local web dev
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Varietal catalog: loaded from DB at startup, falls back to bundled wine_catalog.py.
# Reload by calling _reload_service() (e.g. after /internal/flush-cache).
_service = RecommendationService(load_catalog_from_db())

# Beer catalog: loaded from DB at startup
def _load_beer_catalog():
    from wine_catalog import load_beer_catalog_from_db
    try:
        return load_beer_catalog_from_db()
    except Exception as e:
        logging.getLogger("cellar_sage").warning("Could not load beer catalog: %s", e)
        return []

_beer_service = BeerRecommendationService(_load_beer_catalog())


# How "normal" a pack is as a retail purchase unit (lower = preferred as the
# representative offer for a beer): 4-6 packs first, cartons next, singles last.
def _pack_rank(pack_count: int | None) -> int:
    pc = pack_count or 1
    if 4 <= pc <= 6:
        return 0
    if pc >= 7:
        return 1
    return 2  # singles / pairs


def _load_beer_offers() -> dict[str, list[dict]]:
    """Beer offers keyed by lowercase beer name.

    Each beer is deduped to ONE representative offer per retailer — its most
    sensible retail pack (4-6 pack preferred, carton next, single last) — so a
    beer's cheap single can and pricey carton don't make it span budget tiers.
    Each offer carries pack_count + unit_price for per-drink display.
    """
    import os
    url = os.environ.get("DATABASE_URL")
    if not url:
        return {}
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
        with conn, conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name='beer_merchant_offers')"
            )
            if not cur.fetchone()["exists"]:
                return {}
            cur.execute(
                """SELECT b.name, o.retailer, o.price, o.url, o.package_info,
                          o.pack_count, o.unit_price
                   FROM beer_merchant_offers o JOIN beers b ON b.id = o.beer_id
                   WHERE o.price IS NOT NULL"""
            )
            rows = cur.fetchall()
        # Pick one representative offer per (beer, retailer).
        best: dict[tuple, dict] = {}
        for r in rows:
            key = (r["name"].lower(), r["retailer"])
            cand = {
                "retailer": r["retailer"],
                "price": float(r["price"]),
                "url": r["url"] or "",
                "package_info": r["package_info"] or "",
                "pack_count": r["pack_count"] or 1,
                "unit_price": float(r["unit_price"]) if r["unit_price"] is not None else float(r["price"]),
            }
            cur_best = best.get(key)
            # Prefer the more "normal" pack; tie-break on lower unit price.
            if (cur_best is None
                    or _pack_rank(cand["pack_count"]) < _pack_rank(cur_best["pack_count"])
                    or (_pack_rank(cand["pack_count"]) == _pack_rank(cur_best["pack_count"])
                        and cand["unit_price"] < cur_best["unit_price"])):
                best[key] = cand
        offers: dict[str, list[dict]] = {}
        for (name_lc, _retailer), offer in best.items():
            offers.setdefault(name_lc, []).append(offer)
        for lst in offers.values():
            lst.sort(key=lambda o: o["price"])
        return offers
    except Exception as e:
        logging.getLogger("cellar_sage").warning("Could not load beer offers: %s", e)
        return {}


_beer_offers = _load_beer_offers()


def _reload_service() -> None:
    global _service, _beer_service, _beer_offers
    _service = RecommendationService(load_catalog_from_db())
    _beer_service = BeerRecommendationService(_load_beer_catalog())
    _beer_offers = _load_beer_offers()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class RecommendRequest(BaseModel):
    crispness_acidity: int = Field(..., ge=1, le=5, description="Crispness (Acidity) preference 1-5")
    weight_body: int       = Field(..., ge=1, le=5, description="Weight (Body) preference 1-5")
    texture_tannin: int    = Field(..., ge=1, le=5, description="Texture (Tannin) preference 1-5")
    flavor_intensity: int  = Field(..., ge=1, le=5, description="Flavor Intensity (Aromatics) preference 1-5")
    food_pairing: Optional[str] = Field("none", max_length=100, description="Food pairing backend ID")
    top_n: Optional[int]   = Field(None, ge=1, description="Return top N results")
    pref_dry: bool         = Field(False, description="User prefers dry wines")
    override_mode: Literal["filter_by_profile", "use_pairing_logic", "find_compromise"] = Field(
        "use_pairing_logic",
        description="Palate Paradox resolution mode",
    )
    pairing_mode: Literal["congruent", "contrast", "brave"] = Field(
        "congruent",
        description="Pairing philosophy: congruent (match the dish) | contrast (balance the dish) | brave (food chooses the wine)",
    )
    style_anchors: Optional[list[str]] = Field(
        None,
        max_length=8,
        description="Beer mode only: styles the user already enjoys (e.g. ['IPA', 'Stout']); ignored for wine",
    )


class WineResult(BaseModel):
    name: str
    sku_id: str
    score: float
    attribute_scores: dict[str, float]
    wine_profile: dict[str, float]   # normalised 1-5 attribute values keyed by UI label
    raw_metrics: dict                 # real-world schema values for "under the hood" display


class RecommendResponse(BaseModel):
    recommendations: list[WineResult]
    ui_labels: dict[str, str]
    conflict_alert: Optional[dict] = None
    gastro_clash: Optional[dict] = None
    pairing_conflict: Optional[dict] = None


class BeerResult(BaseModel):
    name: str
    sku_id: str
    score: float
    attribute_scores: dict[str, float]
    beer_profile: dict[str, float]   # normalised 1-5 attribute values
    beer_style: str
    pairing_explanation: str = ""    # Cicerone pairing logic, human-readable
    flavor_tags: list[str] = []      # style-derived descriptors ("chocolate", "citrus hops")
    buy_options: list[dict] = []     # retailer offers: {retailer, price, url, package_info}


class BeerRecommendResponse(BaseModel):
    recommendations: list[BeerResult]
    ui_labels: dict[str, str]  # Reuse wine UI labels for now


class BeerPick(BaseModel):
    name: str
    beer_style: str
    abv_percentage: float
    price: float
    retailer: str
    url: str = ""
    package_info: str = ""
    pack_count: int = 1
    unit_price: float = 0.0
    tier: int = 2                    # 1 Local Hero · 2 Interstater · 3 Internationalist
    tier_label: str = "The Interstater"
    untappd_rating: Optional[float] = None   # community rating out of 5
    untappd_url: str = ""
    highly_rated: bool = False               # strong rating *for its style*


class BeerPicksResponse(BaseModel):
    style: str
    picks: list[BeerPick]


class NearbyRequest(BaseModel):
    wine_name: str = Field(..., max_length=200)
    user_lat: float = Field(..., ge=-90.0, le=90.0)
    user_lng: float = Field(..., ge=-180.0, le=180.0)
    budget_min: float = 0.0
    budget_max: float = 9999.0
    show_global_tier: bool = Field(
        False,
        description=(
            "Override the Pricing Precedent gate — show Tier 3 (Global Icon) "
            "even when it costs more than 5× the cheapest Tier 1 option."
        ),
    )
    currency_code: str = Field(
        "AUD",
        description=(
            "ISO 4217 currency code for the user's locale (e.g. 'AUD', 'USD'). "
            "budget_min/max must be expressed in this currency. "
            "Prices in the response are converted to this currency. "
            "When omitted, the server infers currency from the user's GPS coordinates."
        ),
    )

    @field_validator("currency_code")
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        from currency import CURRENCY_META
        code = v.upper()
        if code not in CURRENCY_META:
            raise ValueError(
                f"Unsupported currency '{v}'. Supported codes: {sorted(CURRENCY_META)}"
            )
        return code


class MerchantResponse(BaseModel):
    name: str
    address: str
    brand: str
    region: str           # wine production region (e.g., "Barossa Valley, SA")
    tier: int             # 1 | 2 | 3
    tier_label: str       # "The Local Hero" | "The National Rival" | "The Global Icon"
    distance_km: float
    price_local: float    # price in the user's requested currency
    currency_code: str    # ISO 4217 (e.g. "AUD")
    currency_symbol: str  # display symbol (e.g. "A$")
    website_url: str      # deep-link to retailer's search page for this wine brand
    score: float
    confidence_score: float
    needs_verification: bool
    is_partner: bool = False      # True when merchant belongs to preferred_partner group
    is_online_only: bool = False  # True for delivery-only retailers
    commercial_group: str = ""    # endeavour | coles_liquor | independent | online


class TierResponse(BaseModel):
    tier: int
    label: str          # "The Local Hero" etc.
    region_hint: str    # Priority regions for this tier
    best_match: Optional[MerchantResponse]
    all_matches: list[MerchantResponse]
    suppressed: bool = False
    suppression_reason: Optional[str] = None
    persona: Optional[str] = None           # "The Proud Neighbour" etc.
    wit: Optional[str] = None               # Short punchy one-liner
    edu_insight: Optional[str] = None       # Template-filled educational hook
    comparison_note: Optional[str] = None   # How this tier differs from the other two


class NearbyResponse(BaseModel):
    wine_name: str
    merchants: list[MerchantResponse]   # flat sorted list (backward compat)
    tiers: list[TierResponse]           # three geographic buckets
    pricing_precedent_applied: bool


class CheckPairingResponse(BaseModel):
    gastro_clash: Optional[dict] = None
    pairing_conflict: Optional[dict] = None


class BuyOption(BaseModel):
    name: str
    price: float
    url: str
    retailer: str = ""
    price_is_stale: bool = False


class WinePick(BaseModel):
    tier: int
    tier_label: str
    name: str
    varietal: Optional[str]
    country: Optional[str]
    state: Optional[str]
    region: Optional[str]
    price: float
    url: str
    retailer: str = ""
    price_is_stale: bool = False
    is_member_price: bool = False
    rating: Optional[float] = None
    review_count: int = 0
    critic_score: Optional[float] = None
    vivino_rating: Optional[float] = None
    vivino_review_count: int = 0
    vivino_url: Optional[str] = None
    is_sage_pick: bool = False
    is_highly_verified: bool = False
    body: Optional[float] = None
    acidity: Optional[float] = None
    tannin: Optional[float] = None
    sweetness: Optional[float] = None
    fruit_intensity: Optional[float] = None
    flavor_notes: list[str] = []


class WinePicksResponse(BaseModel):
    varietal: str
    picks: list[WinePick]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/hello")
def hello():
    return {"message": "Hello from Cellar Sage!"}


@app.get("/check-pairing", response_model=CheckPairingResponse)
def check_pairing(
    food_type: str = Query(..., max_length=100, description="Food pairing selection"),
    crispness_acidity: int = Query(..., ge=1, le=5),
    weight_body: int = Query(..., ge=1, le=5),
    texture_tannin: int = Query(..., ge=1, le=5),
    flavor_intensity: int = Query(..., ge=1, le=5),
    pref_dry: bool = Query(False, description="User prefers dry wines"),
):
    """
    Lightweight endpoint: checks for food/palate clashes — both Gastro-Clash
    (palate attribute mismatches) and Palate Paradox (dry preference vs. a
    sweet-pairing food choice) — without running the full recommendation engine.
    Called immediately after food selection so the UI can surface alerts.
    """
    try:
        prefs = UserPreferences(
            crispness_acidity=crispness_acidity,
            weight_body=weight_body,
            texture_tannin=texture_tannin,
            flavor_intensity=flavor_intensity,
            food_pairing=food_type,
            pref_dry=pref_dry,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    clash   = check_food_pairing_conflicts(prefs)
    paradox = resolve_pairing_conflict(prefs)
    return CheckPairingResponse(
        gastro_clash=dataclasses.asdict(clash) if clash else None,
        pairing_conflict=dataclasses.asdict(paradox) if paradox else None,
    )


def _build_conflict_alert(prefs: UserPreferences) -> dict | None:
    """Return alert data for the first detected palate conflict, or None."""
    # Light body + high tannin — the classic contradiction
    if prefs.weight_body <= 2 and prefs.texture_tannin >= 4:
        return {
            "title": "The Cellar Fox Senses a Disturbance",
            "message": (
                "Ah — Light Weight with High Texture. Bold. Rare. "
                "Like a featherweight boxer with an iron grip.\n\n"
                "Most light-bodied wines keep their tannins polite and their manners impeccable. "
                "For a wider selection from the cellar, the Cellar Fox suggests softening the Texture."
            ),
            "field": "texture_tannin",
            "suggested_value": 2,
        }
    # Low flavor + high acidity — sharp without expression
    if prefs.flavor_intensity <= 1 and prefs.crispness_acidity >= 4:
        return {
            "title": "The Cellar Fox Raises an Eyebrow",
            "message": (
                "Maximum Crispness with barely any Flavor Intensity — "
                "you're asking for a razor edge with nothing behind it.\n\n"
                "The sharpness would dominate completely. "
                "The Cellar Fox suggests lifting Flavor Intensity so there's something to cut through."
            ),
            "field": "flavor_intensity",
            "suggested_value": 3,
        }
    # Maximum tannin + maximum acidity — very aggressive palate
    if prefs.texture_tannin >= 5 and prefs.crispness_acidity >= 5:
        return {
            "title": "The Cellar Fox Is Impressed (and Concerned)",
            "message": (
                "Maximum Texture AND Maximum Crispness. "
                "You want every molecule of that wine to fight back.\n\n"
                "This is a very narrow field — few wines survive both extremes well. "
                "The Cellar Fox suggests dialling Crispness back slightly for a more satisfying match."
            ),
            "field": "crispness_acidity",
            "suggested_value": 3,
        }
    return None


def _wine_profile_dict(wine: WineProfile) -> dict[str, float]:
    """Return a wine's normalised 1-5 attribute profile keyed by UI labels (for radar chart)."""
    return {
        TECHNICAL_TO_UI["acidity"]:   wine.acidity,
        TECHNICAL_TO_UI["body"]:      wine.body,
        TECHNICAL_TO_UI["tannin"]:    wine.tannin,
        TECHNICAL_TO_UI["aromatics"]: wine.aromatics,
    }


def _raw_metrics_dict(wine: WineProfile) -> dict:
    """Return the real-world Enhanced Data Schema fields for 'under the hood' display."""
    return {
        "sku_id":             wine.sku_id,
        "location_tag":       wine.location_tag,
        "acidity_ph":         wine.acidity_ph,
        "aromatic_intensity": wine.aromatic_intensity,
        "tannin_structure":   wine.tannin_structure,
        "abv_percentage":     wine.abv_percentage,
        "residual_sugar_gl":  wine.residual_sugar_gl,
        "style":              wine.style,
        "varietal":           wine.varietal,
    }


@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    try:
        prefs = UserPreferences(
            crispness_acidity=req.crispness_acidity,
            weight_body=req.weight_body,
            texture_tannin=req.texture_tannin,
            flavor_intensity=req.flavor_intensity,
            food_pairing=req.food_pairing,
            pref_dry=req.pref_dry,
            override_mode=req.override_mode,
            pairing_mode=req.pairing_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    results, paradox = run_recommendation_middleware(_service, prefs, top_n=req.top_n)

    return RecommendResponse(
        recommendations=[
            WineResult(
                name=r.wine.name,
                sku_id=r.wine.sku_id,
                score=r.score,
                attribute_scores=r.attribute_scores,
                wine_profile=_wine_profile_dict(r.wine),
                # pairing_explanation rides in raw_metrics — the frontend's
                # whyThisPick callout prefers it over its local heuristics.
                raw_metrics={
                    **_raw_metrics_dict(r.wine),
                    "pairing_explanation": r.explanation,
                },
            )
            for r in results
        ],
        ui_labels=TECHNICAL_TO_UI,
        conflict_alert=_build_conflict_alert(prefs),
        gastro_clash=(
            dataclasses.asdict(clash)
            if (clash := check_food_pairing_conflicts(prefs))
            else None
        ),
        pairing_conflict=dataclasses.asdict(paradox) if paradox else None,
    )


@app.post("/beer-recommend", response_model=BeerRecommendResponse)
def beer_recommend(req: RecommendRequest):
    """Beer pairing recommendation — parallel to /recommend."""
    try:
        prefs = UserPreferences(
            crispness_acidity=req.crispness_acidity,
            weight_body=req.weight_body,
            texture_tannin=req.texture_tannin,
            flavor_intensity=req.flavor_intensity,
            food_pairing=req.food_pairing,
            pref_dry=req.pref_dry,
            override_mode=req.override_mode,
            pairing_mode=req.pairing_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Score beers without middleware (MVP — no geo-gating, no filtering)
    results = _beer_service.recommend(
        prefs, top_n=req.top_n, style_anchors=req.style_anchors,
    )

    def _beer_profile_dict(beer: BeerProfile) -> dict[str, float]:
        """Map beer attributes to UI labels."""
        return {
            "Bitterness": min(5.0, max(1.0, beer.bitterness)),
            "Weight": min(5.0, max(1.0, beer.body)),
            "Flavor Intensity": min(5.0, max(1.0, beer.aromatics)),
            "Sweetness": min(5.0, max(1.0, beer.sweetness)),
            "Carbonation": min(5.0, max(1.0, beer.carbonation)),
            "Roast": min(5.0, max(1.0, beer.roast)),
        }

    return BeerRecommendResponse(
        recommendations=[
            BeerResult(
                name=r.beer.name,
                sku_id=r.beer.sku_id,
                score=r.score,
                attribute_scores=r.attribute_scores,
                beer_profile=_beer_profile_dict(r.beer),
                beer_style=r.beer.beer_style,
                pairing_explanation=r.explanation,
                flavor_tags=r.beer.flavor_tags,
                buy_options=_beer_offers.get(r.beer.name.lower(), [])[:3],
            )
            for r in results
        ],
        ui_labels=TECHNICAL_TO_UI,
    )


_BEER_TIER_LABELS = {1: "Local Hero", 2: "The Interstater", 3: "The Internationalist"}


def _beer_tier(location_tag: str | None, brewery_state: str | None, user_state: str | None) -> int:
    """Origin tier: 3 overseas; 1 if the brewery is in the user's state; else 2."""
    if location_tag == "International":
        return 3
    if user_state and brewery_state and brewery_state.upper() == user_state.upper():
        return 1  # Local Hero — brewed in the user's own state
    return 2      # The Interstater — Australian, another state (or unknown)


@app.get("/beer-picks", response_model=BeerPicksResponse)
def beer_picks(
    style: str = Query(..., max_length=60),
    budget_min: float = Query(0.0, ge=0.0),
    budget_max: float = Query(99999.0, ge=0.0),
    user_state: Optional[str] = Query(None, max_length=10, description="User's AU state (e.g. 'SA') for Local Hero"),
):
    """Every buyable beer of a given style, grouped by origin tier.

    Beer analogue of /wine-picks. Offers filtered to the budget bracket, then
    grouped Local Hero → The Interstater → The Internationalist (best per-drink
    value first within each). 'Local Hero' is awarded when the brewery's state
    matches the user's — geo-personalised like wine, so a Victorian sees VB as
    local while a South Australian sees Coopers as local.
    """
    import os
    picks: list[BeerPick] = []
    url = os.environ.get("DATABASE_URL")
    if url:
        try:
            import psycopg2, psycopg2.extras
            conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
            with conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                    "WHERE table_name='beer_merchant_offers')"
                )
                if cur.fetchone()["exists"]:
                    # Style's average rating, to flag beers that are highly
                    # rated *for their style* (Untappd skews by style — IPAs
                    # high, lagers low — so a flat threshold would bury lagers).
                    cur.execute(
                        "SELECT AVG(untappd_rating) AS a FROM beers "
                        "WHERE beer_style = %s AND untappd_rating IS NOT NULL",
                        (style,),
                    )
                    style_avg = cur.fetchone()["a"]
                    style_avg = float(style_avg) if style_avg is not None else None

                    # Fetch the full in-budget pool (value-ordered), then keep up
                    # to N PER TIER so every origin tier with stock surfaces —
                    # otherwise a flood of domestic offers crowds out the
                    # Internationalist (tier 3 sorts last).
                    cur.execute(
                        """SELECT b.name, b.beer_style, b.abv_percentage,
                                  b.location_tag, b.brewery_state,
                                  b.untappd_rating, b.untappd_url,
                                  o.retailer, o.price, o.url, o.package_info,
                                  o.pack_count, o.unit_price
                           FROM beers b
                           JOIN beer_merchant_offers o ON o.beer_id = b.id
                           WHERE b.beer_style = %s AND o.price IS NOT NULL
                             AND o.price BETWEEN %s AND %s
                           ORDER BY o.unit_price ASC NULLS LAST, o.price ASC
                           LIMIT 200""",
                        (style, budget_min, budget_max),
                    )
                    by_tier: dict[int, list[BeerPick]] = {1: [], 2: [], 3: []}
                    for row in cur.fetchall():  # already value-ordered
                        tier = _beer_tier(row["location_tag"], row["brewery_state"], user_state)
                        rating = float(row["untappd_rating"]) if row["untappd_rating"] is not None else None
                        highly = bool(
                            rating is not None and style_avg is not None
                            and rating >= style_avg + 0.1 and rating >= 3.5
                        )
                        by_tier[tier].append(BeerPick(
                            name=row["name"],
                            beer_style=row["beer_style"] or style,
                            abv_percentage=float(row["abv_percentage"] or 0),
                            price=float(row["price"]),
                            retailer=row["retailer"],
                            url=row["url"] or "",
                            package_info=row["package_info"] or "",
                            pack_count=row["pack_count"] or 1,
                            unit_price=float(row["unit_price"]) if row["unit_price"] is not None else float(row["price"]),
                            tier=tier,
                            tier_label=_BEER_TIER_LABELS[tier],
                            untappd_rating=rating,
                            untappd_url=row["untappd_url"] or "",
                            highly_rated=highly,
                        ))
                    # Up to 10 per tier, grouped Local Hero → Interstater →
                    # Internationalist (value-ordered within each).
                    picks = by_tier[1][:10] + by_tier[2][:10] + by_tier[3][:10]
        except Exception as e:
            logging.getLogger("cellar_sage").warning("beer_picks query failed: %s", e)

    return BeerPicksResponse(style=style, picks=picks)


@app.get("/wine-picks", response_model=WinePicksResponse)
def wine_picks(
    varietal: str = Query(..., max_length=100, description="Canonical varietal name (e.g. 'Sauvignon Blanc')"),
    user_state: Optional[str] = Query(None, max_length=10, description="User's Australian state (e.g. 'SA') for Tier 1 filtering"),
    budget_min: float = Query(0.0, ge=0, description="Minimum price in AUD"),
    budget_max: float = Query(9999.0, ge=0, description="Maximum price in AUD"),
    pref_dry: bool = Query(False, description="Exclude sweet styles from Tier 4 deal pool"),
    pref_organic: bool = Query(False, description="Prioritise organic/preservative-free wines"),
    user_lat: Optional[float] = Query(None, description="User latitude for geo-gated retailer filtering"),
    user_lng: Optional[float] = Query(None, description="User longitude for geo-gated retailer filtering"),
):
    """
    Return up to 4 tiered picks for a given varietal, filtered to the user's budget range.
    Tier 1 = Local Hero, Tier 2 = National Contender, Tier 3 = Internationalist, Tier 4 = The Deal.
    """
    from db_catalog import get_wine_picks
    picks = get_wine_picks(varietal=varietal, user_state=user_state,
                           budget_min=budget_min, budget_max=budget_max, pref_dry=pref_dry,
                           pref_organic=pref_organic, user_lat=user_lat, user_lng=user_lng)
    return WinePicksResponse(varietal=varietal, picks=[WinePick(**p) for p in picks])


@app.get("/buy-options", response_model=list[BuyOption])
def buy_options(
    varietal: str = Query(..., max_length=100, description="Canonical varietal name (e.g. 'Cabernet Sauvignon')"),
    budget_min: float = Query(0.0, ge=0, description="Minimum price in AUD"),
    budget_max: float = Query(9999.0, ge=0, description="Maximum price in AUD"),
    pref_organic: bool = Query(False, description="Prioritise organic/preservative-free wines"),
    user_lat: Optional[float] = Query(None, description="User latitude for geo-gated retailer filtering"),
    user_lng: Optional[float] = Query(None, description="User longitude for geo-gated retailer filtering"),
):
    """
    Return matching listings for a given wine varietal within the user's budget range.
    Used by the Flutter app after the user selects a recommended wine style.
    """
    from db_catalog import get_buy_options
    options = get_buy_options(varietal=varietal, budget_min_aud=budget_min, budget_max_aud=budget_max,
                              pref_organic=pref_organic, user_lat=user_lat, user_lng=user_lng)
    return [BuyOption(**o) for o in options]


def _merchant_response(r, currency_code: str) -> MerchantResponse:
    """Build a MerchantResponse from a MerchantResult, with price converted to currency_code."""
    info = get_currency_info(currency_code)
    # Build the destination search URL first, then wrap with affiliate tracking.
    template = r.merchant.search_url_template
    search_url = template.replace("{brand}", urllib.parse.quote(r.brand)) if template else ""
    aff_template = r.merchant.affiliate_url_template.replace("{brand}", urllib.parse.quote(r.brand)) \
        if r.merchant.affiliate_url_template else ""
    website_url = build_affiliate_url(
        commercial_group=r.merchant.commercial_group,
        destination_url=search_url,
        affiliate_url_template=aff_template,
    )
    return MerchantResponse(
        name=r.merchant.name,
        address=r.merchant.address,
        brand=r.brand,
        region=r.region,
        tier=r.tier,
        tier_label=TIER_LABELS.get(r.tier, "Unknown"),
        distance_km=r.distance_km,
        price_local=convert_from_aud(r.price_aud, currency_code),
        currency_code=info.code,
        currency_symbol=info.symbol,
        website_url=website_url,
        score=r.score,
        confidence_score=r.confidence_score,
        needs_verification=r.needs_verification,
        is_partner=r.is_partner,
        is_online_only=r.merchant.is_online_only,
        commercial_group=r.merchant.commercial_group,
    )


@app.post("/nearby", response_model=NearbyResponse)
def nearby(req: NearbyRequest):
    # Resolve currency: use client-supplied code, fall back to GPS-derived.
    currency_code = req.currency_code.upper() if req.currency_code else \
        lat_lng_to_currency(req.user_lat, req.user_lng)

    # Convert budget from the user's local currency to AUD for catalog filtering.
    budget_min_aud = convert_to_aud(req.budget_min, currency_code)
    budget_max_aud = convert_to_aud(req.budget_max, currency_code) if req.budget_max < 9999.0 else 9999.0

    tiered: TieredMerchantResults = run_merchant_middleware(
        wine_name=req.wine_name,
        user_lat=req.user_lat,
        user_lng=req.user_lng,
        budget_min=budget_min_aud,
        budget_max=budget_max_aud,
        show_global_tier=req.show_global_tier,
    )

    flat = [_merchant_response(r, currency_code) for r in tiered.all_results]

    tier_responses = []
    for t in (1, 2, 3):
        bucket    = tiered.tiers.get(t, [])
        matches   = [_merchant_response(r, currency_code) for r in bucket]
        suppressed = (t == 3 and tiered.tier_3_suppressed)
        blurb_obj  = tiered.blurbs.get(t)
        tier_responses.append(TierResponse(
            tier=t,
            label=TIER_LABELS[t],
            region_hint=TIER_REGION_HINTS[t],
            best_match=matches[0] if matches else None,
            all_matches=matches,
            suppressed=suppressed,
            suppression_reason=tiered.suppression_reason if suppressed else None,
            persona=blurb_obj.persona if blurb_obj else None,
            wit=blurb_obj.wit if blurb_obj else None,
            edu_insight=blurb_obj.edu_insight if blurb_obj else None,
            comparison_note=blurb_obj.comparison_note if blurb_obj else None,
        ))

    return NearbyResponse(
        wine_name=req.wine_name,
        merchants=flat,
        tiers=tier_responses,
        pricing_precedent_applied=tiered.tier_3_suppressed,
    )


# ---------------------------------------------------------------------------
# Internal — cache management
# ---------------------------------------------------------------------------

@app.post("/internal/flush-cache")
def flush_cache(token: str = Query(...)):
    """
    Flush all in-memory caches so the next request pulls fresh data from the DB.
    Called by sync scripts after a data update completes.
    Token must match the CACHE_FLUSH_TOKEN environment variable.
    """
    import os
    expected = os.environ.get("CACHE_FLUSH_TOKEN", "")
    if not expected or token != expected:
        raise HTTPException(status_code=403, detail="Invalid token")

    from db_catalog import _CACHE, _BUY_CACHE, _PICKS_CACHE
    _CACHE.clear()
    _BUY_CACHE.clear()
    _PICKS_CACHE.clear()
    _reload_service()
    log = logging.getLogger("cellar_sage")
    log.info("[Cache] All caches flushed and varietal catalog reloaded via /internal/flush-cache")
    return {"flushed": True, "message": "All caches cleared and varietal catalog reloaded"}
