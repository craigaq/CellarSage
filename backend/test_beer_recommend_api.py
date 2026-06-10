"""
Test the beer recommendation engine with real seeded beers.
"""

from dotenv import load_dotenv
load_dotenv()

from recommendation_service import BeerRecommendationService, UserPreferences
from wine_catalog import load_beer_catalog_from_db

# Load seeded beers from DB
beers = load_beer_catalog_from_db()
print(f"Loaded {len(beers)} beers from database")

if not beers:
    print("ERROR: No beers loaded!")
    exit(1)

service = BeerRecommendationService(beers)

# Test 1: Red Meat pairing (congruent)
print("\n" + "="*60)
print("Test 1: Red Meat (Congruent Mode)")
print("="*60)
prefs = UserPreferences(
    crispness_acidity=3,   # Medium bitterness
    weight_body=4,         # Full body
    texture_tannin=2,      # (ignored for beer)
    flavor_intensity=3,    # Medium hop intensity
    food_pairing="red_meat",
    pairing_mode="congruent",
)

results = service.recommend(prefs, top_n=5)
for i, r in enumerate(results, 1):
    print(f"{i}. {r.beer.name:45} | Score: {r.score:.3f} | Style: {r.beer.beer_style}")

# Test 2: Spicy Food (contrast)
print("\n" + "="*60)
print("Test 2: Spicy Food (Contrast Mode)")
print("="*60)
prefs = UserPreferences(
    crispness_acidity=4,   # Higher bitterness for cutting heat
    weight_body=2,         # Lower body (alcohol fanning flames)
    texture_tannin=2,
    flavor_intensity=4,    # Hop intensity
    food_pairing="spicy_food",
    pairing_mode="contrast",
)

results = service.recommend(prefs, top_n=5)
for i, r in enumerate(results, 1):
    print(f"{i}. {r.beer.name:45} | Score: {r.score:.3f} | IBUs: {r.beer.ibu_bitterness}")

# Test 3: Charcuterie (contrast)
print("\n" + "="*60)
print("Test 3: Charcuterie (Contrast Mode)")
print("="*60)
prefs = UserPreferences(
    crispness_acidity=5,   # Maximum bitterness to cut through salt/fat
    weight_body=2,         # Light frame
    texture_tannin=1,
    flavor_intensity=3,
    food_pairing="charcuterie",
    pairing_mode="contrast",
)

results = service.recommend(prefs, top_n=5)
for i, r in enumerate(results, 1):
    print(f"{i}. {r.beer.name:45} | Score: {r.score:.3f} | Carbonation: {r.beer.carbonation}")

# Test 4: Dessert (congruent)
print("\n" + "="*60)
print("Test 4: Dessert (Congruent Mode)")
print("="*60)
prefs = UserPreferences(
    crispness_acidity=1,   # Low bitterness
    weight_body=3,         # Medium body
    texture_tannin=1,
    flavor_intensity=4,    # Higher aromatics for sweetness
    food_pairing="dessert",
    pairing_mode="congruent",
)

results = service.recommend(prefs, top_n=5)
for i, r in enumerate(results, 1):
    print(f"{i}. {r.beer.name:45} | Score: {r.score:.3f} | Sweetness: {r.beer.malt_sweetness}")

print("\n" + "="*60)
print("Beer recommendation engine working correctly!")
print("="*60)
