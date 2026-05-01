"""
Wine region → country + Australian state lookup.

Used by the normalizer to classify scraped wines more accurately than
name-keyword inference alone. Wines with no recognisable region in their
name fall back to the keyword approach in normalizer.py and then default
to 'Australia' (a safe assumption for Liquorland's predominantly domestic
catalogue).

Designed to be replaced or extended when direct retailer API data becomes
available (e.g. Endeavour Group), at which point name inference can be
dropped entirely in favour of structured metadata.
"""

# Keys are lowercase. Sorted longest-first at module load so "barossa valley"
# matches before "barossa", "napa valley" before "napa", etc.
_REGIONS_RAW: dict[str, dict] = {

    # ── Australia — South Australia ──────────────────────────────────────────
    "barossa valley":       {"country": "Australia", "state": "SA"},
    "barossa":              {"country": "Australia", "state": "SA"},
    "mclaren vale":         {"country": "Australia", "state": "SA"},
    "clare valley":         {"country": "Australia", "state": "SA"},
    "eden valley":          {"country": "Australia", "state": "SA"},
    "coonawarra":           {"country": "Australia", "state": "SA"},
    "padthaway":            {"country": "Australia", "state": "SA"},
    "langhorne creek":      {"country": "Australia", "state": "SA"},
    "adelaide hills":       {"country": "Australia", "state": "SA"},
    "wrattonbully":         {"country": "Australia", "state": "SA"},
    "kangaroo island":      {"country": "Australia", "state": "SA"},
    "riverland":            {"country": "Australia", "state": "SA"},
    "mount benson":         {"country": "Australia", "state": "SA"},
    "currency creek":       {"country": "Australia", "state": "SA"},
    "southern fleurieu":    {"country": "Australia", "state": "SA"},
    "robe":                 {"country": "Australia", "state": "SA"},

    # ── Australia — Victoria ─────────────────────────────────────────────────
    "yarra valley":         {"country": "Australia", "state": "VIC"},
    "mornington peninsula": {"country": "Australia", "state": "VIC"},
    "heathcote":            {"country": "Australia", "state": "VIC"},
    "rutherglen":           {"country": "Australia", "state": "VIC"},
    "grampians":            {"country": "Australia", "state": "VIC"},
    "pyrenees":             {"country": "Australia", "state": "VIC"},
    "king valley":          {"country": "Australia", "state": "VIC"},
    "alpine valleys":       {"country": "Australia", "state": "VIC"},
    "beechworth":           {"country": "Australia", "state": "VIC"},
    "macedon ranges":       {"country": "Australia", "state": "VIC"},
    "sunbury":              {"country": "Australia", "state": "VIC"},
    "geelong":              {"country": "Australia", "state": "VIC"},
    "bendigo":              {"country": "Australia", "state": "VIC"},
    "goulburn valley":      {"country": "Australia", "state": "VIC"},
    "henty":                {"country": "Australia", "state": "VIC"},
    "glenrowan":            {"country": "Australia", "state": "VIC"},
    "nagambie lakes":       {"country": "Australia", "state": "VIC"},
    "strathbogie ranges":   {"country": "Australia", "state": "VIC"},

    # ── Australia — New South Wales ──────────────────────────────────────────
    "hunter valley":        {"country": "Australia", "state": "NSW"},
    "orange":               {"country": "Australia", "state": "NSW"},
    "mudgee":               {"country": "Australia", "state": "NSW"},
    "hilltops":             {"country": "Australia", "state": "NSW"},
    "tumbarumba":           {"country": "Australia", "state": "NSW"},
    "canberra district":    {"country": "Australia", "state": "NSW"},
    "cowra":                {"country": "Australia", "state": "NSW"},
    "riverina":             {"country": "Australia", "state": "NSW"},
    "shoalhaven coast":     {"country": "Australia", "state": "NSW"},
    "southern highlands":   {"country": "Australia", "state": "NSW"},

    # ── Australia — Western Australia ────────────────────────────────────────
    "margaret river":       {"country": "Australia", "state": "WA"},
    "great southern":       {"country": "Australia", "state": "WA"},
    "swan valley":          {"country": "Australia", "state": "WA"},
    "pemberton":            {"country": "Australia", "state": "WA"},
    "manjimup":             {"country": "Australia", "state": "WA"},
    "geographe":            {"country": "Australia", "state": "WA"},
    "frankland river":      {"country": "Australia", "state": "WA"},
    "frankland":            {"country": "Australia", "state": "WA"},
    "porongurup":           {"country": "Australia", "state": "WA"},
    "mount barker":         {"country": "Australia", "state": "WA"},

    # ── Australia — Tasmania ─────────────────────────────────────────────────
    "tamar valley":         {"country": "Australia", "state": "TAS"},
    "coal river valley":    {"country": "Australia", "state": "TAS"},
    "huon valley":          {"country": "Australia", "state": "TAS"},
    "derwent valley":       {"country": "Australia", "state": "TAS"},
    "east coast tasmania":  {"country": "Australia", "state": "TAS"},

    # ── Australia — Queensland ───────────────────────────────────────────────
    "granite belt":         {"country": "Australia", "state": "QLD"},
    "south burnett":        {"country": "Australia", "state": "QLD"},

    # ── New Zealand ──────────────────────────────────────────────────────────
    "marlborough":          {"country": "New Zealand"},
    "hawke's bay":          {"country": "New Zealand"},
    "hawkes bay":           {"country": "New Zealand"},
    "central otago":        {"country": "New Zealand"},
    "wairarapa":            {"country": "New Zealand"},
    "martinborough":        {"country": "New Zealand"},
    "gisborne":             {"country": "New Zealand"},
    "nelson":               {"country": "New Zealand"},
    "waiheke":              {"country": "New Zealand"},
    "canterbury":           {"country": "New Zealand"},
    "new zealand":          {"country": "New Zealand"},

    # ── France ───────────────────────────────────────────────────────────────
    "côtes du rhône":       {"country": "France"},
    "cotes du rhone":       {"country": "France"},
    "champagne":            {"country": "France"},
    "burgundy":             {"country": "France"},
    "bourgogne":            {"country": "France"},
    "bordeaux":             {"country": "France"},
    "provence":             {"country": "France"},
    "alsace":               {"country": "France"},
    "rhône valley":         {"country": "France"},
    "rhone valley":         {"country": "France"},
    "rhône":                {"country": "France"},
    "rhone":                {"country": "France"},
    "loire valley":         {"country": "France"},
    "loire":                {"country": "France"},
    "languedoc":            {"country": "France"},
    "roussillon":           {"country": "France"},
    "beaujolais":           {"country": "France"},
    "chablis":              {"country": "France"},
    "sancerre":             {"country": "France"},
    "pouilly":              {"country": "France"},

    # ── Italy ────────────────────────────────────────────────────────────────
    "tuscany":              {"country": "Italy"},
    "toscana":              {"country": "Italy"},
    "piedmont":             {"country": "Italy"},
    "piemonte":             {"country": "Italy"},
    "barolo":               {"country": "Italy"},
    "brunello":             {"country": "Italy"},
    "chianti":              {"country": "Italy"},
    "veneto":               {"country": "Italy"},
    "sicily":               {"country": "Italy"},
    "sicilian":             {"country": "Italy"},
    "puglia":               {"country": "Italy"},
    "campania":             {"country": "Italy"},
    "friuli":               {"country": "Italy"},
    "amarone":              {"country": "Italy"},
    "valpolicella":         {"country": "Italy"},
    "soave":                {"country": "Italy"},
    "gavi":                 {"country": "Italy"},
    "montepulciano":        {"country": "Italy"},
    "primitivo":            {"country": "Italy"},
    "nero d'avola":         {"country": "Italy"},

    # ── Spain ────────────────────────────────────────────────────────────────
    "ribera del duero":     {"country": "Spain"},
    "rías baixas":          {"country": "Spain"},
    "rias baixas":          {"country": "Spain"},
    "rioja":                {"country": "Spain"},
    "priorat":              {"country": "Spain"},
    "penedès":              {"country": "Spain"},
    "penedes":              {"country": "Spain"},
    "cava":                 {"country": "Spain"},
    "jerez":                {"country": "Spain"},

    # ── Portugal ─────────────────────────────────────────────────────────────
    "vinho verde":          {"country": "Portugal"},
    "douro":                {"country": "Portugal"},
    "alentejo":             {"country": "Portugal"},
    "dão":                  {"country": "Portugal"},
    "dao":                  {"country": "Portugal"},
    "bairrada":             {"country": "Portugal"},

    # ── Germany ──────────────────────────────────────────────────────────────
    "rheinhessen":          {"country": "Germany"},
    "rheingau":             {"country": "Germany"},
    "mosel":                {"country": "Germany"},
    "pfalz":                {"country": "Germany"},
    "nahe":                 {"country": "Germany"},
    "baden":                {"country": "Germany"},

    # ── USA ──────────────────────────────────────────────────────────────────
    "willamette valley":    {"country": "USA"},
    "napa valley":          {"country": "USA"},
    "columbia valley":      {"country": "USA"},
    "paso robles":          {"country": "USA"},
    "santa barbara":        {"country": "USA"},
    "sonoma":               {"country": "USA"},
    "napa":                 {"country": "USA"},
    "california":           {"country": "USA"},

    # ── Argentina ────────────────────────────────────────────────────────────
    "luján de cuyo":        {"country": "Argentina"},
    "lujan de cuyo":        {"country": "Argentina"},
    "mendoza":              {"country": "Argentina"},
    "patagonia":            {"country": "Argentina"},
    "salta":                {"country": "Argentina"},

    # ── Chile ────────────────────────────────────────────────────────────────
    "casablanca valley":    {"country": "Chile"},
    "colchagua valley":     {"country": "Chile"},
    "maipo valley":         {"country": "Chile"},
    "colchagua":            {"country": "Chile"},
    "aconcagua":            {"country": "Chile"},
    "maipo":                {"country": "Chile"},
    "leyda":                {"country": "Chile"},

    # ── South Africa ─────────────────────────────────────────────────────────
    "stellenbosch":         {"country": "South Africa"},
    "franschhoek":          {"country": "South Africa"},
    "walker bay":           {"country": "South Africa"},
    "swartland":            {"country": "South Africa"},
    "paarl":                {"country": "South Africa"},

    # ── Austria ──────────────────────────────────────────────────────────────
    "burgenland":           {"country": "Austria"},
    "kremstal":             {"country": "Austria"},
    "wachau":               {"country": "Austria"},
    "kamptal":              {"country": "Austria"},

    # ── Greece ───────────────────────────────────────────────────────────────
    "santorini":            {"country": "Greece"},
    "nemea":                {"country": "Greece"},
}

# Sort longest-first so multi-word phrases ("barossa valley") match before
# their shorter substrings ("barossa").
_SORTED: list[tuple[str, dict]] = sorted(
    _REGIONS_RAW.items(), key=lambda x: -len(x[0])
)


def lookup_region(name: str) -> dict | None:
    """
    Scan a product name for a known wine region.

    Returns {"country": str, "state": str | None} on match, None otherwise.
    Matching is case-insensitive; longer phrases take priority over shorter ones.
    """
    lower = name.lower()
    for region, meta in _SORTED:
        if region in lower:
            return meta
    return None
