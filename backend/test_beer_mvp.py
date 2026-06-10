from recommendation_service import BeerProfile, BeerRecommendationService, UserPreferences
from beer_pairing import FOOD_PAIRING_BEER

# Create sample beers
sample_beers = [
    BeerProfile(
        name="James Squire 150 Lashes Pale Ale",
        ibu_bitterness=50.0,
        body=4.0,
        malt_sweetness=2,
        hop_intensity=7,
        abv_percentage=4.7,
        carbonation_level=4,
        beer_style="Pale Ale",
        sku_id="JS150",
    ),
    BeerProfile(
        name="Cooper's Sparkling Ale",
        ibu_bitterness=30.0,
        body=3.5,
        malt_sweetness=3,
        hop_intensity=4,
        abv_percentage=4.5,
        carbonation_level=3,
        beer_style="Ale",
        sku_id="CSA",
    ),
    BeerProfile(
        name="Little Creatures Pale Ale",
        ibu_bitterness=55.0,
        body=3.8,
        malt_sweetness=2,
        hop_intensity=8,
        abv_percentage=4.3,
        carbonation_level=3,
        beer_style="Pale Ale",
        sku_id="LCPA",
    ),
]

# Create service
service = BeerRecommendationService(sample_beers)

# Test 1: Red meat pairing with congruent mode
prefs = UserPreferences(
    crispness_acidity=3,  # Medium bitterness
    weight_body=4,        # Full body
    texture_tannin=2,     # (ignored for beer)
    flavor_intensity=3,   # Medium hop intensity
    food_pairing="red_meat",
    pairing_mode="congruent",
)

results = service.recommend(prefs)

print("Test 1: Red Meat (Congruent)")
for i, r in enumerate(results):
    print(f"  {i+1}. {r.beer.name} (Score: {r.score:.3f}, Style: {r.beer.beer_style})")
    print(f"     Attributes: {r.attribute_scores}")

# Test 2: Spicy food with contrast mode
prefs2 = UserPreferences(
    crispness_acidity=4,  # Higher bitterness for cutting through heat
    weight_body=2,        # Lower body (alcohol fanning flames)
    texture_tannin=2,
    flavor_intensity=4,   # Hop intensity to match spice
    food_pairing="spicy_food",
    pairing_mode="contrast",
)

results2 = service.recommend(prefs2)

print("\nTest 2: Spicy Food (Contrast)")
for i, r in enumerate(results2):
    print(f"  {i+1}. {r.beer.name} (Score: {r.score:.3f})")

print("\nBeer MVP test complete!")
