import logging
from dotenv import load_dotenv
load_dotenv()  # loads backend/.env in local dev; no-op in production

from fastapi import FastAPI, HTTPException, Query

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
# Show per-criterion Middle Ground debug lines from the interceptor
logging.getLogger("cellar_sage.interceptor").setLevel(logging.DEBUG)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

import dataclasses
import urllib.parse

from recommendation_service import (
    RecommendationService, WineProfile, UserPreferences,
    check_food_pairing_conflicts,
    resolve_pairing_conflict,
)
from wine_catalog import WINE_DATABASE
from term_mapping import TECHNICAL_TO_UI
from interceptor import run_recommendation_middleware, run_merchant_middleware, TieredMerchantResults
from local_sourcing import TIER_LABELS, TIER_REGION_HINTS
from currency import convert_from_aud, convert_to_aud, lat_lng_to_currency, get_info as get_currency_info
from affiliate_config import build_affiliate_url

app = FastAPI(title="Cellar Sage API")


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
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Wine catalog is maintained in wine_catalog.py (Enhanced Data Schema)
_CATALOG = WINE_DATABASE

_service = RecommendationService(_CATALOG)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class RecommendRequest(BaseModel):
    crispness_acidity: int = Field(..., ge=1, le=5, description="Crispness (Acidity) preference 1-5")
    weight_body: int       = Field(..., ge=1, le=5, description="Weight (Body) preference 1-5")
    texture_tannin: int    = Field(..., ge=1, le=5, description="Texture (Tannin) preference 1-5")
    flavor_intensity: int  = Field(..., ge=1, le=5, description="Flavor Intensity (Aromatics) preference 1-5")
    food_pairing: Optional[str] = Field("none", description="Food pairing backend ID")
    top_n: Optional[int]   = Field(None, ge=1, description="Return top N results")
    pref_dry: bool         = Field(False, description="User prefers dry wines")
    override_mode: str     = Field(
        "use_pairing_logic",
        description="Palate Paradox resolution: filter_by_profile | use_pairing_logic | find_compromise",
    )
    pairing_mode: str      = Field(
        "congruent",
        description="Pairing philosophy: congruent (match the dish) | contrast (balance the dish)",
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


class NearbyRequest(BaseModel):
    wine_name: str
    user_lat: float
    user_lng: float
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/hello")
def hello():
    return {"message": "Hello from Cellar Sage!"}


@app.get("/check-pairing", response_model=CheckPairingResponse)
def check_pairing(
    food_type: str = Query(..., description="Food pairing selection"),
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
            "title": "🧙‍♂️ Your Wizard Senses a Disturbance",
            "message": (
                "Ah — Light Weight with High Texture. Bold. Rare. "
                "Like a featherweight boxer with an iron grip.\n\n"
                "Most light-bodied wines keep their tannins polite and their manners impeccable. "
                "For a wider selection from the cellar, the Wizard suggests softening the Texture."
            ),
            "field": "texture_tannin",
            "suggested_value": 2,
        }
    # Low flavor + high acidity — sharp without expression
    if prefs.flavor_intensity <= 1 and prefs.crispness_acidity >= 4:
        return {
            "title": "🧙‍♂️ The Wizard Raises an Eyebrow",
            "message": (
                "Maximum Crispness with barely any Flavor Intensity — "
                "you're asking for a razor edge with nothing behind it.\n\n"
                "The sharpness would dominate completely. "
                "The Wizard suggests lifting Flavor Intensity so there's something to cut through."
            ),
            "field": "flavor_intensity",
            "suggested_value": 3,
        }
    # Maximum tannin + maximum acidity — very aggressive palate
    if prefs.texture_tannin >= 5 and prefs.crispness_acidity >= 5:
        return {
            "title": "🧙‍♂️ The Wizard Is Impressed (and Concerned)",
            "message": (
                "Maximum Texture AND Maximum Crispness. "
                "You want every molecule of that wine to fight back.\n\n"
                "This is a very narrow field — few wines survive both extremes well. "
                "The Wizard suggests dialling Crispness back slightly for a more satisfying match."
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
                raw_metrics=_raw_metrics_dict(r.wine),
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
