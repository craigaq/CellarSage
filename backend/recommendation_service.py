"""
RecommendationService — core scoring engine for Cellar Sage.

Scoring model (v2 — sommelier-aligned, shared architecture with beer)
---------------------------------------------------------------------
1. TARGETS    Each food/mode defines ideal attribute values (1-5). These are
              blended 65/35 with the user's palate dials, and each wine is
              scored by a weighted Gaussian fit against the blended targets.
              Importance weights are decoupled from dial values — "I want NO
              tannin" now carries as much force as "I want HIGH acidity"
              (the v1 formula weighted preferences by their dial value, so
              low-dial constraints were structurally 5× weaker).
2. AFFINITY   A classic-pairing varietal matrix per food (Sangiovese+tomato,
              Pinot+salmon, Shiraz+BBQ) adds a bonus of up to ±0.12.
3. PENALTIES  Directional `avoid` rules (tannin×fish oils, alcohol×capsaicin,
              umami×heavy tannin) and an intensity-mismatch penalty
              (the sommelier's first rule: match the dish's weight class).

final = clamp01( weighted_gaussian_fit + 0.12×affinity − penalties )

Sweetness (residual-sugar-derived) and alcohol (ABV-derived) are now scored
axes, not just hard filters.
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
    sweetness:   float = field(init=False, default=1.0)  # RS-derived, 1-5
    alcohol:     float = field(init=False, default=3.0)  # ABV-derived, 1-5

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
        # Residual sugar → 1-5 perceived sweetness. Piecewise curve calibrated
        # to OIV bands: ≤2 g/L bone dry, 5 g/L "dry on paper", ~15 g/L off-dry,
        # 45+ g/L dessert-sweet. Perception is roughly logarithmic in RS.
        rs = self.residual_sugar_gl
        if rs <= 2.0:
            self.sweetness = 1.0
        elif rs <= 5.0:
            self.sweetness = round(1.0 + (rs - 2.0) / 3.0 * 0.5, 2)    # 1.0–1.5
        elif rs <= 15.0:
            self.sweetness = round(1.5 + (rs - 5.0) / 10.0, 2)          # 1.5–2.5
        elif rs <= 45.0:
            self.sweetness = round(2.5 + (rs - 15.0) / 30.0 * 1.5, 2)   # 2.5–4.0
        else:
            self.sweetness = round(min(5.0, 4.0 + (rs - 45.0) / 60.0), 2)
        # ABV → 1-5 scale: 8% → 1.0, 15.5%+ → 5.0 (fortified clamps to 5).
        self.alcohol = round(min(5.0, max(1.0, 1.0 + (self.abv_percentage - 8.0) / 1.875)), 2)


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
    roast        — 1-5 roasted-malt character, derived from beer_style
                   (pale lager 1.0 → stout 4.5). Cicerone roast↔char bridge.
    alcohol      — ABV normalised to 1-5 (~3.5% → 1.0, ~9% → 5.0). Used for
                   interaction penalties (alcohol amplifies chilli heat).
    flavor_tags  — style-derived descriptors ("chocolate", "citrus hops", …).
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
    roast:        float = field(init=False, default=1.0)
    alcohol:      float = field(init=False, default=2.0)
    flavor_tags:  list[str] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        from beer_pairing import style_traits

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
        # ABV → 1-5 scale: 3.5% → 1.0, 9.0% → 5.0, clamped
        self.alcohol      = round(min(5.0, max(1.0, 1.0 + (self.abv_percentage - 3.5) / 1.375)), 2)
        # Style-derived roast level and flavour tags
        traits = style_traits(self.beer_style)
        self.roast        = traits["roast"]
        self.flavor_tags  = list(traits["tags"])


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
    explanation: str = ""


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

# All scorable wine attributes (1-5 scale each). The four dial attributes
# plus the two profile-derived axes the v1 engine never scored.
_WINE_ATTRS: tuple[str, ...] = (
    "acidity", "body", "tannin", "aromatics", "sweetness", "alcohol",
)


import math as _math


def _soft_cap(x: float) -> float:
    """Squash a raw score into [0,1) without the hard-clamp pile-up at 1.0.

    Below 0.9 the value is unchanged; at/above 0.9 it compresses smoothly and
    asymptotes toward (but never reaches) 1.0. This keeps genuinely-distinct
    raw scores distinct — the previous min(1.0, ...) clamp flattened several
    strong matches to an identical, misleading "100%".
    """
    if x <= 0.0:
        return 0.0
    if x < 0.9:
        return x
    return 0.9 + 0.1 * (1.0 - _math.exp(-(x - 0.9) / 0.1))

# Per-attribute Gaussian sigma values (in 1-5 scale units).
# Lower sigma = tighter tolerance (palates are more sensitive to that axis).
_WINE_ATTR_SIGMA: dict[str, float] = {
    "acidity":   1.0,   # polarising — tight
    "body":      1.3,
    "tannin":    1.0,   # polarising — tight
    "aromatics": 1.4,
    "sweetness": 1.0,   # off-dry vs dry is very noticeable
    "alcohol":   1.3,
}

# How much the food's ideal profile outweighs the user's palate dial when a
# food is selected. Sommelier logic: the dish sets the frame, the palate tunes it.
_WINE_FOOD_TARGET_WEIGHT = 0.65

# Attributes used to estimate a wine's overall intensity (rule #1: match the
# dish's weight class). Acidity is freshness, not weight — excluded.
_WINE_INTENSITY_ATTRS: tuple[str, ...] = ("body", "tannin", "aromatics", "alcohol")


# ---------------------------------------------------------------------------
# Palate Paradox — sweetness classification + conflict resolution
# ---------------------------------------------------------------------------

# Sweetness thresholds are now carried directly on WineProfile.residual_sugar_gl
# and evaluated by the middleware interceptor — see interceptor.py _filter_catalog().

# find_compromise scoring behaviour (Priority 2 high terpenes / Priority 4
# palate-cleansing acid) is implemented as target/weight raises in
# RecommendationService._build_scoring_context.


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
        ctx = self._build_scoring_context(preferences)

        scored = sorted(
            (self._score_wine(wine, ctx) for wine in wines),
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
        return self._score_wine(wine, self._build_scoring_context(preferences))

    # ------------------------------------------------------------------
    # Private helpers (no instance state — static methods)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_scoring_context(preferences: UserPreferences) -> dict:
        """Resolve blended targets, weights, and pairing config for scoring."""
        food_entry = FOOD_PAIRING.get(preferences.food_pairing, FOOD_PAIRING["none"])
        brave = preferences.pairing_mode == "brave"
        mode = preferences.pairing_mode if preferences.pairing_mode in ("congruent", "contrast") else "congruent"
        cfg = food_entry.get(mode, food_entry["congruent"])

        # User palate targets from the four dials (1-5 ints, used directly).
        # Brave mode hands the palate over to the dish entirely.
        user_targets: dict[str, float] = {} if brave else {
            attr: float(getattr(preferences, pref_field))
            for pref_field, attr in _PREF_FIELD_TO_ATTR.items()
        }

        # Middle Ground (find_compromise): dry but fruit-forward. Pull the
        # aromatics and acidity targets up so expressive, palate-cleansing
        # dry wines lead — the documented Priority 2 / Priority 4 behaviour.
        if preferences.override_mode == "find_compromise" and not brave:
            user_targets["aromatics"] = max(user_targets.get("aromatics", 3.0), 4.2)
            user_targets["acidity"]   = max(user_targets.get("acidity", 3.0), 4.0)

        # Blend food targets (lead) with user targets (tune) per attribute.
        food_targets: dict[str, float] = cfg.get("targets", {})
        targets: dict[str, float] = {}
        weights: dict[str, float] = {}
        for attr in _WINE_ATTRS:
            f_t = food_targets.get(attr)
            u_t = user_targets.get(attr)
            if f_t is not None and u_t is not None:
                targets[attr] = _WINE_FOOD_TARGET_WEIGHT * f_t + (1 - _WINE_FOOD_TARGET_WEIGHT) * u_t
            elif f_t is not None:
                targets[attr] = f_t
            elif u_t is not None:
                targets[attr] = u_t
            else:
                continue  # nothing constrains this attribute
            weights[attr] = cfg.get("weights", {}).get(attr, 1.0)

        if preferences.override_mode == "find_compromise":
            weights["aromatics"] = max(weights.get("aromatics", 1.0), 1.4)
            weights["acidity"]   = max(weights.get("acidity", 1.0), 1.2)

        return {
            "targets": targets,
            "weights": weights,
            "varietals": cfg.get("varietals", {}),
            "avoid": cfg.get("avoid", []),
            "why": cfg.get("why", ""),
            "food_intensity": food_entry.get("intensity"),
        }

    @staticmethod
    def _score_wine(wine: WineProfile, ctx: dict) -> ScoredWine:
        """Sommelier three-step scoring: harmony fit + canon affinity − interactions."""
        # Step 2a: weighted Gaussian fit against blended targets.
        attribute_scores: dict[str, float] = {}
        fit_sum = 0.0
        weight_sum = 0.0
        for attr, target in ctx["targets"].items():
            wine_value = getattr(wine, attr, 0.0)
            sigma = _WINE_ATTR_SIGMA.get(attr, 1.2)
            fit = _math.exp(-((wine_value - target) ** 2) / (2 * sigma ** 2))
            w = ctx["weights"].get(attr, 1.0)
            fit_sum += w * fit
            weight_sum += w
            # Keep UI-label keys for the four dial attributes (frontend contract);
            # the two derived axes are exposed under their technical names.
            attribute_scores[TECHNICAL_TO_UI.get(attr, attr)] = round(fit, 4)
        base = fit_sum / weight_sum if weight_sum else 0.5

        # Step 2b: classic-pairing varietal affinity (the sommelier canon).
        affinity = ctx["varietals"].get(wine.varietal, 0.0)
        affinity_bonus = 0.12 * affinity

        # Step 3: directional interaction penalties.
        penalty = 0.0
        penalty_reason = ""
        for rule in ctx["avoid"]:
            value = getattr(wine, rule["attr"], 0.0)
            if value > rule["above"]:
                penalty += rule["penalty"] * min(2.0, value - rule["above"])
                penalty_reason = rule["reason"]

        # Step 1: intensity match (applied last, but conceptually first).
        food_intensity = ctx["food_intensity"]
        if food_intensity is not None:
            wine_intensity = sum(getattr(wine, a) for a in _WINE_INTENSITY_ATTRS) / len(_WINE_INTENSITY_ATTRS)
            gap = abs(wine_intensity - food_intensity)
            penalty += min(0.18, 0.06 * max(0.0, gap - 1.2))

        score = _soft_cap(base + affinity_bonus - penalty)

        # Human-readable pairing logic for the UI.
        explanation = ctx["why"]
        if affinity >= 0.8:
            explanation = f"{explanation} And {wine.varietal} is a textbook classic for this dish."
        elif penalty_reason and penalty > 0.05:
            explanation = f"{explanation} (Heads-up: {penalty_reason}.)"

        return ScoredWine(
            wine=wine,
            score=round(score, 4),
            attribute_scores=attribute_scores,
            explanation=explanation,
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
    explanation: str = ""


# Maps user palate dials (UserPreferences fields) to beer attributes.
# Beer mode re-labels the four wine dials in the UI:
#   crispness_acidity → bitterness preference (smooth → hop-bitter)
#   weight_body       → body (shared axis)
#   texture_tannin    → carbonation preference (smooth → spritzy)
#   flavor_intensity  → hop/flavour aromatic intensity
_BEER_PREF_FIELD_TO_ATTR: dict[str, str] = {
    "crispness_acidity": "bitterness",
    "weight_body":       "body",
    "texture_tannin":    "carbonation",
    "flavor_intensity":  "aromatics",
}

# All scorable beer attributes (1-5 scale each).
_BEER_ATTRS: tuple[str, ...] = (
    "bitterness", "body", "aromatics", "sweetness", "carbonation", "roast", "alcohol",
)

# Per-attribute Gaussian sigma (tolerance) for target fit.
_BEER_ATTR_SIGMA: dict[str, float] = {
    "bitterness":   1.0,  # polarising — tight tolerance
    "body":         1.1,
    "aromatics":    1.3,
    "sweetness":    1.1,
    "carbonation":  1.2,
    "roast":        1.0,  # roast↔char bridges are specific
    "alcohol":      1.2,
}

# How much the food's ideal profile outweighs the user's palate dial when a
# food is selected. Cicerone logic: the dish sets the frame, the palate tunes it.
_FOOD_TARGET_WEIGHT = 0.65

# Attributes used to estimate a beer's overall intensity (Cicerone rule #1:
# match the strength of beer and dish).
_INTENSITY_ATTRS: tuple[str, ...] = ("bitterness", "body", "roast", "alcohol", "aromatics")


class BeerRecommendationService:
    """
    Cicerone-aligned beer scoring (three-step method).

    1. Match intensity — beers are penalised when their overall intensity is
       far from the dish's intensity.
    2. Find harmonies — Gaussian fit against food-derived attribute targets
       (blended with the user's palate dials and optional style anchors),
       plus a classic-style affinity bonus (stout+BBQ, pilsner+fish, …).
    3. Consider interactions — directional `avoid` penalties for chemistry the
       fit can't see (bitterness amplifies capsaicin, alcohol fans chilli heat,
       hops clash with fish oils).

    Optional `style_anchors` (e.g. ["IPA", "Stout"]) are styles the user
    already enjoys; they pull palate targets toward those styles' typical
    profiles and give those styles a small affinity bump.

    Usage
    -----
    service = BeerRecommendationService(beers)
    results = service.recommend(preferences, top_n=5, style_anchors=["IPA"])
    """

    def __init__(self, beer_catalog: list[BeerProfile]) -> None:
        self.beer_catalog = beer_catalog

    def recommend(
        self,
        preferences: UserPreferences,
        top_n: int | None = None,
        catalog: list[BeerProfile] | None = None,
        style_anchors: list[str] | None = None,
    ) -> list[ScoredBeer]:
        """Score beers and return ranked results."""
        beers = catalog if catalog is not None else self.beer_catalog
        ctx = self._build_context(preferences, style_anchors)

        scored = sorted(
            (self._score_beer(beer, ctx) for beer in beers),
            key=lambda s: s.score,
            reverse=True,
        )
        return scored[:top_n] if top_n is not None else scored

    def score_single(
        self,
        beer: BeerProfile,
        preferences: UserPreferences,
        style_anchors: list[str] | None = None,
    ) -> ScoredBeer:
        """Score a single beer against the given preferences."""
        return self._score_beer(beer, self._build_context(preferences, style_anchors))

    # ── Context building ──────────────────────────────────────────────────────

    @staticmethod
    def _build_context(
        preferences: UserPreferences,
        style_anchors: list[str] | None,
    ) -> dict:
        """Resolve blended targets, weights, and pairing config for scoring."""
        from beer_pairing import FOOD_PAIRING_BEER, STYLE_TRAITS, canonical_style

        food_entry = FOOD_PAIRING_BEER.get(preferences.food_pairing, FOOD_PAIRING_BEER["none"])
        mode = preferences.pairing_mode if preferences.pairing_mode in ("congruent", "contrast") else "congruent"
        cfg = food_entry.get(mode, food_entry["congruent"])

        # User palate targets from the four dials (1-5 ints, used directly).
        user_targets: dict[str, float] = {
            attr: float(getattr(preferences, pref_field))
            for pref_field, attr in _BEER_PREF_FIELD_TO_ATTR.items()
        }

        # Style anchors ("I already drink IPAs") supply ONLY the axes the four
        # dials can't express — sweetness, roast, alcohol. On the frontend the
        # chips pre-fill the dials themselves, so the dial axes (bitterness,
        # body, carbonation, aromatics) are the single source of truth and are
        # left untouched here — no hidden blend, no chip-vs-dial contradiction.
        anchor_canons: set[str] = set()
        if style_anchors:
            anchor_vecs = []
            for s in style_anchors:
                canon = canonical_style(s)
                anchor_canons.add(canon)
                traits = STYLE_TRAITS[canon]
                vec = dict(traits["typical"])
                vec["roast"] = traits["roast"]
                anchor_vecs.append(vec)
            for attr in _BEER_ATTRS:
                if attr in user_targets:
                    continue  # dial axis — owned by the (chip-prefilled) dial
                vals = [v[attr] for v in anchor_vecs if attr in v]
                if vals:
                    user_targets[attr] = sum(vals) / len(vals)  # sweetness / roast / alcohol

        # Blend food targets (lead) with user targets (tune) per attribute.
        food_targets: dict[str, float] = cfg.get("targets", {})
        targets: dict[str, float] = {}
        weights: dict[str, float] = {}
        for attr in _BEER_ATTRS:
            f_t = food_targets.get(attr)
            u_t = user_targets.get(attr)
            if f_t is not None and u_t is not None:
                targets[attr] = _FOOD_TARGET_WEIGHT * f_t + (1 - _FOOD_TARGET_WEIGHT) * u_t
            elif f_t is not None:
                targets[attr] = f_t
            elif u_t is not None:
                targets[attr] = u_t
            else:
                continue  # nothing constrains this attribute
            weights[attr] = cfg.get("weights", {}).get(attr, 1.0)

        return {
            "targets": targets,
            "weights": weights,
            "styles": cfg.get("styles", {}),
            "avoid": cfg.get("avoid", []),
            "why": cfg.get("why", ""),
            "food_intensity": food_entry.get("intensity"),
            "anchor_canons": anchor_canons,
        }

    # ── Scoring ───────────────────────────────────────────────────────────────

    @staticmethod
    def _score_beer(beer: BeerProfile, ctx: dict) -> ScoredBeer:
        from beer_pairing import STYLE_HOOKS, canonical_style

        canon = canonical_style(beer.beer_style)

        # Step 2a: weighted Gaussian fit against blended targets.
        attribute_scores: dict[str, float] = {}
        fit_sum = 0.0
        weight_sum = 0.0
        for attr, target in ctx["targets"].items():
            beer_value = getattr(beer, attr, 0.0)
            sigma = _BEER_ATTR_SIGMA.get(attr, 1.2)
            fit = _math.exp(-((beer_value - target) ** 2) / (2 * sigma ** 2))
            w = ctx["weights"].get(attr, 1.0)
            fit_sum += w * fit
            weight_sum += w
            attribute_scores[attr] = round(fit, 4)
        base = fit_sum / weight_sum if weight_sum else 0.5

        # Step 2b: classic-style affinity (the Cicerone pairing canon) and a
        # small bump for styles the user told us they already enjoy.
        affinity = ctx["styles"].get(canon, 0.0)
        style_bonus = 0.12 * affinity
        anchor_bonus = 0.08 if canon in ctx["anchor_canons"] else 0.0

        # Step 3: directional interaction penalties.
        penalty = 0.0
        penalty_reason = ""
        for rule in ctx["avoid"]:
            value = getattr(beer, rule["attr"], 0.0)
            if value > rule["above"]:
                penalty += rule["penalty"] * min(2.0, value - rule["above"])
                penalty_reason = rule["reason"]

        # Step 1: intensity match (applied last, but conceptually first).
        food_intensity = ctx["food_intensity"]
        if food_intensity is not None:
            beer_intensity = sum(getattr(beer, a) for a in _INTENSITY_ATTRS) / len(_INTENSITY_ATTRS)
            gap = abs(beer_intensity - food_intensity)
            penalty += min(0.18, 0.06 * max(0.0, gap - 1.2))

        score = _soft_cap(base + style_bonus + anchor_bonus - penalty)

        # Human-readable pairing logic for the UI.
        explanation = ctx["why"]
        if affinity >= 0.7 and canon in STYLE_HOOKS:
            explanation = f"{explanation} And {STYLE_HOOKS[canon]}."
        elif penalty_reason and penalty > 0.05:
            explanation = f"{explanation} (Heads-up: {penalty_reason}.)"

        return ScoredBeer(
            beer=beer,
            score=round(score, 4),
            attribute_scores=attribute_scores,
            explanation=explanation,
        )
