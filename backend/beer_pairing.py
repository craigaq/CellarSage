"""
Beer food pairing modifiers — parallel to wine_pairing.py.

Beer pairing philosophy differs from wine:
  - IBU bitterness (Cut) replaces wine acidity for cutting through fat
  - Malt sweetness replaces wine residual sugar for sweetness balance
  - Carbonation = palate cleanser (like acidity in wine)
  - Body and aromatics follow similar logic to wine

Structure mirrors wine pairing: congruent vs contrast modes, multipliers + boosts.

Keys are backend IDs (snake_case).
"""

FOOD_PAIRING_BEER: dict[str, dict] = {

    # Red Meat — fat pairs with bitter hops to cut through richness
    "red_meat": {
        "is_sweet_pairing": False,
        "congruent": {
            # Full-bodied, moderately bitter beer matches the richness — Porter/Stout style
            "multipliers": {
                "body":      1.3,  # Full body matches richness
                "sweetness": 0.5,  # Malt sweetness kept subtle
            },
            "boosts": {
                "bitterness": 0.5,  # Moderate hops to balance fat
            },
        },
        "contrast": {
            # Crisp, bitter IPA cuts through fat like a sommelier's knife
            "multipliers": {
                "body":      0.6,  # Lighter body lets bitterness lead
                "sweetness": 0.3,  # Suppress sweetness
            },
            "boosts": {
                "bitterness": 1.5,  # Aggressive IBUs cut through the richness
            },
        },
    },

    # White Meat — delicate; moderate carbonation lifts the bird
    "poultry": {
        "is_sweet_pairing": False,
        "congruent": {
            # Light, crisp lager pairs with delicate chicken
            "multipliers": {
                "body":       0.6,  # Light frame for light meat
                "bitterness": 0.5,  # Mild hops — chicken can't handle heavy IBUs
            },
            "boosts": {
                "carbonation": 0.8,  # Crispness lifts the bird
            },
        },
        "contrast": {
            # Aromatic wheat beer or pale ale contrasts delicate bird — Hefeweizen style
            "multipliers": {
                "bitterness": 0.3,  # Suppress hops
                "body":       0.8,  # Modest body frames the dish
            },
            "boosts": {
                "aromatics":    1.2,  # Fruity/spicy notes contrast the bird's mildness
                "carbonation": 0.6,  # Step back on crispness — aroma leads
            },
        },
    },

    # White Fish — delicate; carbonation and light body essential
    "white_fish": {
        "is_sweet_pairing": False,
        "congruent": {
            # Crisp pilsner mirrors ocean freshness
            "multipliers": {
                "bitterness": 0.0,  # Bitterness clashes with fish oils (like tannin in wine)
                "body":       0.3,  # Ultra-light body
            },
            "boosts": {
                "carbonation": 1.5,  # Effervescence essential for fish
            },
        },
        "contrast": {
            # Aromatic, textured wheat beer provides contrast without bitterness
            "multipliers": {
                "bitterness": 0.0,  # Still cannot work with fish oils
                "body":       0.7,  # Fuller frame creates contrast
            },
            "boosts": {
                "carbonation": 0.8,  # Moderate crispness
                "aromatics":   0.8,  # Fruity notes lift the delicate fish
            },
        },
    },

    # Salmon / Tuna — richer flesh; can handle modest bitterness
    "rich_fish": {
        "is_sweet_pairing": False,
        "congruent": {
            # Moderate IBU amber ale balances oily fish
            "multipliers": {
                "bitterness": 0.6,  # Some IBUs OK for rich fish
                "body":       0.8,  # Medium body matches salmon's weight
            },
            "boosts": {
                "carbonation": 0.6,  # Crispness helps with fat
            },
        },
        "contrast": {
            # Fuller-bodied stout or porter matches salmon's richness with body
            "multipliers": {
                "bitterness": 0.2,  # Suppress hops — body leads
                "aromatics":  0.4,  # Suppress fruit intensity
            },
            "boosts": {
                "body":        1.4,  # Full body meets rich fish — weight for weight
                "carbonation": 0.4,  # Lower fizz for heaviness
            },
        },
    },

    # Spicy Food — off-dry / sweet beers cool the heat; carbonation cuts capsaicin
    "spicy_food": {
        "is_sweet_pairing": True,
        "congruent": {
            # Sweet, fruity beer cools the fire — fruit lambic or wheat beer
            "multipliers": {
                "bitterness": 0.0,  # Hops + capsaicin = burning finish — eliminate
                "body":       0.5,  # High alcohol fans flames
            },
            "boosts": {
                "sweetness":    1.2,  # Residual sweetness puts out the fire
                "carbonation": 1.0,  # Bubbles help too
            },
        },
        "contrast": {
            # Bold, hoppy beer leans into the fire — double IPA
            "multipliers": {
                "bitterness": 1.3,  # Aggressive IBUs amplify the experience (carefully)
                "body":       1.0,  # Medium body carries the intensity
            },
            "boosts": {
                "aromatics": 1.5,  # Fruity/piney hops match the dish's punch
            },
        },
    },

    # Tomato Sauce — acidity analogue: carbonation cuts, hops support acid-forward profile
    "tomato_sauce": {
        "is_sweet_pairing": False,
        "congruent": {
            # Crisp, moderately bitter lager matches tomato's tartness
            "multipliers": {
                "sweetness": 0.4,  # Keep malt sweetness low
            },
            "boosts": {
                "carbonation": 1.2,  # Effervescence mirrors acidity
                "bitterness":  0.5,  # Moderate hops support the acid profile
            },
        },
        "contrast": {
            # Smooth, sweet beer rounds out tomato's sharpness
            "multipliers": {
                "bitterness":  0.2,  # Suppress hops
                "carbonation": 0.5,  # Suppress fizz
            },
            "boosts": {
                "sweetness": 1.3,  # Malt sweetness softens the tang
                "body":      1.2,  # Full body rounds out the sauce
            },
        },
    },

    # Creamy / Cheesy Pasta — body and sweetness balance dairy richness
    "creamy_sauce": {
        "is_sweet_pairing": False,
        "congruent": {
            # Full-bodied, malty beer matches dairy richness
            "multipliers": {
                "bitterness": 0.4,  # Keep hops moderate
            },
            "boosts": {
                "body":        1.2,  # Full body matches the richness
                "carbonation": 0.7,  # Moderate fizz cuts through fat
            },
        },
        "contrast": {
            # Crisp, bitter beer cuts through cream like a sommelier's blade
            "multipliers": {
                "body":       0.5,  # Suppress fullness
                "sweetness": 0.2,  # Suppress malt sweetness
            },
            "boosts": {
                "bitterness":  1.4,  # IBUs cut dairy fat
                "carbonation": 1.3,  # Fizz aids fat-cutting
            },
        },
    },

    # Salads / Green Veggies — crisp, light beer mirrors the dish's freshness
    "greens": {
        "is_sweet_pairing": False,
        "congruent": {
            # Crisp pilsner or blonde ale mirrors fresh greens
            "multipliers": {
                "body":       0.6,  # Light frame
                "bitterness": 0.6,  # Moderate hops
            },
            "boosts": {
                "carbonation": 1.0,  # Crispness essential
                "aromatics":   0.5,  # Subtle fruit notes
            },
        },
        "contrast": {
            # Earthy, malty beer (amber ale) complements the dish — Sangiovese style
            "multipliers": {
                "bitterness": 0.3,  # Suppress hops
                "carbonation": 0.4,  # Suppress fizz
            },
            "boosts": {
                "body":    1.2,     # Weight anchors the earthy pairing
                "sweetness": 0.6,  # Subtle malt supports earthiness
            },
        },
    },

    # Cheese & Charcuterie — all-rounder; bitter hops cut through salt and fat
    "charcuterie": {
        "is_sweet_pairing": False,
        "congruent": {
            # Balanced amber ale — modest IBUs, moderate body
            "multipliers": {},
            "boosts": {
                "carbonation": 0.7,  # Fizz cuts salt and fat
                "bitterness":  0.4,  # Moderate hops
            },
        },
        "contrast": {
            # Crisp, bitter IPA — hops lead to cut aggressively through cured meats
            "multipliers": {
                "body":      0.5,  # Lighter frame
                "sweetness": 0.2,  # Suppress malt sweetness
            },
            "boosts": {
                "bitterness":  1.5,  # Aggressive IBUs cut salt, fat, and richness
                "carbonation": 1.2,  # High fizz aids cutting
            },
        },
    },

    # Dessert / Sweet Treats — sweet, fruity beer mirrors the sweetness
    "dessert": {
        "is_sweet_pairing": True,
        "congruent": {
            # Sweet, fruity beer (fruit lambic, sweet porter) echoes the dessert
            "multipliers": {
                "bitterness": 0.0,  # Hops clash with sweet foods
                "carbonation": 0.4,  # Suppress fizz — sweetness leads
            },
            "boosts": {
                "sweetness": 1.6,  # Malt sweetness mirrors dessert
                "aromatics": 1.2,  # Fruity hops (fruit beers) enhance the dessert
            },
        },
        "contrast": {
            # Dry, crisp beer cuts through sugar — pale ale with high carbonation
            "multipliers": {
                "bitterness": 0.3,  # Suppress — contrast seeks crispness, not grip
                "sweetness": 0.2,   # Suppress malt sweetness
            },
            "boosts": {
                "carbonation": 1.4,  # High fizz cuts through sugar
                "aromatics":   0.6,  # Subtle fruit notes provide contrast
            },
        },
    },

    # Smoked & BBQ — charred bark, sweet rubs, slow-cook richness — big, bold beer
    "smoked_bbq": {
        "is_sweet_pairing": False,
        "congruent": {
            # Full-bodied, moderately bitter beer (brown ale, amber ale) matches smoke/char
            "multipliers": {
                "body":      1.4,  # Big flavours need big beer
                "bitterness": 0.8,  # Moderate hops complement the smoke
            },
            "boosts": {
                "sweetness": 0.6,  # Subtle malt complements the sweet rub
            },
        },
        "contrast": {
            # Crisp, bitter IPA cuts through the sweet-smoky fat
            "multipliers": {
                "body":      0.6,  # Lighter frame lets bitterness lead
                "sweetness": 0.3,  # Suppress malt sweetness
            },
            "boosts": {
                "bitterness": 1.3,  # IBUs cut through richness and sweetness
                "carbonation": 0.9,  # Moderate fizz aids fat-cutting
            },
        },
    },

    # Vegetarian & Earthy — mushrooms, roasted root veg — earthy, malty beer
    "earthy_veg": {
        "is_sweet_pairing": False,
        "congruent": {
            # Earthy, malty beer (brown ale, porter) echoes umami — Pinot Noir equivalent
            "multipliers": {
                "body":      1.1,  # Medium-full body matches hearty veg
                "bitterness": 0.6,  # Moderate hops support earthiness
            },
            "boosts": {
                "sweetness":    0.7,  # Subtle malt complements umami
                "aromatics":    0.8,  # Earthy/spice notes enhance
                "carbonation": 0.5,  # Low fizz prevents heaviness
            },
        },
        "contrast": {
            # Crisp, aromatic wheat beer lifts the earthiness — Riesling style
            "multipliers": {
                "bitterness": 0.3,  # Suppress hops
                "body":       0.6,  # Lighter frame
            },
            "boosts": {
                "carbonation": 1.1,  # Crispness cuts through earthiness
                "aromatics":   0.8,  # Fruity notes lift and frame
            },
        },
    },

    # No food — user's beer preference dial stays exactly where they set it
    "none": {
        "is_sweet_pairing": False,
        "congruent": {
            "multipliers": {},
            "boosts": {},
        },
        "contrast": {
            "multipliers": {},
            "boosts": {},
        },
    },
}
