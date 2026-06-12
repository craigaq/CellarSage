"""
Sommelier sanity scenarios for the v2 wine scoring engine.

Each scenario encodes a judgement a working sommelier would make, run through
the production middleware path (interceptor filters + scoring engine).
Run: python test_sommelier_scenarios.py  (uses bundled catalog fallback)
"""

from dotenv import load_dotenv
load_dotenv()

from recommendation_service import RecommendationService, UserPreferences
from interceptor import run_recommendation_middleware
from wine_catalog import load_catalog_from_db

catalog = load_catalog_from_db()
print(f"Loaded {len(catalog)} wine profiles\n")
service = RecommendationService(catalog)

NEUTRAL = dict(crispness_acidity=3, weight_body=3, texture_tannin=3, flavor_intensity=3)

failures = []

def run(label, food="none", mode="congruent", prefs_kw=None, **prefs_extra):
    prefs = UserPreferences(
        **(prefs_kw or NEUTRAL), food_pairing=food, pairing_mode=mode, **prefs_extra,
    )
    results, _ = run_recommendation_middleware(service, prefs)
    print("=" * 78)
    print(f"{label}  [{food} / {mode}]")
    print("-" * 78)
    for r in results[:5]:
        print(f"  TOP  {r.score:.3f}  tan={r.wine.tannin:.0f} swt={r.wine.sweetness:.1f}  {r.wine.name}")
    for r in results[-3:]:
        print(f"  BOT  {r.score:.3f}  tan={r.wine.tannin:.0f}  {r.wine.name}")
    print(f"  WHY: {results[0].explanation}")
    print()
    return results

def check(cond, msg):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}\n")
    if not cond:
        failures.append(msg)

def rank_of(results, name_fragment):
    for i, r in enumerate(results):
        if name_fragment.lower() in r.wine.name.lower():
            return i
    return None

def top_names(results, n):
    return [r.wine.name for r in results[:n]]


# 1. TANNIN REGRESSION — crisp-and-silky palate, no food. The v1 engine let
#    structured reds ride high because "tannin=1" carried only 0.2 weight
#    (Barbera outranked Pinot Grigio and Vermentino). The principle: no
#    grippy wine (tannin ≥ 3) anywhere near the top for this palate.
#    (Barbera itself is tannin=2 in catalog — a legitimately crisp red —
#    so it may sit near the whites; that's correct sommelier behaviour.)
r = run("1. Crisp + zero tannin palate", "none", "congruent",
        prefs_kw=dict(crispness_acidity=5, weight_body=3, texture_tannin=1, flavor_intensity=3))
check(all(res.wine.tannin <= 2 for res in r[:10]),
      f"top-10 all tannin <= 2 (got {[(res.wine.name, res.wine.tannin) for res in r[:10] if res.wine.tannin > 2]})")
barbera, verm = rank_of(r, "Barbera"), rank_of(r, "Vermentino")
check(barbera > verm,
      f"Barbera (rank {barbera+1}) no longer above Vermentino ({verm+1}) — v1 had it 5 ranks higher")

# 2. Tomato pasta congruent — acid meets acid; the Sangiovese canon.
r = run("2. Tomato pasta", "tomato_sauce", "congruent")
check(any("Sangiovese" in n or "Barbera" in n for n in top_names(r, 3)),
      f"Sangiovese/Barbera in tomato top-3 (got {top_names(r, 3)})")

# 3. Salmon congruent — the Pinot Noir classic.
r = run("3. Salmon", "rich_fish", "congruent")
check(any("Pinot Noir" in n or "Gamay" in n for n in top_names(r, 3)),
      f"Pinot/Gamay in salmon top-3 (got {top_names(r, 3)})")

# 4. Spicy congruent — off-dry aromatic whites; tannic/boozy reds sink.
r = run("4. Spicy curry, cool the burn", "spicy_food", "congruent")
check(any("Off-Dry" in n or "Gewürztraminer" in n or "Gewurztraminer" in n for n in top_names(r, 3)),
      f"off-dry/Gewürz in spicy top-3 (got {top_names(r, 3)})")
neb = rank_of(r, "Nebbiolo")
check(neb is not None and neb > len(r) * 0.6,
      f"Nebbiolo in bottom 40% for spicy (rank {neb+1 if neb is not None else '?'}/{len(r)})")

# 5. Spicy contrast — corrected: crisp dry cleanse, not 'amplify the fire'.
r = run("5. Spicy tacos, crisp cleanse", "spicy_food", "contrast")
check(all(res.wine.tannin <= 2 for res in r[:5]),
      f"spicy-contrast top-5 all low-tannin whites/fizz (tannins {[res.wine.tannin for res in r[:5]]})")

# 6. White fish congruent — coastal whites; structured reds nuked.
r = run("6. White fish", "white_fish", "congruent")
check(all(res.wine.tannin <= 2 for res in r[:5]),
      f"white-fish top-5 tannin-free (got {top_names(r, 5)})")
cab = rank_of(r, "Cabernet Sauvignon")
check(cab is not None and cab > len(r) * 0.7,
      f"Cabernet in bottom 30% for white fish (rank {cab+1 if cab is not None else '?'}/{len(r)})")

# 7. Smoked BBQ congruent — the Shiraz handshake.
r = run("7. Smoked BBQ", "smoked_bbq", "congruent")
check(any("Shiraz" in n or "Malbec" in n for n in top_names(r, 3)),
      f"Shiraz/Malbec in BBQ top-3 (got {top_names(r, 3)})")

# 8. Dessert congruent (trust the pairing) — sweet wines only, stickies top.
r = run("8. Dessert", "dessert", "congruent")
check(all(res.wine.style == "Sweet" for res in r),
      f"dessert results all Sweet style ({len(r)} wines)")
check(any("Botrytis" in n or "Late Harvest" in n or "Tawny" in n for n in top_names(r, 2)),
      f"sticky tops dessert (got {top_names(r, 2)})")

# 9. Brave mode + red meat — food chooses: Cabernet country.
r = run("9. Brave mode, steak", "red_meat", "brave")
check(any("Cabernet Sauvignon" in n or "Shiraz" in n or "Malbec" in n for n in top_names(r, 3)),
      f"big structured red tops brave steak (got {top_names(r, 3)})")

# 10. Middle Ground — spicy + dry drinker chooses compromise: whitelist only.
r = run("10. Spicy + dry drinker, middle ground", "spicy_food", "congruent",
        pref_dry=True, override_mode="find_compromise")
from recommendation_service import COMPROMISE_VARIETALS
check(all(res.wine.varietal in COMPROMISE_VARIETALS for res in r),
      f"compromise results all from whitelist (got {sorted({res.wine.varietal for res in r})})")

# 11. Creamy pasta contrast — acid slices cream.
r = run("11. Creamy pasta, cut the cream", "creamy_sauce", "contrast")
check(any("Sauvignon Blanc" in n or "Champagne" in n or "Riesling" in n for n in top_names(r, 3)),
      f"high-acid white/fizz tops creamy-contrast (got {top_names(r, 3)})")

# 12. Charcuterie congruent — the Gamay bistro classic.
r = run("12. Charcuterie board", "charcuterie", "congruent")
check(any("Gamay" in n or "Barbera" in n or "Fino" in n for n in top_names(r, 3)),
      f"bistro classic in charcuterie top-3 (got {top_names(r, 3)})")

print("=" * 78)
if failures:
    print(f"RESULT: {len(failures)} FAILURE(S)")
    for f in failures:
        print(f"  - {f}")
    raise SystemExit(1)
print("RESULT: ALL SCENARIOS PASS")
