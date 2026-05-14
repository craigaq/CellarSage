"""
Cellar Sage — Recommendation Middleware
========================================
Single intercept layer that sits between the service functions and the
API response layer.  All three fail-safe checks flow through here in a
defined order before any data reaches the UI.

Pipeline
--------
  /recommend POST
      └─ run_recommendation_middleware()
            Check 3 — Palate Paradox:  filter catalog by sweetness
                                       score wines
                                       detect dry-preference conflict
              → (list[ScoredWine], PalateParadox | None)

  /nearby POST
      └─ run_merchant_middleware()
            Check 1 — Unicorn Vintage Trap:  price-aware ranking
            Check 2 — Inventory Ghost:       data-freshness confidence
              → list[MerchantResult]

  /check-pairing GET
      → calls service functions directly (lightweight pre-flight;
        not part of the recommendation pipeline)
"""

from __future__ import annotations

import logging

from recommendation_service import (
    RecommendationService,
    UserPreferences,
    WineProfile,
    ScoredWine,
    PalateParadox,
    COMPROMISE_VARIETALS,
    resolve_pairing_conflict,
)

# ---------------------------------------------------------------------------
# Dry-preference filter threshold  (OIV standard)
# ---------------------------------------------------------------------------
# Priority 1 — Residual Sugar  < 5 g/L  → "dry on paper"
_DRY_RS_MAX = 5.0

# Fortified / digestif threshold — ABV >= 14% captures port, sherry, muscat
# without needing an explicit is_fortified flag on WineProfile.
_FORTIFIED_ABV_MIN = 14.0

from dataclasses import dataclass, field

from local_sourcing import (
    MerchantResult,
    find_raw_candidates,
    _avg_market_price,
    calculate_merchant_rank,
    get_stock_certainty,
    _apply_partner_boost,
    PARTNER_CONFIG,
    TIER_LABELS,
    TIER_REGION_HINTS,
)
from content_generator import TierBlurb, generate_tier_blurbs

log = logging.getLogger("cellar_sage.interceptor")


# ---------------------------------------------------------------------------
# Triple-Region tier output model
# ---------------------------------------------------------------------------

@dataclass
class TieredMerchantResults:
    """Structured output from run_merchant_middleware.

    all_results        : Flat sorted list of active (non-suppressed) results.
    tiers              : {1: [...], 2: [...], 3: [...]} — per-tier candidate lists,
                         sorted by Vintage Trap rank within each tier.
    tier_3_suppressed  : True when Pricing Precedent was applied.
    suppression_reason : Human-readable explanation shown in the UI.
    """
    all_results:        list[MerchantResult]
    tiers:              dict[int, list[MerchantResult]] = field(default_factory=dict)
    tier_3_suppressed:  bool = False
    suppression_reason: str  = ""
    blurbs:             dict[int, TierBlurb] = field(default_factory=dict)


# Pricing Precedent: suppress Tier 3 when its cheapest option costs more than
# this multiple of the cheapest Tier 1 option.
_PRICING_PRECEDENT_MULTIPLIER: float = 5.0


# ---------------------------------------------------------------------------
# Check 3 — Palate Paradox  (wine recommendations)
# ---------------------------------------------------------------------------

def _filter_catalog(
    catalog: list[WineProfile],
    prefs: UserPreferences,
) -> list[WineProfile]:
    """
    Return the subset of catalog permitted by the user's override_mode.

    filter_by_profile  — all wines where residual_sugar_gl < 5 g/L (dry on paper)
    find_compromise    — varietal whitelist: COMPROMISE_VARIETALS + style == "Dry"
    use_pairing_logic  — full catalog, no filtering
    """
    mode = prefs.override_mode

    if mode == "filter_by_profile":
        return [w for w in catalog if w.residual_sugar_gl < _DRY_RS_MAX]

    if mode == "find_compromise":
        eligible = []
        for wine in catalog:
            if wine.varietal in COMPROMISE_VARIETALS and wine.style == "Dry":
                eligible.append(wine)
                log.debug(
                    "[Middle Ground] ELIGIBLE  %-22s  varietal=%s  style=%s",
                    wine.name, wine.varietal, wine.style,
                )
            else:
                log.debug(
                    "[Middle Ground] EXCLUDED  %-22s  varietal=%s  style=%s",
                    wine.name, wine.varietal, wine.style,
                )
        return eligible

    # Dessert pairing — only surface genuinely sweet wines so the engine
    # ranks Botrytis Semillon / Rutherglen Muscat / Port above still reds/whites.
    if prefs.food_pairing == "dessert" and mode == "use_pairing_logic":
        return [w for w in catalog if w.style == "Sweet"]

    # After-dinner / digestif — sweet wines plus any fortified style (ABV ≥ 14%).
    # Captures Fino Sherry (Dry but 15% ABV) alongside Port and Muscat.
    if prefs.food_pairing == "after_dinner" and mode == "use_pairing_logic":
        return [
            w for w in catalog
            if w.style == "Sweet" or w.abv_percentage >= _FORTIFIED_ABV_MIN
        ]

    # Dry preference — filter out Sweet wines when user has indicated pref_dry.
    # This handles neutral or savoury food pairings where no Palate Paradox fires.
    # When the user explicitly resolves a Paradox via use_pairing_logic (dessert/
    # after_dinner pairings above), the sweet filter is intentionally bypassed.
    if prefs.pref_dry and mode == "use_pairing_logic":
        return [w for w in catalog if w.style != "Sweet"]

    return catalog


def run_recommendation_middleware(
    service: RecommendationService,
    prefs: UserPreferences,
    top_n: int | None = None,
) -> tuple[list[ScoredWine], PalateParadox | None]:
    """
    Intercept point for wine recommendations.

    1. Palate Paradox catalog filter — strips wines that violate the user's
       dry preference based on their chosen override_mode.
    2. Scores the filtered catalog via the recommendation engine.
    3. Detects any Palate Paradox conflict and returns it alongside results
       so the API layer can include it in the response.
    """
    log.info("=" * 60)
    log.info("[Middleware] run_recommendation_middleware — START")
    log.info(
        "[Middleware] Prefs: food=%s  pref_dry=%s  override_mode=%s",
        prefs.food_pairing, prefs.pref_dry, prefs.override_mode,
    )

    # --- Check 3: Palate Paradox — catalog filter ---
    full_count = len(service.wine_catalog)
    filtered_catalog = _filter_catalog(service.wine_catalog, prefs)
    filtered_count = len(filtered_catalog)

    if filtered_count < full_count:
        log.info(
            "[Palate Paradox] Catalog filtered  mode=%-20s  %d/%d wines eligible",
            prefs.override_mode, filtered_count, full_count,
        )
        if prefs.override_mode == "find_compromise":
            log.info("[Middle Ground] Per-wine eligibility (varietal whitelist):")
            for wine in service.wine_catalog:
                if wine.varietal in COMPROMISE_VARIETALS and wine.style == "Dry":
                    log.info(
                        "  ✓  %-22s  varietal=%-20s  style=%s  — ELIGIBLE",
                        wine.name, wine.varietal, wine.style,
                    )
                else:
                    log.info(
                        "  ✗  %-22s  varietal=%-20s  style=%s  — EXCLUDED",
                        wine.name, wine.varietal, wine.style,
                    )
        else:
            excluded_names = [w.name for w in service.wine_catalog if w not in filtered_catalog]
            log.info("[Palate Paradox] Excluded wines: %s", excluded_names)
    else:
        log.info(
            "[Palate Paradox] No catalog filter  mode=%s  all %d wines eligible",
            prefs.override_mode, full_count,
        )

    results = service.recommend(prefs, top_n=top_n, catalog=filtered_catalog)

    paradox = resolve_pairing_conflict(prefs)
    if paradox:
        log.info(
            "[Palate Paradox] CONFLICT DETECTED  food='%s' is_sweet_pairing=True  pref_dry=True",
            prefs.food_pairing,
        )
        log.info("[Palate Paradox] Resolution UI triggered — options presented to user:")
        for opt in paradox.options:
            marker = " ← RECOMMENDED" if opt["action"] == "use_pairing_logic" else ""
            log.info("  • %-50s  action=%s%s", opt["label"], opt["action"], marker)
    else:
        log.info("[Palate Paradox] No conflict — proceeding normally")

    log.info("[Middleware] run_recommendation_middleware — END")
    log.info("=" * 60)
    return results, paradox


# ---------------------------------------------------------------------------
# Checks 1, 2 & 4 — Unicorn Vintage Trap + Inventory Ghost + Triple-Region Tier
# ---------------------------------------------------------------------------

def run_merchant_middleware(
    wine_name: str,
    user_lat: float,
    user_lng: float,
    budget_min: float = 0.0,
    budget_max: float = 9999.0,
    show_global_tier: bool = False,
) -> TieredMerchantResults:
    """
    Intercept point for merchant results.

    1. Fetches raw candidates (budget-filtered, distance-computed) from the catalog.
    2. Unicorn Vintage Trap — price-aware ranking; collapses distance weight
       and adds greed penalty for overpriced merchants.
    3. Inventory Ghost — annotates each result with a confidence score and
       needs_verification flag based on data source and staleness.
    4. Triple-Region Tier — groups results into Tier 1 (Local Hero / SA),
       Tier 2 (National Rival / interstate AU), and Tier 3 (Global Icon /
       international).  Each tier is sorted by Vintage Trap rank.
       Pricing Precedent: suppresses Tier 3 when its cheapest option costs
       more than 5× the cheapest Tier 1 option, unless show_global_tier=True.

    Returns a TieredMerchantResults containing the flat sorted list and the
    per-tier breakdown.
    """
    log.info("=" * 60)
    log.info("[Middleware] run_merchant_middleware — START  wine='%s'", wine_name)
    log.info("[Middleware] Budget: $%.2f – $%.2f  show_global_tier=%s",
             budget_min, budget_max, show_global_tier)

    # --- Budget-Locked Sort: allow up to 20% above the user's stated budget ---
    # budget_max is treated as the user's target, not a hard ceiling.  The 1.2
    # multiplier surfaces options slightly above budget that may still be best
    # value.  For the default "no budget" case (budget_max=9999) this is still
    # effectively unlimited (9999 × 1.2 = 11 998.8).
    budget_ceiling = budget_max * 1.2
    log.info("[Budget-Locked Sort] user_budget=$%.2f  ceiling=$%.2f  (+20%%)",
             budget_max, budget_ceiling)

    candidates = find_raw_candidates(wine_name, user_lat, user_lng, budget_min, budget_ceiling)
    avg_price   = _avg_market_price(wine_name)
    log.info("[Middleware] %d candidate(s)  avg_market_price=$%.2f",
             len(candidates), avg_price)

    price_ceiling = avg_price * 1.25
    log.info("[Middleware] Vintage Trap ceiling: $%.2f  (avg × 1.25)", price_ceiling)

    for candidate in candidates:
        m     = candidate.merchant
        price = candidate.price_aud
        dist  = candidate.distance_km

        # --- Check 1: Unicorn Vintage Trap ---
        variance_pct = ((price - avg_price) / avg_price * 100) if avg_price > 0 else 0.0
        overpriced   = price > price_ceiling
        if overpriced:
            penalty = (price / avg_price) * 50
            log.info("[Vintage Trap]  DEMOTED   %-35s  $%.2f  %+.0f%%  penalty=%.2f",
                     m.name, price, variance_pct, penalty)
        else:
            log.info("[Vintage Trap]  OK        %-35s  $%.2f  %+.0f%%  WD=10",
                     m.name, price, variance_pct)

        candidate.score = round(calculate_merchant_rank(dist, price, avg_price), 2)

        # --- Check 2: Inventory Ghost ---
        candidate.confidence_score, candidate.needs_verification = get_stock_certainty(
            m.data_source, m.last_updated_hours,
        )
        status = "FLAGGED" if candidate.needs_verification else "TRUSTED"
        log.info("[Inventory Ghost] %-7s  %-35s  src=%-15s  age=%.1fh  conf=%.3f",
                 status, m.name, m.data_source,
                 m.last_updated_hours, candidate.confidence_score)

    # --- Partner boost: subtract rank score for preferred_partner merchants ---
    _apply_partner_boost(candidates)
    if PARTNER_CONFIG.get("preferred_partner"):
        log.info("[Partner] preferred_partner=%s  exclude_rival=%s",
                 PARTNER_CONFIG["preferred_partner"],
                 PARTNER_CONFIG.get("exclude_rival_group", True))

    candidates.sort(key=lambda c: c.score)

    # --- Check 4: Triple-Region Tier grouping ---
    tier_groups: dict[int, list[MerchantResult]] = {1: [], 2: [], 3: []}
    for c in candidates:
        tier_groups[c.tier].append(c)

    # Budget-Locked Sort: within each tier sort by price ascending so that
    # the cheapest option (best value) is always first — i.e. the best_match
    # per tier is the lowest-price option that passed the budget ceiling filter.
    for t in (1, 2, 3):
        tier_groups[t].sort(key=lambda c: c.price_aud)

    log.info("[Triple-Region] Tier breakdown (sorted cheapest-first per tier):")
    for t in (1, 2, 3):
        items = tier_groups[t]
        label = TIER_LABELS[t]
        hint  = TIER_REGION_HINTS[t]
        log.info("  Tier %d (%s — %s): %d result(s)", t, label, hint, len(items))
        for c in items:
            log.info("    %-35s  $%.2f  rank=%.2f  region=%s",
                     c.merchant.name, c.price_aud, c.score, c.region)

    # --- Pricing Precedent: suppress Tier 3 if too expensive vs Tier 1 ---
    tier_3_suppressed  = False
    suppression_reason = ""

    if tier_groups[1] and tier_groups[3] and not show_global_tier:
        cheapest_t1 = min(c.price_aud for c in tier_groups[1])
        cheapest_t3 = min(c.price_aud for c in tier_groups[3])
        ratio = cheapest_t3 / cheapest_t1 if cheapest_t1 > 0 else 0.0
        log.info("[Pricing Precedent] Tier1_min=$%.2f  Tier3_min=$%.2f  ratio=%.2fx  "
                 "threshold=%.1fx", cheapest_t1, cheapest_t3, ratio,
                 _PRICING_PRECEDENT_MULTIPLIER)
        if ratio > _PRICING_PRECEDENT_MULTIPLIER:
            tier_3_suppressed  = True
            suppression_reason = (
                f"The Global Icon option (${cheapest_t3:.2f}) costs "
                f"{ratio:.1f}× more than the Local Hero (${cheapest_t1:.2f}). "
                f"Enable 'Show international options' to unlock."
            )
            log.info("[Pricing Precedent] TIER 3 SUPPRESSED — %s", suppression_reason)
            tier_groups[3] = []
        else:
            log.info("[Pricing Precedent] Tier 3 retained — ratio %.2fx is under %.1fx threshold",
                     ratio, _PRICING_PRECEDENT_MULTIPLIER)
    elif not tier_groups[1] and tier_groups[3]:
        log.info("[Pricing Precedent] No Tier 1 results — Tier 3 shown without price check")

    # --- Content generation: persona-driven blurbs for each visible tier ---
    blurbs = generate_tier_blurbs(tier_groups, wine_name)
    log.info("[Content] Generated blurbs for tiers: %s", sorted(blurbs.keys()))

    # Rebuild flat list from the (possibly filtered) tier groups
    active_results = tier_groups[1] + tier_groups[2] + tier_groups[3]
    active_results.sort(key=lambda c: c.score)

    log.info("[Middleware] Final ranking (%d active results):", len(active_results))
    for i, c in enumerate(active_results, 1):
        badge = "Call to Confirm" if c.needs_verification else "Trusted"
        log.info("  %d. T%d %-35s  rank=%-7.2f  $%.2f  %.2f km  %s",
                 i, c.tier, c.merchant.name, c.score,
                 c.price_aud, c.distance_km, badge)

    log.info("[Middleware] run_merchant_middleware — END")
    log.info("=" * 60)

    return TieredMerchantResults(
        all_results=active_results,
        tiers=tier_groups,
        tier_3_suppressed=tier_3_suppressed,
        suppression_reason=suppression_reason,
        blurbs=blurbs,
    )
