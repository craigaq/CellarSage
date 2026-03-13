from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional

from recommendation_service import RecommendationService, WineProfile, UserPreferences
from term_mapping import TECHNICAL_TO_UI
from local_sourcing import find_nearby

app = FastAPI(title="Wine Wizard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Placeholder wine catalog (replace with DB later)
# ---------------------------------------------------------------------------

_CATALOG: list[WineProfile] = [
    WineProfile("Sauvignon Blanc", acidity=4.5, body=2.0, tannin=0.5, aromatics=4.0),
    WineProfile("Chardonnay",      acidity=3.0, body=3.5, tannin=0.5, aromatics=3.5),
    WineProfile("Pinot Noir",      acidity=3.5, body=2.5, tannin=2.5, aromatics=4.0),
    WineProfile("Cabernet Sauvignon", acidity=3.0, body=4.5, tannin=4.5, aromatics=4.5),
    WineProfile("Riesling",        acidity=4.5, body=1.5, tannin=0.5, aromatics=4.5),
    WineProfile("Malbec",          acidity=3.0, body=4.0, tannin=4.0, aromatics=3.5),
    WineProfile("Pinot Grigio",    acidity=3.5, body=2.0, tannin=0.5, aromatics=2.5),
    WineProfile("Syrah/Shiraz",    acidity=3.0, body=4.5, tannin=4.0, aromatics=4.5),
]

_service = RecommendationService(_CATALOG)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class RecommendRequest(BaseModel):
    crispness_acidity: int = Field(..., ge=1, le=5, description="Crispness (Acidity) preference 1-5")
    weight_body: int       = Field(..., ge=1, le=5, description="Weight (Body) preference 1-5")
    texture_tannin: int    = Field(..., ge=1, le=5, description="Texture (Tannin) preference 1-5")
    flavor_intensity: int  = Field(..., ge=1, le=5, description="Flavor Intensity (Aromatics) preference 1-5")
    food_pairing: Optional[str] = Field("None", description="Food pairing selection")
    top_n: Optional[int]   = Field(None, ge=1, description="Return top N results")


class WineResult(BaseModel):
    name: str
    score: float
    attribute_scores: dict[str, float]


class RecommendResponse(BaseModel):
    recommendations: list[WineResult]
    ui_labels: dict[str, str]


class NearbyRequest(BaseModel):
    wine_name: str
    user_lat: float
    user_lng: float
    budget_min: float = 0.0
    budget_max: float = 9999.0


class MerchantResponse(BaseModel):
    name: str
    address: str
    brand: str
    distance_km: float
    price_usd: float
    score: float


class NearbyResponse(BaseModel):
    wine_name: str
    merchants: list[MerchantResponse]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/hello")
def hello():
    return {"message": "Hello from Wine Wizard!"}


@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    try:
        prefs = UserPreferences(
            crispness_acidity=req.crispness_acidity,
            weight_body=req.weight_body,
            texture_tannin=req.texture_tannin,
            flavor_intensity=req.flavor_intensity,
            food_pairing=req.food_pairing,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    results = _service.recommend(prefs, top_n=req.top_n)

    return RecommendResponse(
        recommendations=[
            WineResult(
                name=r.wine.name,
                score=r.score,
                attribute_scores=r.attribute_scores,
            )
            for r in results
        ],
        ui_labels=TECHNICAL_TO_UI,
    )


@app.post("/nearby", response_model=NearbyResponse)
def nearby(req: NearbyRequest):
    results = find_nearby(
        wine_name=req.wine_name,
        user_lat=req.user_lat,
        user_lng=req.user_lng,
        budget_min=req.budget_min,
        budget_max=req.budget_max,
    )
    return NearbyResponse(
        wine_name=req.wine_name,
        merchants=[
            MerchantResponse(
                name=r.merchant.name,
                address=r.merchant.address,
                brand=r.brand,
                distance_km=r.distance_km,
                price_usd=r.merchant.price_usd,
                score=r.score,
            )
            for r in results
        ],
    )
