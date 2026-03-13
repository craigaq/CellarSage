"""
RecommendationService — core scoring engine for Wine Wizard.

Scoring formula
---------------
For each wine attribute a:
    W_Final(a) = W_P(a) × M_S(a)

Where:
    W_P  = preference weight  → user input (1-5) normalised to [0.2, 1.0]
    M_S  = match score        → how closely the wine's profile matches W_P (0.0-1.0)

Food pairing modifiers are applied on top of W_Final:
    adjusted(a) = (W_Final(a) * food_multiplier(a)) + food_boost(a)

The overall wine score is the mean of all adjusted attribute scores.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from food_pairing import FOOD_PAIRING
from term_mapping import TECHNICAL_TO_UI

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class WineProfile:
    """Technical attribute profile for a wine (all values 1-5 scale)."""
    name: str
    acidity: float
    body: float
    tannin: float
    aromatics: float


@dataclass
class UserPreferences:
    """
    User-supplied preference inputs from the UI.

    Attribute names use UI labels; values are integers 1-5.
    food_pairing must be a key present in food_pairing.FOOD_PAIRING.
    """
    crispness_acidity: int      # Crispness (Acidity)
    weight_body: int            # Weight (Body)
    texture_tannin: int         # Texture (Tannin)
    flavor_intensity: int       # Flavor Intensity (Aromatics)
    food_pairing: str = "None"


@dataclass
class ScoredWine:
    """A wine together with its computed recommendation score."""
    wine: WineProfile
    score: float
    attribute_scores: dict[str, float] = field(default_factory=dict)


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


def _normalise(user_input: int) -> float:
    """Map a 1-5 user input to a preference weight W_P in [0.2, 1.0]."""
    if not 1 <= user_input <= 5:
        raise ValueError(f"User input must be between 1 and 5, got {user_input}")
    return user_input / 5.0


def _match_score(preference_weight: float, wine_value: float) -> float:
    """
    Compute M_S: how well a wine's attribute value satisfies the preference weight.

    Both preference_weight (W_P) and wine_value are on [0.2, 1.0] after normalisation.
    Returns a value in [0.0, 1.0]; 1.0 = perfect match, 0.0 = opposite ends.
    """
    wine_normalised = wine_value / 5.0
    return 1.0 - abs(preference_weight - wine_normalised)


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
    ) -> list[ScoredWine]:
        """
        Score every wine in the catalog and return them ranked best-first.

        Parameters
        ----------
        preferences:
            User preference inputs (1-5 per attribute) plus optional food pairing.
        top_n:
            If provided, return only the top N wines.

        Returns
        -------
        List of ScoredWine sorted by descending score.
        """
        pref_weights, pairing_cfg = self._build_scoring_context(preferences)

        scored = sorted(
            (self._score_wine(wine, pref_weights, pairing_cfg) for wine in self.wine_catalog),
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
    # Private helpers
    # ------------------------------------------------------------------

    def _build_scoring_context(
        self,
        preferences: UserPreferences,
    ) -> tuple[dict[str, float], dict]:
        """Derive pref_weights and pairing_cfg from a UserPreferences instance."""
        pref_weights: dict[str, float] = {
            attr: _normalise(getattr(preferences, pref_field))
            for pref_field, attr in _PREF_FIELD_TO_ATTR.items()
        }
        pairing_cfg = FOOD_PAIRING.get(preferences.food_pairing, FOOD_PAIRING["None"])
        return pref_weights, pairing_cfg

    # ------------------------------------------------------------------
    # Internal scoring
    # ------------------------------------------------------------------

    def _score_wine(
        self,
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
        attrs = tuple(_PREF_FIELD_TO_ATTR.values())  # single source of truth
        attribute_scores: dict[str, float] = {}

        for attr in attrs:
            wine_value: float = getattr(wine, attr)
            w_p = pref_weights[attr]
            m_s = _match_score(w_p, wine_value)

            # Core formula: W_Final = W_P × M_S
            w_final = w_p * m_s

            # Food pairing adjustments
            multiplier = pairing_cfg["multipliers"].get(attr, 1.0)
            boost = pairing_cfg["boosts"].get(attr, 0.0)
            adjusted = (w_final * multiplier) + boost

            # Store under the UI-friendly label
            ui_label = TECHNICAL_TO_UI[attr]
            attribute_scores[ui_label] = round(adjusted, 4)

        overall = sum(attribute_scores.values()) / len(attribute_scores)
        return ScoredWine(
            wine=wine,
            score=round(overall, 4),
            attribute_scores=attribute_scores,
        )
