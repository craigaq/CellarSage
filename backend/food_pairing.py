"""
Wine food pairing — sommelier-aligned model (v2).

Why v2? The v1 multiplier/boost system could only express "reward attribute"
or "ignore attribute". It could not express "this attribute is actively BAD
here", and — because preference weights doubled as importance weights — a
guest asking for "no tannin" carried 5× less influence than one asking for
"high acidity". (Proven failure: a crisp-and-silky request ranked Barbera
above Pinot Grigio.)

The v2 model encodes classical sommelier method (CMS/WSET canon):

  1. MATCH INTENSITY  — delicate dishes need delicate wines; bold needs bold.
     Each food carries an `intensity` (1-5); wines compute their own and are
     penalised for large mismatches. The sommelier's first rule.

  2. FIND HARMONIES   — encoded two ways:
       - `targets`: ideal attribute values (1-5) per food/mode. Scoring is a
         Gaussian fit against these, blended with the user's palate dials.
       - `varietals`: a classic-pairing affinity map (-1..+1) encoding the
         canon directly — Sangiovese+tomato, Pinot Noir+salmon, Chardonnay+
         cream, Gamay+charcuterie, Sauternes+dessert, Shiraz+BBQ.

  3. CONSIDER INTERACTIONS — directional chemistry the fit can't capture:
       - `avoid`: signed penalty rules — tannin reacts metallic with fish
         oils, tannin scrapes against capsaicin, alcohol fans chilli heat,
         umami turns heavy tannin bitter.

Newly scored axes (v1 ignored both):
  sweetness — derived from residual_sugar_gl (graduated, not just the binary
              style gate). Lets off-dry Riesling beat dry Riesling on spicy
              food *by degree*.
  alcohol   — ABV normalised 1-5. Spicy targets low; BBQ tolerates high.

All attribute values are on a 1-5 scale:
  acidity, body, tannin, aromatics — as before (pH-derived, expert ratings)
  sweetness — 1.0 bone dry → 5.0 lusciously sweet (RS-derived)
  alcohol   — ~8% ABV → 1.0, ~15.5%+ → 5.0

Modes remain `congruent` (echo the dish) and `contrast` (balance the dish).
`is_sweet_pairing` is preserved for Palate Paradox detection.

NOTE (spicy/contrast correction): v1's contrast mode "amplified the fire"
with bold high-alcohol wines. Canon says the opposite — alcohol and tannin
both amplify capsaicin. Contrast now means a cold, bone-dry, high-acid
cleanse; the heat-amplifying pick was bad advice and is gone.

Keys are backend food IDs (snake_case).
"""

FOOD_PAIRING: dict[str, dict] = {

    "red_meat": {
        "intensity": 4.2,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"tannin": 4.5, "body": 4.3, "acidity": 3.2, "aromatics": 3.6,
                        "sweetness": 1.0, "alcohol": 3.8},
            "weights": {"tannin": 1.6, "body": 1.4},
            "varietals": {"Cabernet Sauvignon": 1.0, "Syrah/Shiraz": 0.9, "Malbec": 0.9,
                          "Tempranillo": 0.7, "Nebbiolo": 0.7, "Red Blend": 0.7,
                          "Merlot": 0.6, "Mourvèdre": 0.6, "Carménère": 0.6,
                          "Cabernet Franc": 0.5, "Grenache": 0.4,
                          "Pinot Grigio": -0.6, "Sauvignon Blanc": -0.6, "Moscato": -1.0},
            "avoid": [],
            "why": "Structured tannin locks onto the meat's fat and protein — the fat tames the grip while the body matches the richness.",
        },
        "contrast": {
            "targets": {"acidity": 4.3, "tannin": 2.3, "body": 2.8, "aromatics": 3.2,
                        "sweetness": 1.0, "alcohol": 3.2},
            "weights": {"acidity": 1.6},
            "varietals": {"Pinot Noir": 1.0, "Barbera": 0.9, "Gamay": 0.8, "Sangiovese": 0.6,
                          "Cabernet Franc": 0.5},
            "avoid": [],
            "why": "Bright acidity slices through the fat instead of wrestling it — lighter frame, electric finish.",
        },
    },

    "poultry": {
        "intensity": 2.5,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"body": 2.8, "tannin": 1.8, "acidity": 3.4, "aromatics": 2.8,
                        "sweetness": 1.2, "alcohol": 2.8},
            "weights": {"tannin": 1.3, "body": 1.2},
            "varietals": {"Chardonnay": 0.9, "Pinot Noir": 0.8, "Chenin Blanc": 0.7,
                          "Semillon": 0.5, "Gamay": 0.5, "Vermentino": 0.4,
                          "Nebbiolo": -0.5, "Cabernet Sauvignon": -0.4},
            "avoid": [
                {"attr": "tannin", "above": 3.5, "penalty": 0.10,
                 "reason": "heavy tannin steamrolls the delicate bird"},
            ],
            "why": "A gentle, balanced wine with soft grip and clean acidity lets the bird lead.",
        },
        "contrast": {
            "targets": {"aromatics": 4.2, "body": 3.6, "tannin": 1.2, "acidity": 3.0,
                        "sweetness": 1.5, "alcohol": 3.2},
            "weights": {"aromatics": 1.5, "tannin": 1.4},
            "varietals": {"Viognier": 1.0, "Gewürztraminer": 0.7, "Fiano": 0.7,
                          "Marsanne": 0.6, "Torrontés": 0.6},
            "avoid": [
                {"attr": "tannin", "above": 3.5, "penalty": 0.10,
                 "reason": "heavy tannin steamrolls the delicate bird"},
            ],
            "why": "An intensely aromatic, full-textured white deliberately outshines the mild meat — contrast through perfume, not grip.",
        },
    },

    "white_fish": {
        "intensity": 1.6,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"acidity": 4.5, "tannin": 1.0, "body": 1.8, "aromatics": 2.6,
                        "sweetness": 1.0, "alcohol": 2.2},
            "weights": {"tannin": 1.7, "acidity": 1.5, "body": 1.3},
            "varietals": {"Albariño": 1.0, "Vermentino": 0.9, "Sauvignon Blanc": 0.8,
                          "Pinot Grigio": 0.8, "Champagne": 0.8, "Cava": 0.7,
                          "Fino Sherry": 0.7, "Grüner Veltliner": 0.6,
                          "Trebbiano Toscano": 0.5, "Airén": 0.4,
                          "Cabernet Sauvignon": -1.0, "Syrah/Shiraz": -1.0,
                          "Nebbiolo": -1.0, "Malbec": -0.9, "Tempranillo": -0.8},
            "avoid": [
                {"attr": "tannin", "above": 2.2, "penalty": 0.15,
                 "reason": "tannin reacts with delicate fish oils — metallic, tinny finish"},
            ],
            "why": "Saline, razor-crisp acidity mirrors the brine — and tannin stays at zero, where fish demands it.",
        },
        "contrast": {
            "targets": {"body": 3.0, "aromatics": 3.6, "tannin": 1.0, "acidity": 3.4,
                        "sweetness": 1.3, "alcohol": 2.8},
            "weights": {"tannin": 1.7, "aromatics": 1.3},
            "varietals": {"Viognier": 0.8, "Fiano": 0.8, "Marsanne": 0.8, "Chenin Blanc": 0.7,
                          "Gewürztraminer": 0.5,
                          "Cabernet Sauvignon": -1.0, "Syrah/Shiraz": -1.0, "Nebbiolo": -1.0},
            "avoid": [
                {"attr": "tannin", "above": 2.2, "penalty": 0.15,
                 "reason": "tannin reacts with delicate fish oils — metallic, tinny finish"},
            ],
            "why": "A textured, perfumed white frames the delicate fish — contrast through richness, never through tannin.",
        },
    },

    "rich_fish": {
        "intensity": 3.0,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"acidity": 3.8, "body": 2.8, "tannin": 1.6, "aromatics": 3.0,
                        "sweetness": 1.2, "alcohol": 2.8},
            "weights": {"acidity": 1.2, "tannin": 1.2},
            "varietals": {"Pinot Noir": 1.0, "Gamay": 0.8, "Chardonnay": 0.7,
                          "Champagne": 0.6, "Albariño": 0.5, "Vermentino": 0.4},
            "avoid": [
                {"attr": "tannin", "above": 3.2, "penalty": 0.12,
                 "reason": "salmon takes a whisper of grip, not a tannic assault"},
            ],
            "why": "Freshness balances the oily flesh — silky light-red or bright-white territory, the classic salmon move.",
        },
        "contrast": {
            "targets": {"body": 3.6, "tannin": 1.8, "acidity": 3.0, "aromatics": 3.4,
                        "sweetness": 1.3, "alcohol": 3.2},
            "weights": {"body": 1.4},
            "varietals": {"Chardonnay": 0.8, "Viognier": 0.7, "Marsanne": 0.7,
                          "Pinot Noir": 0.5},
            "avoid": [
                {"attr": "tannin", "above": 3.2, "penalty": 0.12,
                 "reason": "salmon takes a whisper of grip, not a tannic assault"},
            ],
            "why": "Weight meets weight — a rich, rounded wine stands shoulder to shoulder with the dense flesh.",
        },
    },

    "spicy_food": {
        "intensity": 3.8,
        "is_sweet_pairing": True,
        "congruent": {
            "targets": {"sweetness": 2.6, "acidity": 3.8, "aromatics": 4.0, "tannin": 1.2,
                        "body": 2.2, "alcohol": 1.8},
            "weights": {"sweetness": 1.5, "alcohol": 1.4, "tannin": 1.4},
            "varietals": {"Riesling": 1.0, "Gewürztraminer": 0.9, "Moscato": 0.6,
                          "Torrontés": 0.6, "Prosecco": 0.6, "Chenin Blanc": 0.6,
                          "Cabernet Sauvignon": -0.8, "Nebbiolo": -0.8, "Syrah/Shiraz": -0.6},
            "avoid": [
                {"attr": "tannin", "above": 2.5, "penalty": 0.15,
                 "reason": "tannin scrapes against capsaicin and turns bitter"},
                {"attr": "alcohol", "above": 3.2, "penalty": 0.12,
                 "reason": "alcohol fans the chilli flames"},
            ],
            "why": "Off-dry sweetness and perfumed fruit cool the burn — low alcohol keeps the flames down, the off-dry classic for heat.",
        },
        "contrast": {
            "targets": {"acidity": 4.4, "body": 1.9, "tannin": 1.0, "sweetness": 1.4,
                        "alcohol": 1.6, "aromatics": 2.8},
            "weights": {"acidity": 1.5, "alcohol": 1.3, "tannin": 1.3},
            "varietals": {"Sauvignon Blanc": 0.9, "Cava": 0.8, "Albariño": 0.8,
                          "Vermentino": 0.8, "Pinot Grigio": 0.7, "Champagne": 0.6,
                          "Cabernet Sauvignon": -0.8, "Nebbiolo": -0.8},
            "avoid": [
                {"attr": "tannin", "above": 2.5, "penalty": 0.15,
                 "reason": "tannin scrapes against capsaicin and turns bitter"},
                {"attr": "alcohol", "above": 3.2, "penalty": 0.12,
                 "reason": "alcohol fans the chilli flames"},
            ],
            "why": "An ice-cold, bone-dry, razor-crisp white scrubs and resets the palate between fiery bites.",
        },
    },

    "tomato_sauce": {
        "intensity": 3.2,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"acidity": 4.2, "tannin": 2.8, "body": 3.0, "aromatics": 3.2,
                        "sweetness": 1.2, "alcohol": 3.0},
            "weights": {"acidity": 1.6},
            "varietals": {"Sangiovese": 1.0, "Barbera": 0.9, "Nero d'Avola": 0.7,
                          "Tempranillo": 0.5, "Grenache": 0.4, "Trebbiano Toscano": 0.4},
            "avoid": [],
            "why": "Acid meets acid — a wine that can't match the tomato's tartness tastes flat beside it. A high-acid red and tomato are Tuscany on a plate.",
        },
        "contrast": {
            "targets": {"body": 3.4, "tannin": 2.2, "acidity": 3.2, "aromatics": 3.0,
                        "sweetness": 1.4, "alcohol": 3.2},
            "weights": {"acidity": 1.2, "body": 1.2},
            "varietals": {"Merlot": 0.8, "Grenache": 0.6, "Red Blend": 0.5},
            "avoid": [],
            "why": "Plush, rounded fruit softens the sauce's sharp edges — still with enough acid to stay alive on the plate.",
        },
    },

    "creamy_sauce": {
        "intensity": 3.4,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"body": 3.8, "acidity": 3.0, "tannin": 1.6, "aromatics": 3.2,
                        "sweetness": 1.3, "alcohol": 3.2},
            "weights": {"body": 1.4},
            "varietals": {"Chardonnay": 1.0, "Viognier": 0.8, "Marsanne": 0.8,
                          "Fiano": 0.6, "Semillon": 0.6},
            "avoid": [],
            "why": "Butter meets butter — a full, creamy-textured white matches the dairy weight for weight.",
        },
        "contrast": {
            "targets": {"acidity": 4.4, "body": 2.4, "tannin": 1.2, "aromatics": 3.0,
                        "sweetness": 1.2, "alcohol": 2.6},
            "weights": {"acidity": 1.6},
            "varietals": {"Sauvignon Blanc": 0.9, "Champagne": 0.8, "Riesling": 0.8,
                          "Grüner Veltliner": 0.7, "Cava": 0.7},
            "avoid": [],
            "why": "Sharp, high-wire acidity slices through the cream like a squeeze of lemon.",
        },
    },

    "greens": {
        "intensity": 1.8,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"acidity": 4.2, "body": 1.9, "tannin": 1.2, "aromatics": 3.2,
                        "sweetness": 1.1, "alcohol": 2.0},
            "weights": {"acidity": 1.3, "body": 1.2},
            "varietals": {"Sauvignon Blanc": 1.0, "Grüner Veltliner": 1.0, "Vermentino": 0.8,
                          "Albariño": 0.7, "Pinot Grigio": 0.6, "Sauvignonasse/Friulano": 0.6},
            "avoid": [
                {"attr": "tannin", "above": 3.5, "penalty": 0.08,
                 "reason": "grippy tannin tastes harsh against raw greens"},
            ],
            "why": "Grassy, green-edged crispness mirrors the garden — herbaceous whites are the vegetable wines.",
        },
        "contrast": {
            "targets": {"body": 2.6, "tannin": 2.0, "aromatics": 2.8, "acidity": 3.2,
                        "sweetness": 1.2, "alcohol": 2.6},
            "weights": {"tannin": 1.1},
            "varietals": {"Gamay": 0.8, "Pinot Noir": 0.7, "Sangiovese": 0.4},
            "avoid": [],
            "why": "A light, earthy red grounds the fresh greens with gentle savoury weight.",
        },
    },

    "charcuterie": {
        "intensity": 3.4,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"acidity": 3.6, "body": 3.0, "tannin": 2.6, "aromatics": 3.0,
                        "sweetness": 1.3, "alcohol": 3.0},
            "weights": {"acidity": 1.2},
            "varietals": {"Gamay": 1.0, "Barbera": 0.8, "Fino Sherry": 0.8,
                          "Tempranillo": 0.7, "Cava": 0.7, "Grenache": 0.6,
                          "Pinot Noir": 0.6, "Sangiovese": 0.5},
            "avoid": [],
            "why": "A juicy, medium-everything bistro wine — salt softens tannin, so cured meat flatters easy reds, born for the board.",
        },
        "contrast": {
            "targets": {"acidity": 4.3, "body": 2.4, "tannin": 1.4, "aromatics": 3.0,
                        "sweetness": 1.5, "alcohol": 2.6},
            "weights": {"acidity": 1.4},
            "varietals": {"Champagne": 0.9, "Riesling": 0.8, "Sauvignon Blanc": 0.7,
                          "Prosecco": 0.6, "Grüner Veltliner": 0.6},
            "avoid": [],
            "why": "Scrubbing acidity and a touch of fruit power through the salt, fat and cure.",
        },
    },

    "dessert": {
        "intensity": 4.0,
        "is_sweet_pairing": True,
        "congruent": {
            "targets": {"sweetness": 4.6, "body": 3.6, "acidity": 3.4, "aromatics": 4.0,
                        "tannin": 1.6, "alcohol": 3.4},
            "weights": {"sweetness": 1.7, "acidity": 1.2},
            "varietals": {"Botrytis Semillon": 1.0, "Late Harvest Riesling": 1.0,
                          "Tawny Port": 0.9, "Muscat Liqueur": 0.9, "Moscato": 0.7},
            "avoid": [],
            "why": "The wine must be at least as sweet as the dish — anything drier turns thin and bitter beside sugar. Acid keeps the lusciousness lifted.",
        },
        "contrast": {
            "targets": {"sweetness": 3.4, "acidity": 4.4, "body": 2.4, "aromatics": 3.4,
                        "tannin": 1.2, "alcohol": 2.4},
            "weights": {"sweetness": 1.3, "acidity": 1.4},
            "varietals": {"Moscato": 0.9, "Late Harvest Riesling": 0.8, "Champagne": 0.5},
            "avoid": [],
            "why": "Lighter, frothier sweetness with electric acidity — refreshment against the richness rather than an echo of it.",
        },
    },

    "smoked_bbq": {
        "intensity": 4.4,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"body": 4.2, "tannin": 3.8, "aromatics": 4.0, "acidity": 3.0,
                        "sweetness": 1.4, "alcohol": 4.0},
            "weights": {"body": 1.4, "aromatics": 1.2},
            "varietals": {"Syrah/Shiraz": 1.0, "Malbec": 0.9, "Sparkling Shiraz": 0.8,
                          "Mourvèdre": 0.7, "Tempranillo": 0.6, "Red Blend": 0.6,
                          "Cabernet Sauvignon": 0.6, "Grenache": 0.5,
                          "Pinot Grigio": -0.6, "Sauvignon Blanc": -0.5},
            "avoid": [],
            "why": "Big, smoky, peppery fruit locks onto char and sweet rub — a bold red and the barbecue is the great Australian handshake.",
        },
        "contrast": {
            "targets": {"acidity": 4.2, "tannin": 2.2, "body": 2.8, "aromatics": 3.2,
                        "sweetness": 1.8, "alcohol": 2.8},
            "weights": {"acidity": 1.5},
            "varietals": {"Barbera": 0.8, "Riesling": 0.6, "Gamay": 0.6,
                          "Sparkling Shiraz": 0.4},
            "avoid": [],
            "why": "Bright acid and juicy fruit cut through the smoke and sweet fat, resetting the palate between bites.",
        },
    },

    "earthy_veg": {
        "intensity": 2.8,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {"body": 3.0, "tannin": 2.4, "acidity": 3.4, "aromatics": 3.0,
                        "sweetness": 1.2, "alcohol": 3.0},
            "weights": {"tannin": 1.2},
            "varietals": {"Pinot Noir": 1.0, "Nebbiolo": 0.8, "Grenache": 0.6,
                          "Tempranillo": 0.6, "Gamay": 0.6, "Sangiovese": 0.5},
            "avoid": [
                {"attr": "tannin", "above": 4.2, "penalty": 0.08,
                 "reason": "umami makes very heavy tannin taste bitter"},
            ],
            "why": "Forest-floor earthiness echoes mushroom and roasted-root umami — earthy reds and mushrooms share the same soil.",
        },
        "contrast": {
            "targets": {"acidity": 4.0, "body": 2.2, "aromatics": 3.2, "tannin": 1.2,
                        "sweetness": 1.3, "alcohol": 2.4},
            "weights": {"acidity": 1.3},
            "varietals": {"Grüner Veltliner": 0.9, "Sauvignon Blanc": 0.7,
                          "Chenin Blanc": 0.7, "Pinot Grigio": 0.5},
            "avoid": [],
            "why": "Bright, peppery freshness lifts the earthiness like a squeeze of lemon over roast vegetables.",
        },
    },

    # No food — pure palate match; no targets, no varietal bias, no penalties.
    "none": {
        "intensity": None,
        "is_sweet_pairing": False,
        "congruent": {
            "targets": {}, "weights": {}, "varietals": {}, "avoid": [],
            "why": "Matched purely to your palate — no food in the picture, the wine gets to shine on its own.",
        },
        "contrast": {
            "targets": {}, "weights": {}, "varietals": {}, "avoid": [],
            "why": "Matched purely to your palate — no food in the picture, the wine gets to shine on its own.",
        },
    },
}
