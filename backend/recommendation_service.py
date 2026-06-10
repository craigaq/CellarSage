"""
RecommendationService — core scoring engine for Cellar Sage.

Scoring formula
---------------
For each wine attribute a:
    W_Final(a) = W_P(a) × M_S(a)

Where:
    W_P  = preference weight  → user input (1-5) normalised to [0.2, 1.0]
    M_S  = match score        → how closely the wine's profile matches W_P (0.0-1.0)

Food pairing modifiers are applied on top of W_Final:
    adjusted(a) = (W_Final(a) * food_multiplier(a)) + (food_boost(a) * wine_value(a) / 5.0)

    The boost is proportional to the wine's attribute value so that a
    high-acidity boost in contrast mode rewards genuinely acidic wines
    rather than shifting all wines identically.

The overall wine score is the mean of all adjusted attribute scores.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from food_pairing import FOOD_PAIRING
from term_mapping import TECHNICAL_TO_UI


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class WineProfile:
    """Technical attribute profile for a wine.

    Enhanced Data Schema — real-world measurable fields
    ────────────────────────────────────────────────────
    sku_id             — Unique identifier for inventory tracking.
    acidity_ph         — pH 2.8–4.0; lower = more acidic = higher crispness.
    body               — 1-5 expert rating (Light → Full); no direct lab equivalent.
    tannin_structure   — Integer 1 (Silk/Low) – 5 (Grip/High); tannin perception.
    aromatic_intensity — Integer 1 (Neutral) – 10 (High); drives Middle Ground logic.
    abv_percentage     — Alcohol by Volume %; high ABV + spicy food = burn sensation.
    residual_sugar_gl  — g/L RS; < 5 g/L = "dry on paper" (OIV standard). CRITICAL.
    style              — "Dry" | "Off-Dry" | "Sweet"; distinguishes label variants.
    varietal           — Grape variety for filter matching; defaults to name.

    Internal scoring fields (derived in __post_init__ — NOT constructor parameters)
    ────────────────────────────────────────────────────────────────────────────────
    acidity    — Normalised 1-5 from acidity_ph  (inverted: lower pH → higher score).
                 Formula: 1 + (4.0 − ph) / 1.2 × 4
    tannin     — Float cast of tannin_structure (1-5 → 1.0-5.0).
    aromatics  — aromatic_intensity / 2.0  (maps 1-10 → 0.5-5.0 scoring range).
    alcohol_abv — Alias of abv_percentage (backward-compat with interceptor logging).
    """
    name:               str
    acidity_ph:         float       # pH 2.8–4.0
    body:               float       # 1-5 expert rating
    tannin_structure:   int         # 1-5
    aromatic_intensity: int         # 1-10
    abv_percentage:     float = 13.0
    residual_sugar_gl:  float = 2.0
    style:              str   = "Dry"
    varietal:           str   = ""
    sku_id:             str   = ""
    location_tag:       str   = ""   # "Local" | "National" | "International"
    # ── Derived scoring fields (populated by __post_init__, not in constructor) ──
    acidity:     float = field(init=False, default=0.0)
    tannin:      float = field(init=False, default=0.0)
    aromatics:   float = field(init=False, default=0.0)
    alcohol_abv: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        if not self.varietal:
            self.varietal = self.name
        # Invert pH to a 1-5 crispness score: pH 2.8 → 5.0,  pH 4.0 → 1.0
        # Clamped to [1.0, 5.0] to guard against out-of-range pH values in catalog data.
        self.acidity     = round(min(5.0, max(1.0, 1.0 + (4.0 - self.acidity_ph) / 1.2 * 4.0)), 2)
        self.tannin      = float(self.tannin_structure)
        # Map 1-10 intensity to 0.5-5.0 scoring range (halved)
        self.aromatics   = self.aromatic_intensity / 2.0
        self.alcohol_abv = self.abv_percentage


@dataclass
class BeerProfile:
    """Technical attribute profile for a beer.

    Attributes
    ──────────
    name                — Beer name / brand.
    ibu_bitterness      — International Bitterness Units (0–100+); analogous to wine acidity.
    body                — 1-5 expert rating (Light → Full); shared axis with wine.
    malt_sweetness      — 1-5 malt character scale (dry malt → sweet malt).
    hop_intensity       — 1-10 hop aroma intensity (clean → intensely hoppy).
    abv_percentage      — Alcohol by Volume %.
    carbonation_level   — 1-5 carbonation (flat → highly effervescent).
    beer_style          — Category: IPA, Lager, Stout, Porter, Sour, Wheat, Pilsner, etc.
    sku_id              — Unique identifier for inventory tracking.
    location_tag        — "Local" | "National" | "International".

    Internal scoring fields (derived in __post_init__)
    ──────────────────────────────────────────────────
    bitterness   — IBU normalised to 1-5 range (linear: IBU/20, clamped to 1.0-5.0).
    body, aromatics, alcohol_abv — same as wine scoring semantics.
    sweetness    — Float cast of malt_sweetness (1-5 → 1.0-5.0).
    carbonation  — Float cast of carbonation_level (1-5 → 1.0-5.0).
    """
    name:               str
    ibu_bitterness:     float       # IBUs: 0–100+
    body:               float       # 1-5 expert rating
    malt_sweetness:     int         # 1-5 malt character
    hop_intensity:      int         # 1-10
    abv_percentage:     float = 5.0
    carbonation_level:  int = 3
    beer_style:         str = "Lager"
    sku_id:             str = ""
    location_tag:       str = ""
    # ── Derived scoring fields (populated by __post_init__) ──
    bitterness:   float = field(init=False, default=0.0)
    aromatics:    float = field(init=False, default=0.0)
    sweetness:    float = field(init=False, default=0.0)
    carbonation:  float = field(init=False, default=0.0)
    alcohol_abv:  float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        # Normalise IBUs to 1-5 range: 0 IBU → 1.0, 100 IBU → 5.0, clamped
        self.bitterness   = round(min(5.0, max(1.0, 1.0 + (self.ibu_bitterness / 20.0))), 2)
        # Hop intensity halved (1-10 → 0.5-5.0)
        self.aromatics    = self.hop_intensity / 2.0
        # Malt sweetness as-is (1-5 → 1.0-5.0)
        self.sweetness    = float(self.malt_sweetness)
        # Carbonation as-is (1-5 → 1.0-5.0)
        self.carbonation  = float(self.carbonation_level)
        # Alias for compatibility
        self.alcohol_abv  = self.abv_percentage


# Wines the Cellar Fox targets in "Find a Middle Ground" mode.
# These varietals are technically dry but aromatically intense enough
# to stand in for off-dry pairings with spicy food.
COMPROMISE_VARIETALS: frozenset[str] = frozenset({
    "Gewürztraminer",   # Dry Alsatian — lychee/rose, fermented bone-dry
    "Chenin Blanc",     # Vouvray Sec  — honeyed texture, very high acid
    "Grüner Veltliner", # Federspiel   — stone fruit, crisp, low ABV
    "Viognier",         # Dry          — intensely floral, apricot/peach
})


@dataclass
class UserPreferences:
    """
    User-supplied preference inputs from the UI.

    Attribute names use UI labels; values are integers 1-5.
    food_pairing must be a key present in food_pairing.FOOD_PAIRING.

    pref_dry:
        True when the user has indicated they prefer dry wines.
        Activates Palate Paradox detection for food pairings that favour
        off-dry or sweet wines (e.g. spicy dishes → Riesling).

    override_mode:
        Resolution action chosen after a Palate Paradox is surfaced.
        "filter_by_profile"  — exclude off-dry / sweet wines from results.
        "use_pairing_logic"  — normal scoring; sweet wines are eligible.
        "find_compromise"    — exclude dessert-sweet wines and boost
                               aromatics weight to favour fruit-forward
                               dry options (the middle-ground).
    """
    crispness_acidity: int      # Crispness (Acidity)
    weight_body: int            # Weight (Body)
    texture_tannin: int         # Texture (Tannin)
    flavor_intensity: int       # Flavor Intensity (Aromatics)
    food_pairing: str = "none"
    pref_dry: bool = False
    override_mode: str = "use_pairing_logic"
    pairing_mode: str = "congruent"   # "congruent" | "contrast"


@dataclass
class ScoredWine:
    """A wine together with its computed recommendation score."""
    wine: WineProfile
    score: float
    attribute_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class PalateParadox:
    """
    Returned when a user's dry preference clashes with a food pairing that
    classically calls for an off-dry or sweet wine.

    status:   Always "CONFLICT" when present.
    message:  Human-readable explanation surfaced in the UI.
    options:  Ordered list of resolution choices, each with a display
              'label' and a backend 'action' string.
    """
    status: str
    message: str
    options: list[dict]


@dataclass
class FoodPairingAlert:
    """
    Raised when the user's food choice clashes with their palate profile.

    action_type:
        "OVERRIDE"  — the Cellar Fox strongly recommends adjusting preferences
        "WARNING"   — worth noting but not a hard incompatibility

    new_values:
        Dict of UserPreferences field names → suggested replacement values.
        May contain multiple fields (e.g. spicy food adjusts both weight and flavor).
    """
    id: str
    title: str
    message: str
    action_type: str
    new_values: dict[str, int]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

# Mapping from UserPreferences fields to internal technical attribute names
_PREF_FIELD_TO_ATTR: dict[str, str] = {
    "crispness_acidity": "acidity",
    "weight_body": "body",
    "texture_tannin": "tannin",
    "flavor_intensity": "aromatics",
}

# Ordered tuple of technical attribute names — derived once to avoid repeated dict iteration
_ATTRS: tuple[str, ...] = tuple(_PREF_FIELD_TO_ATTR.values())


import math as _math

def _normalise(user_input: int) -> float:
    """Map a 1-5 user input to a preference weight W_P in [0.2, 1.0]."""
    if not 1 <= user_input <= 5:
        raise ValueError(f"User input must be between 1 and 5, got {user_input}")
    return user_input / 5.0


# Per-attribute Gaussian sigma values (in 1-5 scale units).
# Lower sigma = tighter tolerance (user is more sensitive to that attribute).
# Tannin and acidity are polarising — tight tolerance (1.0).
# Body and aromatics have broader tolerance bands (1.5).
_ATTR_SIGMA: dict[str, float] = {
    "acidity":  1.0,
    "body":     1.5,
    "tannin":   1.0,
    "aromatics": 1.5,
}


def _match_score(preference_weight: float, wine_value: float, attr: str = "") -> float:
    """
    Compute M_S via Gaussian decay: how well the wine's attribute matches the
    user's preference. Returns 1.0 at perfect match, decaying exponentially
    with distance. Replaces the previous linear abs-difference model which
    penalised adjacent values (e.g. user=1, wine=2) as harshly as distant
    values (e.g. user=1, wine=5).

    Both user_input and wine_value are on the 1-5 scale.
    sigma is per-attribute (tannin/acidity tight at 1.0; body/aromatics wide at 1.5).
    """
    sigma = _ATTR_SIGMA.get(attr, 1.0)
    # Convert preference_weight back to 1-5 scale for the distance calculation
    user_input_scaled = preference_weight * 5.0
    diff = wine_value - user_input_scaled
    return _math.exp(-(diff ** 2) / (2 * sigma ** 2))


def _score_attribute(
    attr: str,
    wine_value: float,
    pref_weight: float,
    pairing_cfg: dict,
) -> float:
    """
    Apply the full per-attribute formula and return the adjusted score.

    W_Final  = W_P × M_S  (Gaussian decay match score)
    adjusted = (W_Final × multiplier) + (boost × wine_value / 5.0)

    The boost is proportional to the wine's actual attribute value so that
    e.g. an acidity boost in contrast mode rewards genuinely high-acid wines
    rather than shifting every wine's score identically (which would leave
    the relative ranking unchanged).
    """
    w_final = pref_weight * _match_score(pref_weight, wine_value, attr)
    multiplier = pairing_cfg["multipliers"].get(attr, 1.0)
    boost = pairing_cfg["boosts"].get(attr, 0.0)
    return (w_final * multiplier) + (boost * wine_value / 5.0)


# ---------------------------------------------------------------------------
# Palate Paradox — sweetness classification + conflict resolution
# ---------------------------------------------------------------------------

# Sweetness thresholds are now carried directly on WineProfile.residual_sugar_gl
# and evaluated by the middleware interceptor — see interceptor.py _filter_catalog().

_COMPROMISE_AROMA_BOOST = 0.3  # find_compromise: boost aromatics weight (Priority 2 — high terpenes)
_COMPROMISE_ACID_BOOST  = 0.2  # find_compromise: boost acidity  weight (Priority 4 — palate cleanse)


def resolve_pairing_conflict(prefs: UserPreferences) -> PalateParadox | None:
    """
    Detect a Palate Paradox: user prefers dry wines but has chosen a food
    that classically pairs with off-dry or sweet wines.

    Returns a PalateParadox with three resolution options, or None when there
    is no clash (user does not prefer dry, or food is not a sweet pairing).
    """
    pairing_cfg = FOOD_PAIRING.get(prefs.food_pairing, FOOD_PAIRING["none"])
    if not prefs.pref_dry or not pairing_cfg.get("is_sweet_pairing", False):
        return None
    # Conflict is already resolved — user made an explicit override choice.
    # Only surface the paradox UI when the mode is still the unresolved default.
    if prefs.override_mode != "use_pairing_logic":
        return None

    _messages: dict[str, str] = {
        "spicy_food": (
            "This dish pairs best with off-dry or fruit-forward wine to cool the heat, "
            "but you've told the Cellar Fox you prefer dry. How would you like to proceed?"
        ),
        "dessert": (
            "Dessert calls for a wine with a touch of sweetness — otherwise the wine "
            "tastes thin and bitter alongside the food. You've told the Cellar Fox you "
            "prefer dry. How would you like to proceed?"
        ),
    }
    _default_message = (
        "This dish pairs best with an off-dry or fruit-forward wine, "
        "but you've told the Cellar Fox you prefer dry. How would you like to proceed?"
    )
    message = _messages.get(prefs.food_pairing, _default_message)

    return PalateParadox(
        status="CONFLICT",
        message=message,
        options=[
            {
                "label":  "Stick to my Dry preference",
                "action": "filter_by_profile",
            },
            {
                "label":  "Trust the pairing (Recommended)",
                "action": "use_pairing_logic",
            },
            {
                "label":  "Find a middle ground (Dry but Fruit-Forward)",
                "action": "find_compromise",
            },
        ],
    )


# ---------------------------------------------------------------------------
# Gastro-clash detection — data-driven rule table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _ClashRule:
    """
    A single food/palate incompatibility rule.

    condition:  Lambda that receives UserPreferences and returns True when
                the clash applies.  Evaluated only when food_id matches.
    new_values: Fields to override if the user accepts the Cellar Fox's suggestion.
    """
    food_id:    str
    condition:  Callable[[UserPreferences], bool]
    alert_id:   str
    title:      str
    message:    str
    new_values: dict[str, int]


# Rules are evaluated in order; the first match wins.
# To add a new rule, append a _ClashRule entry — no other code changes needed.
_CLASH_RULES: list[_ClashRule] = [

    # ── White Fish / Shellfish ──────────────────────────────────────────────
    # Tannins react with delicate fish oils → metallic, tinny aftertaste.
    _ClashRule(
        food_id="white_fish",
        condition=lambda p: p.texture_tannin >= 3,
        alert_id="white_fish_tannin_clash",
        title="Cellar Fox Insight: The Metallic Mismatch 🐟",
        message=(
            "You've chosen white fish but your Texture (Tannin) is quite high. "
            "Tannins and delicate fish oils react to create a metallic, tinny taste — "
            "one of the most notorious mismatches in the cellar.\n\n"
            "The Cellar Fox strongly suggests dropping Texture to Silky (1) "
            "so the fish can actually shine."
        ),
        new_values={"texture_tannin": 1},
    ),

    # ── Salmon / Tuna ───────────────────────────────────────────────────────
    # Richer flesh tolerates a little grip — but not a full tannic assault.
    _ClashRule(
        food_id="rich_fish",
        condition=lambda p: p.texture_tannin >= 4,
        alert_id="rich_fish_tannin_clash",
        title="Cellar Fox Insight: Easy on the Grip 🍣",
        message=(
            "Salmon and tuna can handle a light touch of texture — "
            "but at this level the tannins will overpower the fish.\n\n"
            "The Cellar Fox suggests softening Texture to a Gentle (2) "
            "to stay in rosé/light red territory."
        ),
        new_values={"texture_tannin": 2},
    ),

    # ── Spicy Food ──────────────────────────────────────────────────────────
    # High body (alcohol) amplifies capsaicin heat → burning, bitter finish.
    _ClashRule(
        food_id="spicy_food",
        condition=lambda p: p.weight_body >= 4,
        alert_id="spicy_alcohol_clash",
        title="Cellar Fox Insight: Careful with the Heat! 🌶️",
        message=(
            "Bold, heavy wines amplify spicy food — the alcohol fans the flames "
            "and the finish turns bitter.\n\n"
            "The Cellar Fox suggests a Lighter Weight (2) and a touch more "
            "Flavor Intensity (4) — the fruit sweetness will cool the burn."
        ),
        new_values={"weight_body": 2, "flavor_intensity": 4},
    ),

    # ── Tomato-based Pasta / Pizza ──────────────────────────────────────────
    # Flat, low-acid wine tastes dull and flabby against tomato's sharpness.
    _ClashRule(
        food_id="tomato_sauce",
        condition=lambda p: p.crispness_acidity <= 2,
        alert_id="tomato_low_acid_clash",
        title="Cellar Fox Insight: The Flat Tomato Problem 🍅",
        message=(
            "Tomato sauce is highly acidic — a low-crispness wine will taste "
            "flat and lifeless next to it.\n\n"
            "The Cellar Fox suggests lifting Crispness to at least a Medium (3) "
            "so the wine can match the tomato's natural tartness."
        ),
        new_values={"crispness_acidity": 3},
    ),

    # ── Poultry ─────────────────────────────────────────────────────────────
    # Chicken / turkey is too delicate for a heavy tannic assault.
    _ClashRule(
        food_id="poultry",
        condition=lambda p: p.texture_tannin >= 4,
        alert_id="poultry_tannin_clash",
        title="Cellar Fox Insight: Too Much Grip for the Bird 🍗",
        message=(
            "Chicken and turkey have delicate flavours that get steamrolled "
            "by high tannins — the wine ends up tasting bitter and dry.\n\n"
            "The Cellar Fox suggests softening Texture to a Gentle (2) "
            "to let the poultry lead."
        ),
        new_values={"texture_tannin": 2},
    ),
]


def check_food_pairing_conflicts(prefs: UserPreferences) -> FoodPairingAlert | None:
    """
    Scans _CLASH_RULES for the first food/palate mismatch and returns an
    OVERRIDE alert, or None if the profile is harmonious.
    """
    for rule in _CLASH_RULES:
        if prefs.food_pairing == rule.food_id and rule.condition(prefs):
            return FoodPairingAlert(
                id=rule.alert_id,
                title=rule.title,
                message=rule.message,
                action_type="OVERRIDE",
                new_values=rule.new_values,
            )
    return None


# ---------------------------------------------------------------------------
# Brave mode — food-derived ideal palate vector
# ---------------------------------------------------------------------------

def _brave_palate(food_cfg: dict) -> dict[str, float]:
    """Synthesise an ideal palate vector from a food's congruent pairing config.

    Maps each attribute's multiplier/boost to a preference weight so the scoring
    engine ranks wines by food-compatibility rather than user preference.
    multiplier 0→weight 0.2 (banned), 1→0.6 (neutral), 1.5→0.9 (strongly desired).
    """
    congruent   = food_cfg.get("congruent", {"multipliers": {}, "boosts": {}})
    multipliers = congruent.get("multipliers", {})
    boosts      = congruent.get("boosts", {})
    weights: dict[str, float] = {}
    for attr in _ATTRS:
        m = multipliers.get(attr, 1.0)
        b = boosts.get(attr, 0.0)
        base  = min(1.0, max(0.2, m * 0.6))  # 0→0.2, 1→0.6, 1.5→0.9
        bonus = min(0.4, b * 0.15)            # high boost nudges weight up
        weights[attr] = round(min(1.0, base + bonus), 3)
    return weights


# ---------------------------------------------------------------------------
# RecommendationService
# ---------------------------------------------------------------------------

class RecommendationService:
    """
    Scores a list of wines against user preferences and returns ranked results.

    Usage
    -----
    service = RecommendationService(wines)
    results = service.recommend(preferences, top_n=5)
    """

    def __init__(self, wine_catalog: list[WineProfile]) -> None:
        self.wine_catalog = wine_catalog

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(
        self,
        preferences: UserPreferences,
        top_n: int | None = None,
        catalog: list[WineProfile] | None = None,
    ) -> list[ScoredWine]:
        """
        Score the provided catalog (or the full instance catalog if none is
        given) and return wines ranked best-first.

        Catalog filtering (Palate Paradox sweetness gate) is the responsibility
        of the middleware interceptor — pass the pre-filtered list via the
        catalog parameter.  The compromise aromatics boost is applied here
        because it is a scoring concern, not a filtering concern.

        Parameters
        ----------
        preferences:
            User preference inputs (1-5 per attribute) plus optional food
            pairing, pref_dry flag, and override_mode.
        top_n:
            If provided, return only the top N wines.
        catalog:
            Pre-filtered wine list supplied by the middleware interceptor.
            Falls back to the full instance catalog when omitted.
        """
        wines = catalog if catalog is not None else self.wine_catalog
        pref_weights, pairing_cfg = self._build_scoring_context(preferences)

        if preferences.override_mode == "find_compromise":
            # Shallow-copy so we don't mutate the shared dict
            pref_weights = dict(pref_weights)
            # Priority 2 — High Terpenes: boost aromatics so fruit-forward dry wines score higher
            pref_weights["aromatics"] = min(1.0, pref_weights["aromatics"] + _COMPROMISE_AROMA_BOOST)
            # Priority 4 — Medium-High Acidity: boost acidity so palate-cleansing wines score higher
            pref_weights["acidity"]   = min(1.0, pref_weights["acidity"]   + _COMPROMISE_ACID_BOOST)

        scored = sorted(
            (self._score_wine(wine, pref_weights, pairing_cfg) for wine in wines),
            key=lambda s: s.score,
            reverse=True,
        )
        return scored[:top_n] if top_n is not None else scored

    def score_single(
        self,
        wine: WineProfile,
        preferences: UserPreferences,
    ) -> ScoredWine:
        """Score a single wine against the given preferences."""
        pref_weights, pairing_cfg = self._build_scoring_context(preferences)
        return self._score_wine(wine, pref_weights, pairing_cfg)

    # ------------------------------------------------------------------
    # Private helpers (no instance state — static methods)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_scoring_context(
        preferences: UserPreferences,
    ) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
        """Derive pref_weights and pairing_cfg from a UserPreferences instance."""
        food_entry = FOOD_PAIRING.get(preferences.food_pairing, FOOD_PAIRING["none"])
        if preferences.pairing_mode == "brave":
            # Override user palate entirely — use food-ideal weights + congruent config
            pref_weights = _brave_palate(food_entry)
            pairing_cfg  = food_entry["congruent"]
        else:
            pref_weights = {
                attr: _normalise(getattr(preferences, pref_field))
                for pref_field, attr in _PREF_FIELD_TO_ATTR.items()
            }
            mode = preferences.pairing_mode if preferences.pairing_mode in ("congruent", "contrast") else "congruent"
            pairing_cfg = food_entry.get(mode, food_entry["congruent"])
        return pref_weights, pairing_cfg

    @staticmethod
    def _score_wine(
        wine: WineProfile,
        pref_weights: dict[str, float],
        pairing_cfg: dict,
    ) -> ScoredWine:
        """
        Apply the full scoring formula for one wine.

        Step 1: W_Final(a) = W_P(a) × M_S(a)
        Step 2: adjusted(a) = (W_Final(a) × food_multiplier(a)) + food_boost(a)
        Step 3: overall_score = mean(adjusted values)
        """
        attribute_scores: dict[str, float] = {
            TECHNICAL_TO_UI[attr]: round(
                _score_attribute(attr, getattr(wine, attr), pref_weights[attr], pairing_cfg),
                4,
            )
            for attr in _ATTRS
        }
        overall = sum(attribute_scores.values()) / len(attribute_scores)
        return ScoredWine(
            wine=wine,
            score=round(overall, 4),
            attribute_scores=attribute_scores,
        )


# ---------------------------------------------------------------------------
# Beer Recommendation Engine — parallel to Wine
# ---------------------------------------------------------------------------

@dataclass
class ScoredBeer:
    """A beer together with its computed recommendation score."""
    beer: BeerProfile
    score: float
    attribute_scores: dict[str, float] = field(default_factory=dict)


# Beer preference mapping: maps UserPreferences field names to beer attributes
_BEER_PREF_FIELD_TO_ATTR: dict[str, str] = {
    "crispness_acidity": "bitterness",  # IBUs replace wine acidity for cutting fat
    "weight_body": "body",              # Shared axis
    "flavor_intensity": "aromatics",    # Hop intensity replaces wine aromatics
}

# Ordered tuple of beer attribute names for scoring
_BEER_ATTRS: tuple[str, ...] = (
    "bitterness",
    "body",
    "aromatics",
    "sweetness",
    "carbonation",
)

# Per-attribute Gaussian sigma values for beer (tuned for beer palate sensitivity)
_BEER_ATTR_SIGMA: dict[str, float] = {
    "bitterness":   1.2,  # IBUs are polarising — moderate tolerance
    "body":         1.5,  # Broader tolerance
    "aromatics":    1.5,  # Broader tolerance
    "sweetness":    1.3,  # Malt sweetness is noticeable
    "carbonation":  1.4,  # Fizz level is moderately polarising
}


class BeerRecommendationService:
    """
    Scores a list of beers against user preferences and returns ranked results.

    Uses the same UserPreferences input as wine but maps attributes differently:
    - crispness_acidity → bitterness (IBUs)
    - weight_body → body (shared)
    - flavor_intensity → aromatics (hop intensity)
    Plus derived attributes: sweetness, carbonation

    Usage
    -----
    from beer_pairing import FOOD_PAIRING_BEER
    service = BeerRecommendationService(beers)
    results = service.recommend(preferences, top_n=5)
    """

    def __init__(self, beer_catalog: list[BeerProfile]) -> None:
        self.beer_catalog = beer_catalog

    def recommend(
        self,
        preferences: UserPreferences,
        top_n: int | None = None,
        catalog: list[BeerProfile] | None = None,
    ) -> list[ScoredBeer]:
        """Score beers and return ranked results."""
        beers = catalog if catalog is not None else self.beer_catalog
        pref_weights, pairing_cfg = self._build_beer_scoring_context(preferences)

        scored = sorted(
            (self._score_beer(beer, pref_weights, pairing_cfg) for beer in beers),
            key=lambda s: s.score,
            reverse=True,
        )
        return scored[:top_n] if top_n is not None else scored

    def score_single(
        self,
        beer: BeerProfile,
        preferences: UserPreferences,
    ) -> ScoredBeer:
        """Score a single beer against the given preferences."""
        pref_weights, pairing_cfg = self._build_beer_scoring_context(preferences)
        return self._score_beer(beer, pref_weights, pairing_cfg)

    @staticmethod
    def _build_beer_scoring_context(
        preferences: UserPreferences,
    ) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
        """Derive pref_weights and pairing_cfg for beer from UserPreferences."""
        from beer_pairing import FOOD_PAIRING_BEER

        food_entry = FOOD_PAIRING_BEER.get(preferences.food_pairing, FOOD_PAIRING_BEER["none"])
        pref_weights = {
            attr: _normalise(getattr(preferences, pref_field))
            for pref_field, attr in _BEER_PREF_FIELD_TO_ATTR.items()
        }

        # Add derived attributes — user doesn't directly dial these
        # sweetness and carbonation use a neutral 0.6 (middle) default
        pref_weights["sweetness"] = 0.6
        pref_weights["carbonation"] = 0.6

        mode = preferences.pairing_mode if preferences.pairing_mode in ("congruent", "contrast") else "congruent"
        pairing_cfg = food_entry.get(mode, food_entry["congruent"])
        return pref_weights, pairing_cfg

    @staticmethod
    def _score_beer(
        beer: BeerProfile,
        pref_weights: dict[str, float],
        pairing_cfg: dict,
    ) -> ScoredBeer:
        """Score a single beer using the same formula as wine but with beer attributes."""
        attribute_scores: dict[str, float] = {}

        for attr in _BEER_ATTRS:
            beer_value = getattr(beer, attr, 0.0)
            pref_weight = pref_weights.get(attr, 0.6)

            # Use beer-specific Gaussian sigma
            sigma = _BEER_ATTR_SIGMA.get(attr, 1.0)
            user_input_scaled = pref_weight * 5.0
            diff = beer_value - user_input_scaled
            match_score = _math.exp(-(diff ** 2) / (2 * sigma ** 2))

            # Apply food pairing modifiers
            multiplier = pairing_cfg.get("multipliers", {}).get(attr, 1.0)
            boost = pairing_cfg.get("boosts", {}).get(attr, 0.0)

            w_final = pref_weight * match_score
            adjusted = (w_final * multiplier) + (boost * beer_value / 5.0)

            attribute_scores[attr] = round(adjusted, 4)

        overall = sum(attribute_scores.values()) / len(attribute_scores)
        return ScoredBeer(
            beer=beer,
            score=round(overall, 4),
            attribute_scores=attribute_scores,
        )
