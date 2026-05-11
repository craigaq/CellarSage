"""
Food pairing modifiers applied to attribute scores.

Keys are backend IDs (snake_case). The frontend maps UI labels → backend IDs
before sending them to the API.

Structure per pairing:
  is_sweet_pairing — True triggers Palate Paradox detection for dry-preferring users
  congruent        — multipliers/boosts that mirror the dish's dominant character
  contrast         — multipliers/boosts that create balance against the dish

Formula applied per attribute (regardless of mode):
  final_attribute = (base_score * multiplier) + boost

Pairing philosophy:
  congruent  — "Match the dish." Find a wine that echoes the food's character.
               Rich food → rich wine. Acidic dish → high-acid wine.
  contrast   — "Balance the dish." Find a wine that cuts against the food.
               Rich food → crisp wine to slice through fat.
               Delicate food → expressive wine to frame it.

Cellar Fox's Logic (the reasoning behind each entry):
  red_meat     — congruent: structure meets richness. contrast: acid cuts fat.
  poultry      — congruent: delicate meets delicate. contrast: expressive frames the bird.
  white_fish   — congruent: bright and clean. contrast: textured and expressive (tannin still off-limits).
  rich_fish    — congruent: freshness balances oily flesh. contrast: body matches body.
  spicy_food   — congruent: cool and soothe the heat. contrast: amplify the fire.
  tomato_sauce — congruent: acid meets acid. contrast: smooth rounds out the tang.
  creamy_sauce — congruent: body matches dairy. contrast: acid cuts the fat.
  greens       — congruent: bright mirrors fresh. contrast: earthy complements vegetal.
  charcuterie  — congruent: balanced all-rounder. contrast: acid cuts salt and fat.
  none         — palate dial stays exactly where the user set it.
"""

FOOD_PAIRING: dict[str, dict] = {

    # Red Meat — fat tames tannin; body provides structure
    "red_meat": {
        "is_sweet_pairing": False,
        "congruent": {
            # Big wine for big meat — fat absorbs tannin, body matches richness
            "multipliers": {
                "tannin": 1.5,   # Fat from steak/lamb cuts through grippy tannins
                "body":   1.2,   # Full body matches the richness of the protein
            },
            "boosts": {},
        },
        "contrast": {
            # Acid-driven wine cuts through the fat instead — Pinot Noir / Barbera style
            "multipliers": {
                "tannin": 0.5,   # Soften grip — the acid does the heavy lifting here
                "body":   0.7,   # Lighter frame lets the brightness shine through
            },
            "boosts": {
                "acidity": 1.0,  # Crispness slices through fat like a sommelier's knife
            },
        },
    },

    # White Meat — light to medium; acidity lifts delicate flavours
    "poultry": {
        "is_sweet_pairing": False,
        "congruent": {
            # Delicate wine for delicate bird — modest grip, clean finish
            "multipliers": {
                "tannin": 0.7,   # Moderate grip only — chicken can't hold heavy tannin
            },
            "boosts": {
                "acidity": 0.5,  # Crispness cuts through poultry fat cleanly
            },
        },
        "contrast": {
            # Fuller, more expressive wine contrasts the bird's mildness — Viognier style
            "multipliers": {},
            "boosts": {
                "body":     0.8,  # Richness frames and elevates the subtle protein
                "aromatics": 0.5, # Floral or stone-fruit notes lift the whole dish
            },
        },
    },

    # Seafood: White Fish / Shellfish — tannin destroys delicate fish oils
    "white_fish": {
        "is_sweet_pairing": False,
        "congruent": {
            # Bright and clean — match the ocean freshness
            "multipliers": {
                "tannin": 0.0,   # Tannin-Free Zone — metallic clash with fish oils
            },
            "boosts": {
                "acidity": 1.5,  # High crispness is essential to complement the brine
            },
        },
        "contrast": {
            # Skin-contact / textured style — expressiveness to frame the delicacy
            # Tannin remains off-limits regardless of mode — it's a physical reaction
            "multipliers": {
                "tannin":  0.0,  # Still cannot work with fish oils — no exceptions
                "acidity": 0.6,  # Step back on the crispness to let texture lead
            },
            "boosts": {
                "body":     0.8, # Fuller frame creates contrast with the fish's delicacy
                "aromatics": 0.5, # Expressive nose lifts the whole pairing
            },
        },
    },

    # Seafood: Salmon / Tuna — richer flesh; can handle a whisper of texture
    "rich_fish": {
        "is_sweet_pairing": False,
        "congruent": {
            # Freshness balances the oily flesh — rosé / light red territory
            "multipliers": {
                "tannin": 0.5,   # Small amount of grip OK — rosé/light red territory
            },
            "boosts": {
                "acidity": 0.5,  # Still want freshness to balance the oily flesh
            },
        },
        "contrast": {
            # Match the salmon's weight with body rather than cutting through with acid
            "multipliers": {
                "tannin":  0.8,  # Richer flesh tolerates more texture
                "acidity": 0.5,  # Step back on crispness — richness leads here
            },
            "boosts": {
                "body": 1.0,     # Full body meets full fish — weight for weight
            },
        },
    },

    # Spicy Food — off-dry wines (Riesling, Gewürztraminer) cool the heat best.
    # is_sweet_pairing=True triggers the Palate Paradox check for dry-preferring users.
    "spicy_food": {
        "is_sweet_pairing": True,
        "congruent": {
            # Cool and soothe — fruit sweetness acts as a fire extinguisher
            "multipliers": {
                "tannin": 0.0,   # Tannin + capsaicin = burning finish — suppress entirely
                "body":   0.5,   # High alcohol fans the flames — dampen body
            },
            "boosts": {
                "aromatics": 1.0,  # Residual fruit/sweetness puts out the fire
            },
        },
        "contrast": {
            # Lean into the fire — bold aromatics amplify the experience
            "multipliers": {
                "tannin": 0.0,   # Still cannot combine tannin with capsaicin
                "body":   0.8,   # Allow a little more weight to carry the intensity
            },
            "boosts": {
                "aromatics": 2.0,  # Maximum fruit expression to match the dish's punch
            },
        },
    },

    # Tomato-based Pasta / Pizza — tomato acid demands a wine that matches it
    "tomato_sauce": {
        "is_sweet_pairing": False,
        "congruent": {
            # Acid meets acid — match the tomato's tartness
            "multipliers": {},
            "boosts": {
                "acidity": 1.5,  # High acidity matches the tomato's natural tartness
            },
        },
        "contrast": {
            # Smooth and round softens the tang instead of matching it
            "multipliers": {
                "acidity": 0.5,  # Step back on crispness — let the body absorb the acid
            },
            "boosts": {
                "body": 0.8,     # Roundness and weight smooth out the tomato's sharpness
            },
        },
    },

    # Creamy / Cheesy Pasta — dairy richness needs body and a touch of acid to cut through
    "creamy_sauce": {
        "is_sweet_pairing": False,
        "congruent": {
            # Match the dairy richness — full body, softened tannin
            "multipliers": {
                "tannin": 0.5,   # Grippy tannin clashes with cream — soften it
            },
            "boosts": {
                "body":    1.0,  # Full body matches the dairy richness
                "acidity": 0.3,  # Light crispness cuts through the fat
            },
        },
        "contrast": {
            # Classic sommelier move — razor acid slices through the fat
            "multipliers": {
                "body":   0.4,   # Suppress the richness — acidity leads
                "tannin": 0.7,   # Moderate grip is fine when acid is the star
            },
            "boosts": {
                "acidity": 1.5,  # High crispness cuts through dairy fat like Chablis
            },
        },
    },

    # Salads / Green Veggies — crisp, herbaceous; light is right
    "greens": {
        "is_sweet_pairing": False,
        "congruent": {
            # Bright wine mirrors the freshness of the dish
            "multipliers": {
                "body":   0.7,   # Heavy reds overwhelm delicate greens
                "tannin": 0.5,   # Grippy tannin clashes with bitter vegetables
            },
            "boosts": {
                "acidity":   1.0,  # Crispness mirrors the freshness of the dish
                "aromatics": 0.5,  # Herbaceous notes complement green flavours
            },
        },
        "contrast": {
            # Earthy, textured wine complements rather than mirrors the greens
            "multipliers": {
                "tannin": 0.8,   # Allow a little grip to ground the earthy pairing
            },
            "boosts": {
                "body":     0.5,  # Some weight to anchor the pairing
                "aromatics": 1.0, # Expressive nose — earthy, spice, or stone fruit
            },
        },
    },

    # Cheese & Charcuterie — the all-rounder; acid cuts through salt and fat
    "charcuterie": {
        "is_sweet_pairing": False,
        "congruent": {
            # Balanced all-rounder — modest acid and body for the full board
            "multipliers": {},
            "boosts": {
                "acidity": 0.5,  # Crispness cuts through cured-meat fat and salt
                "body":    0.3,  # Medium body rounds out the board nicely
            },
        },
        "contrast": {
            # Lean and punchy — acid leads to cut through fat and salt aggressively
            "multipliers": {
                "body": 0.6,     # Lighter frame lets the acid do the work
            },
            "boosts": {
                "acidity": 1.2,  # High crispness cuts through salt, fat, and rich cheeses
            },
        },
    },

    # Dessert / Sweet Treats — residual sugar in wine echoes sweetness in food
    # is_sweet_pairing=True triggers Palate Paradox for dry-preferring users.
    "dessert": {
        "is_sweet_pairing": True,
        "congruent": {
            # Match sweetness with sweetness — aromatic, luscious styles
            "multipliers": {
                "tannin":  0.0,   # Tannin makes sweet foods taste bitter — eliminate it
                "acidity": 0.5,   # Some crispness prevents cloying; not the focus
            },
            "boosts": {
                "aromatics": 1.5, # Fruit-forward and honeyed notes echo the dessert
                "body":      0.5, # A little weight carries the sweetness gracefully
            },
        },
        "contrast": {
            # Bright, high-acid counterpoint cuts through sugar — Sauternes-with-cheese style
            "multipliers": {
                "tannin":  0.0,   # Still kills sweet flavours — no exceptions
                "body":    0.5,   # Lighter style lets the acidity lead
            },
            "boosts": {
                "acidity": 1.5,   # Razor crispness slices through richness and sugar
            },
        },
    },

    # After Dinner / Digestif — fortified, aromatic; the nightcap wines
    # is_sweet_pairing=False — sherry, dry port styles sit outside the paradox check.
    "after_dinner": {
        "is_sweet_pairing": False,
        "congruent": {
            # Match the contemplative, complex after-dinner mood
            "multipliers": {},
            "boosts": {
                "aromatics": 1.2, # Expressive, complex nose — port, muscat, sherry territory
                "body":      0.5, # Weight and warmth suits the end of a meal
            },
        },
        "contrast": {
            # Bright and cleansing after a rich meal — fino sherry style
            "multipliers": {
                "body":   0.5,    # Lighter style refreshes rather than adds weight
                "tannin": 0.3,    # Minimal grip — the palate is tired after dinner
            },
            "boosts": {
                "acidity": 0.8,   # Crispness cuts through richness and refreshes
            },
        },
    },

    # No food — palate dial stays exactly where the user set it
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
