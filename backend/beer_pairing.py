"""
Beer food pairing — Cicerone-aligned model (v2).

Why v2? The v1 multiplier/boost system (ported from wine) could only express
"reward attribute" or "ignore attribute" — it could not express "this attribute
is actively BAD here" (e.g. high IBU with delicate fish, alcohol with chilli
heat). Cicerone methodology needs directional logic.

The v2 model encodes the Cicerone Certification Program's three-step method:

  1. MATCH INTENSITY  — delicate dishes need delicate beers; bold needs bold.
     Each food carries an `intensity` (1-5); beers compute their own intensity
     and are penalised for large mismatches. This is the Cicerone's first rule.

  2. FIND HARMONIES   — flavour bridges (roast↔char, caramel↔maillard,
     herbal hops↔greens). Encoded two ways:
       - `targets`: ideal attribute values (1-5) per food/mode. Scoring is a
         Gaussian fit against these targets, blended with the user's palate.
       - `styles`: a style-affinity map (-1..+1) encoding classic Cicerone
         pairings (stout+BBQ, pilsner+fish, IPA+burger) directly.

  3. CONSIDER INTERACTIONS — directional chemistry the fit can't capture:
       - `avoid`: signed penalty rules, e.g. bitterness amplifies capsaicin,
         alcohol fans chilli flames, hops clash with fish oils.
     Carbonation/bitterness "cut" of fat is handled via targets (high
     carbonation targets for rich foods) in BOTH modes — cutting is the third
     Cicerone mode (complement / contrast / cut) and is almost always welcome
     with rich food, not just in "contrast".

Modes remain `congruent` (complement) and `contrast` for UI continuity.

All attribute values are on a 1-5 scale:
  bitterness   — IBU-derived (IBU/20 + 1, clamped)
  body         — light → full
  sweetness    — malt sweetness, dry → sweet
  carbonation  — flat → effervescent
  aromatics    — hop aroma intensity (hop_intensity / 2)
  roast        — derived from style: pale → roasty (chocolate/coffee)
  alcohol      — ABV-normalised: ~3.5% → 1.0, ~9% → 5.0

Keys are backend food IDs (snake_case).
"""

# ── Style knowledge ───────────────────────────────────────────────────────────
# Canonical style traits: roast level, flavour tags, and a typical attribute
# vector (used to derive roast/tags per beer, and to turn user "style anchors"
# into palate targets).

_STYLE_ALIASES: dict[str, str] = {
    "pale lager":     "Lager",
    "extra pale ale": "Pale Ale",
    "xpa":            "Pale Ale",
    "blonde ale":     "Golden Ale",
    "hefeweizen":     "Wheat",
    "wheat beer":     "Wheat",
    "witbier":        "Wheat",
    "old ale":        "Strong Ale",
    "barleywine":     "Strong Ale",
}

STYLE_TRAITS: dict[str, dict] = {
    "Lager": {
        "roast": 1.0,
        "tags": ["clean", "crisp"],
        "typical": {"bitterness": 1.8, "body": 2.6, "sweetness": 1.6, "carbonation": 4.0, "aromatics": 1.5},
    },
    "Pilsner": {
        "roast": 1.0,
        "tags": ["crisp", "herbal hops"],
        "typical": {"bitterness": 2.8, "body": 2.6, "sweetness": 1.4, "carbonation": 4.2, "aromatics": 2.6},
    },
    "Pale Ale": {
        "roast": 1.3,
        "tags": ["citrus hops", "floral"],
        "typical": {"bitterness": 3.2, "body": 3.2, "sweetness": 2.0, "carbonation": 3.0, "aromatics": 3.4},
    },
    "IPA": {
        "roast": 1.0,
        "tags": ["citrus", "pine", "resinous hops"],
        "typical": {"bitterness": 4.2, "body": 3.4, "sweetness": 1.9, "carbonation": 3.0, "aromatics": 4.4},
    },
    "Hazy IPA": {
        "roast": 1.0,
        "tags": ["tropical", "juicy"],
        "typical": {"bitterness": 3.0, "body": 3.4, "sweetness": 2.4, "carbonation": 2.8, "aromatics": 4.4},
    },
    "Black IPA": {
        "roast": 3.6,
        "tags": ["pine hops", "roasted malt"],
        "typical": {"bitterness": 4.4, "body": 3.6, "sweetness": 2.0, "carbonation": 3.0, "aromatics": 4.2},
    },
    "Golden Ale": {
        "roast": 1.1,
        "tags": ["light fruit", "easy-drinking"],
        "typical": {"bitterness": 2.2, "body": 2.8, "sweetness": 2.2, "carbonation": 3.2, "aromatics": 2.4},
    },
    "Amber Ale": {
        "roast": 2.2,
        "tags": ["caramel", "toffee"],
        "typical": {"bitterness": 2.9, "body": 3.4, "sweetness": 2.8, "carbonation": 2.8, "aromatics": 2.6},
    },
    "Brown Ale": {
        "roast": 3.0,
        "tags": ["nutty", "caramel"],
        "typical": {"bitterness": 2.6, "body": 3.5, "sweetness": 2.9, "carbonation": 2.6, "aromatics": 2.2},
    },
    "Porter": {
        "roast": 4.0,
        "tags": ["chocolate", "coffee"],
        "typical": {"bitterness": 3.0, "body": 3.9, "sweetness": 2.9, "carbonation": 2.4, "aromatics": 2.2},
    },
    "Stout": {
        "roast": 4.5,
        "tags": ["chocolate", "coffee", "roast"],
        "typical": {"bitterness": 3.4, "body": 4.2, "sweetness": 2.8, "carbonation": 2.4, "aromatics": 2.4},
    },
    "Wheat": {
        "roast": 1.0,
        "tags": ["banana", "clove", "soft"],
        "typical": {"bitterness": 1.6, "body": 2.8, "sweetness": 2.6, "carbonation": 3.8, "aromatics": 3.2},
    },
    "Sour": {
        "roast": 1.0,
        "tags": ["tart", "fruity"],
        "typical": {"bitterness": 1.4, "body": 2.2, "sweetness": 2.4, "carbonation": 4.0, "aromatics": 3.4},
    },
    "Strong Ale": {
        "roast": 2.6,
        "tags": ["caramel", "dark fruit", "warming"],
        "typical": {"bitterness": 2.8, "body": 4.0, "sweetness": 3.2, "carbonation": 2.2, "aromatics": 2.6},
    },
    # Australian sparkling/dinner ale (e.g. Coopers Sparkling) — estery, lively.
    "Ale": {
        "roast": 1.6,
        "tags": ["fruity esters", "lively"],
        "typical": {"bitterness": 2.2, "body": 3.2, "sweetness": 2.6, "carbonation": 3.4, "aromatics": 2.6},
    },
}

_STYLE_FALLBACK = "Golden Ale"  # balanced middle-ground when style is unknown


def canonical_style(style: str) -> str:
    """Resolve a raw beer_style string to a STYLE_TRAITS key."""
    if not style:
        return _STYLE_FALLBACK
    s = style.strip()
    if s in STYLE_TRAITS:
        return s
    return _STYLE_ALIASES.get(s.lower(), s if s in STYLE_TRAITS else _STYLE_FALLBACK)


def style_traits(style: str) -> dict:
    """Traits dict for a (possibly raw) style string."""
    return STYLE_TRAITS[canonical_style(style)]


# Short hooks appended to pairing explanations when a beer's style is a
# classic match for the dish (affinity >= 0.7).
STYLE_HOOKS: dict[str, str] = {
    "Stout":      "a stout's roasted depth is a textbook Cicerone call here",
    "Porter":     "a porter's chocolate-coffee notes are a textbook match",
    "IPA":        "a hop-forward IPA is the classic pick for this dish",
    "Pale Ale":   "a citrusy pale ale is a go-to pairing here",
    "Pilsner":    "a crisp pilsner is the classic palate-cleanser for this",
    "Lager":      "a clean lager is a safe, classic match",
    "Amber Ale":  "an amber's caramel malt is a natural bridge to this dish",
    "Wheat":      "a soft wheat beer is the traditional companion here",
    "Golden Ale": "an easy golden ale slots straight into this pairing",
}


# ── Food pairing model ────────────────────────────────────────────────────────
# Per food: intensity (1-5), then per mode:
#   targets : ideal beer attribute values (1-5); blended 65/35 with user palate
#   weights : importance of each attribute in the fit (default 1.0)
#   styles  : classic-style affinity, -1..+1 (Cicerone pairing canon)
#   avoid   : directional penalty rules
#             {"attr", "above", "penalty" (per unit over), "reason"}
#   why     : one-line pairing logic shown to the user

FOOD_PAIRING_BEER: dict[str, dict] = {

    "red_meat": {
        "intensity": 4.2,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"roast": 3.8, "body": 3.8, "bitterness": 3.2, "sweetness": 2.6, "carbonation": 2.8},
            "weights": {"roast": 1.6, "body": 1.4, "bitterness": 1.0},
            "styles": {"Stout": 1.0, "Porter": 1.0, "Black IPA": 0.7, "Amber Ale": 0.8,
                       "Brown Ale": 0.8, "Strong Ale": 0.6, "Ale": 0.3,
                       "Lager": -0.4, "Pilsner": -0.4, "Golden Ale": -0.2},
            "avoid": [],
            "why": "Roasted malt echoes the char and Maillard crust on the meat — a classic flavour bridge.",
        },
        "contrast": {
            "targets": {"bitterness": 4.3, "carbonation": 3.8, "body": 3.0, "sweetness": 1.8},
            "weights": {"bitterness": 1.7, "carbonation": 1.2},
            "styles": {"IPA": 1.0, "Pale Ale": 0.7, "Black IPA": 0.5, "Pilsner": 0.3,
                       "Golden Ale": -0.2, "Wheat": -0.4},
            "avoid": [],
            "why": "Assertive hop bitterness and lively carbonation scrub rich fat from the palate between bites.",
        },
    },

    "poultry": {
        "intensity": 2.5,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"body": 2.4, "bitterness": 2.2, "carbonation": 3.4, "aromatics": 2.4, "roast": 1.2},
            "weights": {"body": 1.3, "bitterness": 1.2, "roast": 1.2},
            "styles": {"Golden Ale": 1.0, "Lager": 0.8, "Pilsner": 0.7, "Ale": 0.6,
                       "Pale Ale": 0.3, "Stout": -0.8, "Porter": -0.7, "IPA": -0.4, "Black IPA": -0.8},
            "avoid": [],
            "why": "A light, balanced beer keeps pace with the bird without drowning its delicate flavour.",
        },
        "contrast": {
            "targets": {"aromatics": 3.4, "sweetness": 2.6, "bitterness": 1.8, "body": 2.8, "roast": 1.2},
            "weights": {"aromatics": 1.5, "bitterness": 1.1},
            "styles": {"Wheat": 1.0, "Ale": 0.8, "Hazy IPA": 0.5, "Golden Ale": 0.6,
                       "Stout": -0.7, "Black IPA": -0.7},
            "avoid": [],
            "why": "Fruity yeast esters lift and frame the mild meat — contrast through aroma, not bitterness.",
        },
    },

    "white_fish": {
        "intensity": 1.6,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"bitterness": 1.8, "body": 1.8, "carbonation": 4.2, "roast": 1.0, "aromatics": 2.0},
            "weights": {"carbonation": 1.6, "bitterness": 1.5, "roast": 1.4, "body": 1.3},
            "styles": {"Pilsner": 1.0, "Lager": 0.9, "Golden Ale": 0.6, "Sour": 0.5,
                       "IPA": -1.0, "Black IPA": -1.0, "Stout": -1.0, "Porter": -0.9,
                       "Hazy IPA": -0.6, "Amber Ale": -0.4},
            "avoid": [
                {"attr": "bitterness", "above": 3.2, "penalty": 0.12,
                 "reason": "heavy hop bitterness clashes with delicate fish oils"},
            ],
            "why": "Crisp, scrubbing carbonation and a feather-light frame mirror the ocean-fresh delicacy.",
        },
        "contrast": {
            "targets": {"body": 2.8, "aromatics": 3.0, "carbonation": 3.2, "bitterness": 1.8, "roast": 1.0},
            "weights": {"aromatics": 1.4, "bitterness": 1.4, "roast": 1.2},
            "styles": {"Wheat": 1.0, "Golden Ale": 0.7, "Ale": 0.6, "Hazy IPA": 0.3,
                       "Stout": -1.0, "Porter": -0.9, "IPA": -0.8, "Black IPA": -1.0},
            "avoid": [
                {"attr": "bitterness", "above": 3.2, "penalty": 0.12,
                 "reason": "heavy hop bitterness clashes with delicate fish oils"},
            ],
            "why": "A softer, aromatic beer frames the delicate fish with texture — never with bitterness.",
        },
    },

    "rich_fish": {
        "intensity": 3.0,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"bitterness": 2.8, "body": 3.0, "carbonation": 3.4, "roast": 1.5, "sweetness": 2.0},
            "weights": {"body": 1.3, "carbonation": 1.2},
            "styles": {"Amber Ale": 0.8, "Pale Ale": 0.8, "Golden Ale": 0.6, "Lager": 0.4,
                       "Pilsner": 0.4, "Stout": -0.4, "Black IPA": -0.4},
            "avoid": [],
            "why": "Medium maltiness meets the richer flesh, while carbonation keeps the oils in check.",
        },
        "contrast": {
            "targets": {"body": 3.8, "roast": 2.8, "bitterness": 2.2, "carbonation": 2.6, "sweetness": 2.6},
            "weights": {"body": 1.5, "roast": 1.2},
            "styles": {"Porter": 0.8, "Stout": 0.7, "Amber Ale": 0.6, "Strong Ale": 0.4,
                       "Pilsner": -0.3, "Lager": -0.3},
            "avoid": [],
            "why": "Weight meets weight — a fuller, gently roasty beer stands shoulder to shoulder with the rich fish.",
        },
    },

    "spicy_food": {
        "intensity": 3.8,
        "is_sweet_pairing": True,
        "congruent": {
            "targets": {"sweetness": 3.4, "carbonation": 3.8, "bitterness": 1.6, "body": 2.2,
                        "alcohol": 1.8, "roast": 1.2},
            "weights": {"sweetness": 1.5, "bitterness": 1.6, "alcohol": 1.4, "carbonation": 1.2},
            "styles": {"Wheat": 1.0, "Golden Ale": 0.8, "Lager": 0.7, "Sour": 0.6, "Ale": 0.5,
                       "IPA": -1.0, "Black IPA": -1.0, "Strong Ale": -0.8, "Pale Ale": -0.3},
            "avoid": [
                {"attr": "bitterness", "above": 3.0, "penalty": 0.15,
                 "reason": "hop bitterness amplifies capsaicin burn"},
                {"attr": "alcohol", "above": 2.8, "penalty": 0.12,
                 "reason": "alcohol intensifies chilli heat"},
            ],
            "why": "Soft malt sweetness and lively bubbles cool capsaicin heat — bitterness and booze would fan the flames.",
        },
        "contrast": {
            "targets": {"carbonation": 4.4, "bitterness": 2.4, "body": 1.8, "sweetness": 1.8,
                        "alcohol": 1.6, "roast": 1.0},
            "weights": {"carbonation": 1.6, "alcohol": 1.3, "bitterness": 1.1},
            "styles": {"Pilsner": 1.0, "Lager": 0.9, "Sour": 0.5, "Golden Ale": 0.4,
                       "IPA": -0.8, "Black IPA": -0.8, "Strong Ale": -0.8, "Stout": -0.6},
            "avoid": [
                {"attr": "alcohol", "above": 3.0, "penalty": 0.12,
                 "reason": "alcohol intensifies chilli heat"},
            ],
            "why": "A bone-dry, highly carbonated beer scrubs and resets the palate between fiery bites.",
        },
    },

    "tomato_sauce": {
        "intensity": 3.2,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"bitterness": 2.8, "carbonation": 3.6, "sweetness": 2.4, "body": 2.6, "roast": 1.6},
            "weights": {"carbonation": 1.3, "bitterness": 1.1},
            "styles": {"Pilsner": 0.8, "Lager": 0.7, "Pale Ale": 0.7, "Amber Ale": 0.6, "Ale": 0.4},
            "avoid": [],
            "why": "Carbonation stands in for acidity against the tomato tang, with enough hop snap to keep up.",
        },
        "contrast": {
            "targets": {"sweetness": 3.2, "body": 3.4, "bitterness": 1.8, "carbonation": 2.4, "roast": 2.2},
            "weights": {"sweetness": 1.4, "body": 1.2},
            "styles": {"Amber Ale": 0.9, "Ale": 0.6, "Golden Ale": 0.4, "Stout": 0.3, "Brown Ale": 0.7},
            "avoid": [],
            "why": "Rounded caramel malt softens the sauce's sharp edges instead of sparring with them.",
        },
    },

    "creamy_sauce": {
        "intensity": 3.4,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"body": 3.6, "sweetness": 2.8, "carbonation": 3.0, "bitterness": 2.4, "roast": 1.8},
            "weights": {"body": 1.4, "sweetness": 1.1},
            "styles": {"Amber Ale": 0.8, "Golden Ale": 0.6, "Ale": 0.6, "Strong Ale": 0.5, "Wheat": 0.4},
            "avoid": [],
            "why": "A full, malty body matches the dairy richness pound for pound.",
        },
        "contrast": {
            "targets": {"bitterness": 4.0, "carbonation": 4.0, "body": 2.4, "sweetness": 1.6},
            "weights": {"bitterness": 1.6, "carbonation": 1.4},
            "styles": {"IPA": 1.0, "Pale Ale": 0.8, "Pilsner": 0.7, "Black IPA": 0.4},
            "avoid": [],
            "why": "Sharp IBUs and scrubbing bubbles slice through the cream like a knife.",
        },
    },

    "greens": {
        "intensity": 1.8,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"bitterness": 2.4, "body": 1.8, "carbonation": 3.8, "aromatics": 2.6, "roast": 1.0},
            "weights": {"body": 1.3, "carbonation": 1.2, "roast": 1.2},
            "styles": {"Pilsner": 1.0, "Golden Ale": 0.8, "Lager": 0.7, "Sour": 0.5, "Hazy IPA": 0.3,
                       "Stout": -0.9, "Porter": -0.8, "Black IPA": -0.7},
            "avoid": [],
            "why": "Herbal, grassy hop notes bridge straight to the greens; a light frame keeps everything fresh.",
        },
        "contrast": {
            "targets": {"body": 2.8, "sweetness": 2.6, "roast": 2.2, "bitterness": 2.0, "carbonation": 2.6},
            "weights": {"roast": 1.2, "sweetness": 1.1},
            "styles": {"Amber Ale": 0.8, "Ale": 0.6, "Brown Ale": 0.6, "Stout": -0.4},
            "avoid": [],
            "why": "Toasty malt grounds the garden-fresh dish with gentle earthy weight.",
        },
    },

    "charcuterie": {
        "intensity": 3.4,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"body": 3.0, "bitterness": 2.8, "carbonation": 3.4, "sweetness": 2.4, "roast": 2.0},
            "weights": {"carbonation": 1.2},
            "styles": {"Amber Ale": 0.8, "Pale Ale": 0.7, "Golden Ale": 0.6, "Lager": 0.5,
                       "Ale": 0.5, "Pilsner": 0.5},
            "avoid": [],
            "why": "A balanced, malty all-rounder loves cured meat, while carbonation cuts the salt and fat.",
        },
        "contrast": {
            "targets": {"bitterness": 4.0, "carbonation": 4.0, "body": 2.6, "sweetness": 1.6},
            "weights": {"bitterness": 1.5, "carbonation": 1.3},
            "styles": {"IPA": 1.0, "Pale Ale": 0.8, "Pilsner": 0.6, "Black IPA": 0.4},
            "avoid": [],
            "why": "Aggressive hops and high fizz power through the board's salt, fat and cure.",
        },
    },

    "dessert": {
        "intensity": 4.0,
        "is_sweet_pairing": True,
        "congruent": {
            "targets": {"sweetness": 4.2, "roast": 3.6, "body": 3.8, "bitterness": 2.0, "carbonation": 2.2},
            "weights": {"sweetness": 1.6, "roast": 1.4, "body": 1.2},
            "styles": {"Stout": 1.0, "Porter": 1.0, "Strong Ale": 0.8, "Brown Ale": 0.6, "Amber Ale": 0.4,
                       "Lager": -0.8, "Pilsner": -0.9, "IPA": -0.6, "Golden Ale": -0.4},
            "avoid": [],
            "why": "Chocolate-coffee roast and malt sweetness mirror the dessert — the beer must never taste drier than the dish.",
        },
        "contrast": {
            "targets": {"carbonation": 4.2, "bitterness": 2.6, "sweetness": 1.8, "body": 2.2, "roast": 1.2},
            "weights": {"carbonation": 1.5, "sweetness": 1.2},
            "styles": {"Sour": 1.0, "Pilsner": 0.8, "Lager": 0.6, "Golden Ale": 0.5,
                       "Stout": -0.4, "Strong Ale": -0.4},
            "avoid": [],
            "why": "Dry, snappy fizz resets a sugar-coated palate between rich bites.",
        },
    },

    "smoked_bbq": {
        "intensity": 4.4,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"roast": 4.0, "body": 3.6, "sweetness": 2.8, "bitterness": 2.8, "carbonation": 2.8},
            "weights": {"roast": 1.7, "body": 1.3},
            "styles": {"Stout": 1.0, "Porter": 1.0, "Amber Ale": 0.8, "Black IPA": 0.7,
                       "Strong Ale": 0.6, "Brown Ale": 0.8, "Ale": 0.3,
                       "Pilsner": -0.5, "Golden Ale": -0.3, "Lager": -0.3},
            "avoid": [],
            "why": "Roasted malt locks onto smoke and char, while a kiss of malt sweetness mirrors the rub.",
        },
        "contrast": {
            "targets": {"bitterness": 4.2, "carbonation": 3.8, "body": 2.8, "sweetness": 1.8},
            "weights": {"bitterness": 1.6, "carbonation": 1.2},
            "styles": {"IPA": 1.0, "Pale Ale": 0.8, "Black IPA": 0.6, "Pilsner": 0.4},
            "avoid": [],
            "why": "Big IBUs and bright carbonation cut through the sweet-smoky fat and reset the palate.",
        },
    },

    "earthy_veg": {
        "intensity": 2.8,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"roast": 2.8, "body": 3.0, "sweetness": 2.8, "bitterness": 2.2, "carbonation": 2.6},
            "weights": {"roast": 1.4, "sweetness": 1.1},
            "styles": {"Amber Ale": 1.0, "Brown Ale": 0.9, "Ale": 0.6, "Stout": 0.5, "Porter": 0.5,
                       "Golden Ale": 0.4, "Pilsner": -0.3},
            "avoid": [],
            "why": "Toasty caramel malt echoes mushroom and roasted-root umami — earth meets earth.",
        },
        "contrast": {
            "targets": {"carbonation": 3.8, "aromatics": 3.0, "body": 2.2, "bitterness": 2.2, "roast": 1.2},
            "weights": {"carbonation": 1.3, "aromatics": 1.2},
            "styles": {"Wheat": 0.9, "Pilsner": 0.8, "Golden Ale": 0.7, "Hazy IPA": 0.4, "Sour": 0.5},
            "avoid": [],
            "why": "Bright fizz and fruity aromatics lift the earthiness like a squeeze of lemon.",
        },
    },

    # No food — pure palate match; no targets, no style bias, no penalties.
    "none": {
        "intensity": None,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {}, "weights": {}, "styles": {}, "avoid": [],
            "why": "Matched purely to your palate — no food in the picture, the beer gets to shine on its own.",
        },
        "contrast": {
            "targets": {}, "weights": {}, "styles": {}, "avoid": [],
            "why": "Matched purely to your palate — no food in the picture, the beer gets to shine on its own.",
        },
    },
}
