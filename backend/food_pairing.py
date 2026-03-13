"""
Food pairing modifiers applied to attribute scores.

Structure per pairing:
  multipliers  - multiply the base score for that attribute (0.0 suppresses it)
  boosts       - additive bonus applied after the multiplier

Formula applied per attribute:
  final_attribute = (base_score * multiplier) + boost
"""

FOOD_PAIRING: dict[str, dict] = {
    "Chicken/Fish": {
        "multipliers": {
            "tannin": 0.0,   # Texture (Tannin) suppressed for light proteins
        },
        "boosts": {
            "acidity": 1.5,  # Crispness (Acidity) boosted to complement delicate flavours
        },
    },
    "Red Meat": {
        "multipliers": {
            "tannin": 1.5,   # Texture (Tannin) complemented by high-protein fat
        },
        "boosts": {},
    },
    "Cheese": {
        "multipliers": {},
        "boosts": {
            "body": 0.5,     # Weight (Body) slightly preferred
        },
    },
    "Dessert": {
        "multipliers": {},
        "boosts": {
            "aromatics": 1.0,  # Flavor Intensity (Aromatics) lifted for sweet pairings
        },
    },
    "None": {
        "multipliers": {},
        "boosts": {},
    },
}
