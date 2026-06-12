"""
Cicerone sanity scenarios for the v2 beer scoring engine.

Each scenario encodes a judgement a Certified Cicerone would make. The test
prints the top 5 + bottom 3 for each and asserts the headline expectations.
Run: python test_cicerone_scenarios.py  (uses the live beers table)
"""

from dotenv import load_dotenv
load_dotenv()

from recommendation_service import BeerRecommendationService, UserPreferences
from wine_catalog import load_beer_catalog_from_db

catalog = load_beer_catalog_from_db()
print(f"Loaded {len(catalog)} beers from DB\n")
assert catalog, "beers table is empty — seed it first"

service = BeerRecommendationService(catalog)

NEUTRAL = dict(crispness_acidity=3, weight_body=3, texture_tannin=3, flavor_intensity=3)

def run(label, food, mode, anchors=None, prefs_kw=None):
    prefs = UserPreferences(
        **(prefs_kw or NEUTRAL),
        food_pairing=food,
        pairing_mode=mode,
    )
    results = service.recommend(prefs, style_anchors=anchors)
    print("=" * 78)
    print(f"{label}  [{food} / {mode}" + (f" / anchors={anchors}]" if anchors else "]"))
    print("-" * 78)
    for r in results[:5]:
        print(f"  TOP  {r.score:.3f}  {r.beer.beer_style:<16} {r.beer.name}")
    for r in results[-3:]:
        print(f"  BOT  {r.score:.3f}  {r.beer.beer_style:<16} {r.beer.name}")
    print(f"  WHY: {results[0].explanation}")
    print()
    return results

failures = []

def check(cond, msg):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {msg}\n")
    if not cond:
        failures.append(msg)

def styles_of(results, n):
    return [r.beer.beer_style for r in results[:n]]

def rank_of(results, name_fragment):
    for i, r in enumerate(results):
        if name_fragment.lower() in r.beer.name.lower():
            return i
    return None


# 1. Spicy congruent — cool the fire. No IPAs near the top; big IBU beers sink.
r = run("1. Spicy curry, cool-the-fire", "spicy_food", "congruent")
top5 = styles_of(r, 5)
check(not any("IPA" in s for s in top5), f"no IPAs in spicy top-5 (got {top5})")
hop_hog = rank_of(r, "Hop Hog")
check(hop_hog is not None and hop_hog > len(r) * 0.6,
      f"Feral Hop Hog (70 IBU) in bottom 40% for spicy food (rank {hop_hog + 1}/{len(r)})")

# 2. Spicy contrast — crisp cleanse, NOT 'amplify the burn'.
r = run("2. Spicy tacos, crisp cleanse", "spicy_food", "contrast")
top5 = styles_of(r, 5)
check(any(s in ("Lager", "Pilsner", "Pale Lager") for s in top5),
      f"crisp lager/pilsner present in spicy-contrast top-5 (got {top5})")
check(not any("IPA" in s for s in top5), f"no IPAs in spicy-contrast top-5 (got {top5})")

# 3. White fish congruent — delicate; pilsner/lager country, stouts & IPAs sink.
r = run("3. White fish, delicate", "white_fish", "congruent")
top5 = styles_of(r, 5)
check(all(s in ("Lager", "Pilsner", "Pale Lager", "Golden Ale", "Blonde Ale") for s in top5),
      f"white-fish top-5 all light styles (got {top5})")
bottom5 = [r_.beer.beer_style for r_ in r[-5:]]
check(any(("IPA" in s or s == "Stout") for s in bottom5),
      f"IPAs/Stouts in white-fish bottom-5 (got {bottom5})")

# 4. Smoked BBQ congruent — roast↔smoke bridge: stout/porter/amber lead.
r = run("4. Smoked BBQ, roast bridge", "smoked_bbq", "congruent")
top5 = styles_of(r, 5)
check(any(s in ("Stout", "Porter", "Amber Ale", "Black IPA", "Strong Ale") for s in top5[:3]),
      f"dark/roasty style in BBQ top-3 (got {top5[:3]})")

# 5. Dessert congruent — roast-chocolate bridge: stouts top.
r = run("5. Chocolate dessert", "dessert", "congruent")
check(styles_of(r, 1)[0] in ("Stout", "Porter", "Strong Ale"),
      f"stout/porter tops dessert (got {styles_of(r, 1)[0]})")

# 6. Red meat contrast — the classic burger IPA.
r = run("6. Burger, cut-the-fat", "red_meat", "contrast")
top5 = styles_of(r, 5)
check(any("IPA" in s or s == "Pale Ale" for s in top5[:3]),
      f"IPA/Pale Ale in burger-contrast top-3 (got {top5[:3]})")

# 7. No food + IPA anchor — user's style identity drives results.
r = run("7. Just sipping, loves IPAs", "none", "congruent", anchors=["IPA"])
top5 = styles_of(r, 5)
check(sum(1 for s in top5 if "IPA" in s or s == "Pale Ale") >= 3,
      f"hop-forward styles dominate anchored sipping top-5 (got {top5})")

print("=" * 78)
if failures:
    print(f"RESULT: {len(failures)} FAILURE(S)")
    for f in failures:
        print(f"  - {f}")
    raise SystemExit(1)
print("RESULT: ALL SCENARIOS PASS")
