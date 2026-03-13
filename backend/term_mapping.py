"""
Maps internal technical wine attributes to user-facing UI labels.

Technical Term      -> UI Display Label
---------------------------------------------------------------------------
acidity             -> Crispness (Acidity)
body                -> Weight (Body)
tannin              -> Texture (Tannin)
aromatics           -> Flavor Intensity (Aromatics)
"""

TECHNICAL_TO_UI: dict[str, str] = {
    "acidity": "Crispness (Acidity)",
    "body": "Weight (Body)",
    "tannin": "Texture (Tannin)",
    "aromatics": "Flavor Intensity (Aromatics)",
}

UI_TO_TECHNICAL: dict[str, str] = {v: k for k, v in TECHNICAL_TO_UI.items()}
