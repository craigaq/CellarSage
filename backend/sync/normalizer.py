"""
Maps raw scraped JSON from each merchant into our internal WineRecord +
MerchantOffer schema. Add a new _normalize_<merchant> function for each
new retailer; the dispatch table at the bottom routes automatically.
"""

import json
import pathlib
import re
import logging
from typing import Optional

from .models import WineRecord, MerchantOffer

log = logging.getLogger(__name__)

# ── Country origin markers (checked longest-phrase-first per country) ─────────
# Maps distinctive region/place names to their country. Default is "Australia"
# since Liquorland is an Australian retailer and most unlabelled wines are domestic.
_COUNTRY_MARKERS: list[tuple[str, list[str]]] = [
    ("New Zealand", [
        "new zealand", "marlborough", "hawke's bay", "hawkes bay",
        "central otago", "wairarapa", "martinborough", "gisborne",
        "nelson", "waiheke", "northland", "waitaki",
    ]),
    ("France", [
        "champagne", "burgundy", "bordeaux", "provence", "alsace",
        "rhone", "rhône", "loire", "languedoc", "beaujolais",
        "chablis", "sancerre", "médoc", "medoc", "pomerol",
        "saint-emilion", "st emilion", "roussillon", "cremant",
        "crémant", "muscadet",
    ]),
    ("Italy", [
        "tuscany", "tuscan", "barolo", "brunello", "chianti",
        "amarone", "ripasso", "primitivo", "sicilian", "sicily", "gavi",
        "veneto", "piedmont", "piemonte", "friuli", "puglia",
        "abruzzo", "toscana", "nero d'avola", "nebbiolo doc",
        "soave", "valpolicella", "montepulciano doc",
        # prosecco omitted: widely used as a style name by Australian producers
    ]),
    ("Spain", [
        "rioja", "ribera del duero", "cava", "navarra",
        "penedes", "penedès", "priorat", "galicia", "rias baixas",
        "rueda", "la mancha", "castilla", "toro spain",
    ]),
    ("Portugal", ["douro", "alentejo", "vinho verde", "dao", "dão", "bairrada"]),
    ("Germany", ["mosel", "rheingau", "pfalz", "rheinhessen", "nahe", "ahr"]),
    ("USA", [
        "napa valley", "napa", "sonoma", "california",
        "willamette", "columbia valley", "paso robles",
        "central coast", "washington state", "oregon",
    ]),
    ("South Africa", [
        "stellenbosch", "franschhoek", "swartland",
        "walker bay", "elgin", "constantia", "paarl",
    ]),
    ("Austria", ["wachau", "kamptal", "burgenland", "kremstal"]),
    ("Argentina", [
        "mendoza", "lujan de cuyo", "luján de cuyo",
        "patagonia argentina", "salta argentina",
    ]),
    ("Chile", [
        "maipo", "colchagua", "casablanca valley", "aconcagua",
        "rapel", "maule", "leyda", "san antonio chile",
    ]),
    ("Greece", ["assyrtiko", "santorini", "nemea", "xinomavro"]),
    ("Hungary", ["tokaj", "tokay"]),
]

# Brand-name → country for well-known imported brands that carry no
# geographic marker in their product names and would otherwise default
# to "Australia". Checked after region lookup, before the Australia fallback.
_BRAND_COUNTRY: list[tuple[str, str]] = [
    # New Zealand
    ("oyster bay",       "New Zealand"),
    ("villa maria",      "New Zealand"),
    ("kim crawford",     "New Zealand"),
    ("selaks",           "New Zealand"),
    ("saint clair",      "New Zealand"),
    ("babich",           "New Zealand"),
    ("cloudy bay",       "New Zealand"),
    ("spy valley",       "New Zealand"),
    ("stoneleigh",       "New Zealand"),
    ("catalina sounds",  "New Zealand"),
    ("counting sheep",   "New Zealand"),
    ("giesen",           "New Zealand"),
    ("kamana",           "New Zealand"),
    ("lana's bike",      "New Zealand"),
    ("split rock",       "New Zealand"),
    ("matua",            "New Zealand"),
    ("nanny goat",       "New Zealand"),
    ("rapaura springs",  "New Zealand"),
    ("rochecombe",       "New Zealand"),
    ("rock paper scissors", "New Zealand"),
    ("secret stone",     "New Zealand"),
    ("sheep shape",      "New Zealand"),
    ("squealing pig",    "New Zealand"),
    ("ta ku",            "New Zealand"),
    ("upside down",      "New Zealand"),
    ("invivo",           "New Zealand"),
    ("hunter's",         "New Zealand"),
    ("hunters wine",     "New Zealand"),
    ("seifried",         "New Zealand"),
    ("lake road",        "New Zealand"),
    ("clos henri",       "New Zealand"),
    ("framingham",       "New Zealand"),
    ("te mata",          "New Zealand"),
    ("craggy range",     "New Zealand"),
    ("dog point",        "New Zealand"),
    ("main divide",      "New Zealand"),
    ("mud house",        "New Zealand"),
    ("villa maria",      "New Zealand"),
    ("wither hills",     "New Zealand"),
    ("yealands",         "New Zealand"),
    ("pernod ricard nz", "New Zealand"),
    ("tiki",             "New Zealand"),
    ("tohu",             "New Zealand"),
    ("tora bay",         "New Zealand"),
    ("mahi",             "New Zealand"),
    ("seresin",          "New Zealand"),
    ("staete landt",     "New Zealand"),
    ("gravitas",         "New Zealand"),
    ("greywacke",        "New Zealand"),
    ("ata rangi",        "New Zealand"),
    ("dry river",        "New Zealand"),
    ("bay of stones",    "New Zealand"),
    ("taku",             "New Zealand"),
    ("rahiti",           "New Zealand"),
    # France
    ("veuve clicquot",   "France"),
    ("champteloup",      "France"),
    ("b francois",       "France"),
    ("tussock jumper",   "France"),
    ("fat bastard",      "France"),
    ("mouton cadet",     "France"),
    ("louis jadot",      "France"),
    ("joseph drouhin",   "France"),
    ("albert bichot",    "France"),
    ("georges duboeuf",  "France"),
    ("nicolas feuillatte","France"),
    ("laurent perrier",  "France"),
    ("bollinger",        "France"),
    ("pol roger",        "France"),
    ("piper-heidsieck",  "France"),
    ("piper heidsieck",  "France"),
    ("charles heidsieck","France"),
    ("taittinger",       "France"),
    ("ruinart",          "France"),
    ("krug",             "France"),
    ("dom perignon",     "France"),
    ("moet",             "France"),
    ("moët",             "France"),
    ("perrier-jouet",    "France"),
    ("perrier jouet",    "France"),
    ("g.h. mumm",        "France"),
    ("g h mumm",         "France"),
    ("ayala",            "France"),
    ("gosset",           "France"),
    ("billecart",        "France"),
    ("charles lafitte",  "France"),
    ("mionetto",         "France"),
    ("georges duboeuf",  "France"),
    ("pierre sparr",     "France"),
    ("hugel",            "France"),
    ("wolfberger",       "France"),
    ("trimbach",         "France"),
    ("pierre d'amour",   "France"),
    ("roche lacour",     "France"),
    ("barton & guestier","France"),
    ("b&g",              "France"),
    ("calvet",           "France"),
    ("sieur d'arques",   "France"),
    ("prestige du capitole", "France"),
    ("francoise chauvenet", "France"),
    # Italy
    ("antinori",         "Italy"),
    ("ruffino",          "Italy"),
    ("santa margherita", "Italy"),
    ("planeta",          "Italy"),
    ("banfi",            "Italy"),
    ("bolla",            "Italy"),
    ("frescobaldi",      "Italy"),
    ("masi",             "Italy"),
    ("pasqua",           "Italy"),
    ("zonin",            "Italy"),
    ("gaja",             "Italy"),
    ("sassicaia",        "Italy"),
    ("ornellaia",        "Italy"),
    ("tignanello",       "Italy"),
    ("biondi santi",     "Italy"),
    ("mastroberardino",  "Italy"),
    ("feudi di san gregorio", "Italy"),
    ("umani ronchi",     "Italy"),
    ("villa antinori",   "Italy"),
    ("sensi",            "Italy"),
    ("botter",           "Italy"),
    ("la marca",         "Italy"),
    ("bottega",          "Italy"),
    ("cossaro monferrato","Italy"),
    ("masi renzo",       "Italy"),
    # Spain
    ("torres",           "Spain"),   # note: torres also makes Chilean/US wine, but AU retail overwhelmingly Spain
    ("campo viejo",      "Spain"),
    ("codorniu",         "Spain"),
    ("freixenet",        "Spain"),
    ("vega sicilia",     "Spain"),
    ("alvaro palacios",  "Spain"),
    ("protos",           "Spain"),
    ("cune",             "Spain"),
    ("cvne",             "Spain"),
    ("beronia",          "Spain"),
    ("marques de murrieta", "Spain"),
    ("marques de riscal", "Spain"),
    ("bodegas muga",     "Spain"),
    ("muga rioja",       "Spain"),
    ("la rioja alta",    "Spain"),
    ("faustino",         "Spain"),
    ("el coto",          "Spain"),
    ("vina real",        "Spain"),
    ("protocolo",        "Spain"),
    ("camino real",      "Spain"),
    ("running with bulls","Spain"),
    ("altos de rioja",   "Spain"),
    ("altos r ",         "Spain"),
    ("familia martinez bujanda","Spain"),
    ("bodegas de sarria","Spain"),
    ("marques de tezona","Spain"),
    ("campos de viento", "Spain"),
    ("la poda",          "Spain"),
    ("rey del mundo",    "Spain"),
    ("cune crianza",     "Spain"),
    ("cune reserva",     "Spain"),
    # USA
    ("wente",            "USA"),
    ("beringer",         "USA"),
    ("robert mondavi",   "USA"),
    ("barefoot",         "USA"),
    ("bota box",         "USA"),
    ("kendall jackson",  "USA"),
    ("kendall-jackson",  "USA"),
    ("stag's leap",      "USA"),
    ("staggs leap",      "USA"),
    ("chateau montelena","USA"),
    ("jordan winery",    "USA"),
    ("coppola",          "USA"),
    ("meiomi",           "USA"),
    ("the prisoner",     "USA"),
    ("liberty school",   "USA"),
    ("columbia crest",   "USA"),
    ("chateau ste michelle","USA"),
    ("j lohr",           "USA"),
    ("pine ridge",       "USA"),
    # Argentina
    ("alamos",           "Argentina"),
    ("catena",           "Argentina"),
    ("achaval ferrer",   "Argentina"),
    ("clos de los 7",    "Argentina"),
    ("dona paula",       "Argentina"),
    ("doña paula",       "Argentina"),
    ("zuccardi",         "Argentina"),
    ("rutini",           "Argentina"),
    ("fabre montmayou",  "Argentina"),
    ("norton",           "Argentina"),
    ("malbec reserve mendoza", "Argentina"),
    ("finca beltran",    "Argentina"),
    ("finca beltrán",    "Argentina"),
    ("parcela selecta",  "Argentina"),
    ("mach 2t",          "Argentina"),
    ("opi malbec",       "Argentina"),
    ("q malbec",         "Argentina"),
    ("HJ fabre",         "Argentina"),
    # Chile
    ("concha y toro",    "Chile"),
    ("santa rita",       "Chile"),
    ("montes",           "Chile"),
    ("casa lapostolle",  "Chile"),
    ("carmen",           "Chile"),
    ("errazuriz",        "Chile"),
    ("errázuriz",        "Chile"),
    ("almaviva",         "Chile"),
    ("undurraga",        "Chile"),
    ("antakari",         "Chile"),
    ("cono sur",         "Chile"),
    ("casillero del diablo", "Chile"),
    ("reserva de familia", "Chile"),
    ("marques de casa concha","Chile"),
    ("terra noble",      "Chile"),
    ("vina mar",         "Chile"),
    # South Africa
    ("meerlust",         "South Africa"),
    ("kanonkop",         "South Africa"),
    ("hamilton russell", "South Africa"),
    ("boekenhoutskloof", "South Africa"),
    ("mullineux",        "South Africa"),
    ("ken forrester",    "South Africa"),
    ("indaba",           "South Africa"),
    ("spier",            "South Africa"),
    ("simonsig",         "South Africa"),
    ("fairview",         "South Africa"),
    ("neil ellis",       "South Africa"),
    ("libertas",         "South Africa"),
    # Germany
    ("dr loosen",        "Germany"),
    ("egon muller",      "Germany"),
    ("moselland",        "Germany"),
    ("selbach",          "Germany"),
    ("gunderloch",       "Germany"),
    ("weiss riesling",   "Germany"),
    # Portugal
    ("andresen",         "Portugal"),
    ("casal mendes",     "Portugal"),
    ("mateus",           "Portugal"),
    ("graham's",         "Portugal"),
    ("grahams port",     "Portugal"),
    ("taylor fladgate",  "Portugal"),
    ("quinta do crasto", "Portugal"),
    ("esporao",          "Portugal"),
    # Explicit Australian overrides — brands that sound foreign but are AU
    ("19 crimes",        "Australia"),   # made under licence in AU
    ("yellow tail",      "Australia"),
    ("jacob's creek",    "Australia"),
    ("wolf blass",       "Australia"),
    ("penfolds",         "Australia"),
    ("lindemans",        "Australia"),
    ("hardy's",          "Australia"),
    ("hardys",           "Australia"),
]

# Bundle product name patterns — reject cases, dozens, add-ons, etc.
_BUNDLE_NAME_RE = re.compile(
    r'\b(dozen|add[- ]?on)\b',
    re.IGNORECASE,
)

# Compound varietal overrides: when the API gives a simple varietal (e.g. "Shiraz")
# but the product name clearly indicates a compound style (e.g. "Sparkling Shiraz"),
# use the compound form so the DB keyword matching works correctly.
_COMPOUND_OVERRIDES: list[tuple[re.Pattern, str]] = [
    # Color-modifier compounds: strip the base varietal, keep only the color
    (re.compile(r'\w+\s+(?:rosé|rose)\b', re.IGNORECASE), 'Rose'),  # e.g., "Sangiovese Rose" → "Rose"

    # Sparkling blends: Chardonnay + Pinot Noir is classic Champagne (both orderings)
    (re.compile(r'chardonnay[\s/]+pinot\s+noir', re.IGNORECASE), 'Champagne'),
    (re.compile(r'pinot\s+noir[\s/]+chardonnay', re.IGNORECASE), 'Champagne'),

    (re.compile(r'sparkling\s+shiraz', re.IGNORECASE), 'Sparkling Shiraz'),
    (re.compile(r'sparkling\s+red\b',  re.IGNORECASE), 'Sparkling Shiraz'),
    (re.compile(r'late\s+harvest\s+riesling', re.IGNORECASE), 'Late Harvest Riesling'),
    (re.compile(r'\bbotrytis\s+semillon', re.IGNORECASE), 'Botrytis Semillon'),
    (re.compile(r'rutherglen\s+muscat',  re.IGNORECASE), 'Muscat Liqueur'),
    (re.compile(r'muscat\s+liqueur',     re.IGNORECASE), 'Muscat Liqueur'),
    (re.compile(r'tawny\s+port',         re.IGNORECASE), 'Tawny Port'),
    (re.compile(r'vintage\s+port',       re.IGNORECASE), 'Vintage Port'),
    (re.compile(r'fino\s+sherry',        re.IGNORECASE), 'Fino Sherry'),
    (re.compile(r'shiraz\s+viognier',                          re.IGNORECASE), 'Red Blend'),
    (re.compile(r'syrah\s+viognier',                           re.IGNORECASE), 'Red Blend'),
    # GSM and Rhône-style blends — any order of the three
    (re.compile(r'grenache[\s/]+shiraz[\s/]+mourvèdre',        re.IGNORECASE), 'Red Blend'),
    (re.compile(r'grenache[\s/]+shiraz[\s/]+mourvedre',        re.IGNORECASE), 'Red Blend'),
    (re.compile(r'shiraz[\s/\w]*grenache[\s/\w]*mourv',        re.IGNORECASE), 'Red Blend'),
    (re.compile(r'grenache[\s/\w]*mourv',                      re.IGNORECASE), 'Red Blend'),
    (re.compile(r'mourv[èe]dre[\s/\w]*(shiraz|grenache)',      re.IGNORECASE), 'Red Blend'),
    (re.compile(r'(shiraz|grenache)[\s/\w]*mourv[èe]dre',      re.IGNORECASE), 'Red Blend'),
    (re.compile(r'\bgsm\b',                                    re.IGNORECASE), 'Red Blend'),
    # Cabernet-led blends
    (re.compile(r'cabernet[\s/]+merlot',                       re.IGNORECASE), 'Red Blend'),
    (re.compile(r'cabernet[\s/]+shiraz',                       re.IGNORECASE), 'Red Blend'),
    (re.compile(r'shiraz[\s/]+cabernet',                       re.IGNORECASE), 'Red Blend'),
    (re.compile(r'cabernet[\s/]+merlot[\s/]+shiraz',           re.IGNORECASE), 'Red Blend'),
    (re.compile(r'cabernet[\s/]+franc[\s/]+merlot',            re.IGNORECASE), 'Red Blend'),
    # Malbec-led blends
    (re.compile(r'malbec[\s/\w]*shiraz',                       re.IGNORECASE), 'Red Blend'),
    (re.compile(r'malbec[\s/\w]*syrah',                        re.IGNORECASE), 'Red Blend'),
    (re.compile(r'malbec[\s/\w]*durif',                        re.IGNORECASE), 'Red Blend'),
    (re.compile(r'malbec[\s/\w]*cabernet',                     re.IGNORECASE), 'Red Blend'),
    (re.compile(r'malbec[\s/\w]*merlot',                       re.IGNORECASE), 'Red Blend'),
    (re.compile(r'syrah[\s/]+malbec',                          re.IGNORECASE), 'Red Blend'),
    (re.compile(r'shiraz[\s/]+malbec',                         re.IGNORECASE), 'Red Blend'),
    # Durif blends (Durif/Petite Sirah mixed with anything = Red Blend)
    (re.compile(r'shiraz[\s/\w]*durif',                        re.IGNORECASE), 'Red Blend'),
    (re.compile(r'durif[\s/\w]*shiraz',                        re.IGNORECASE), 'Red Blend'),
    (re.compile(r'durif[\s/\w]*cabernet',                      re.IGNORECASE), 'Red Blend'),
    # Explicitly labelled blends
    (re.compile(r'\bwhite\s+blend\b',                          re.IGNORECASE), 'White Blend'),
    (re.compile(r'\bbrut\b',                                   re.IGNORECASE), 'Champagne'),
    (re.compile(r'\bpetillant\b|\bpétillant\b',                re.IGNORECASE), 'Champagne'),
    (re.compile(r'semillon[\s/]+sauvignon',                    re.IGNORECASE), 'White Blend'),
    (re.compile(r'\bred\s+blend\b',                            re.IGNORECASE), 'Red Blend'),
    (re.compile(r'\bred\s+wine\s+blend\b',                     re.IGNORECASE), 'Red Blend'),
    (re.compile(r'semillon[\s/]+sauvignon\s+blanc',            re.IGNORECASE), 'White Blend'),
    (re.compile(r'sauvignon\s+blanc[\s/]+semillon',            re.IGNORECASE), 'White Blend'),
    (re.compile(r'chardonnay[\s/]+semillon',                   re.IGNORECASE), 'White Blend'),
    (re.compile(r'marsanne[\s/]+roussanne',                    re.IGNORECASE), 'White Blend'),
    (re.compile(r'\bwhite\s+blend\b',                          re.IGNORECASE), 'White Blend'),
]


def _refine_compound_varietal(varietal: str, name: str) -> str:
    """Override a simple varietal with its compound form when the product name demands it,
    then normalise to the canonical catalog label."""
    for pattern, compound in _COMPOUND_OVERRIDES:
        if pattern.search(name):
            return compound
    return _normalise_varietal(varietal)


# Unaccented → accented canonical spellings
_VARIETAL_CANONICAL: dict[str, str] = {
    "gruner veltliner": "Grüner Veltliner",
    "gewurztraminer": "Gewürztraminer",
    "carmenere": "Carménère",
    "mourvedre": "Mourvèdre",
    "airen": "Airén",
    "albarino": "Albariño",
    "torrontes": "Torrontés",
}

# API-supplied varietal strings that need remapping to our catalog labels.
# Applied after compound-override checks so fine-grained patterns win first.
_VARIETAL_SYNONYMS: dict[str, str] = {
    # Retailers store as "Shiraz" or "Syrah" — catalog label is "Syrah/Shiraz"
    "shiraz":            "Syrah/Shiraz",
    "syrah":             "Syrah/Shiraz",
    # Tawny without "Port" suffix
    "tawny":             "Tawny Port",
    # Rutherglen Muscat sold under several names
    "topaque":           "Muscat Liqueur",
    "tokay":             "Muscat Liqueur",
    "liqueur muscat":    "Muscat Liqueur",
    "rutherglen muscat": "Muscat Liqueur",
}


def _normalise_varietal(varietal: str) -> str:
    """Map a raw API varietal string to the canonical catalog label."""
    key = varietal.strip().lower()
    if key in _VARIETAL_SYNONYMS:
        return _VARIETAL_SYNONYMS[key]
    if key in _VARIETAL_CANONICAL:
        return _VARIETAL_CANONICAL[key]
    return varietal


# ── Australian producer → state mapping (loaded from producer_state.json) ────
# Longest entries sort first so "jacob's creek" matches before "jacob".
# Add new producers to the JSON file — no code change needed.
_PRODUCER_STATE: list[tuple[str, str]] = sorted(
    [tuple(pair) for pair in json.loads(
        (pathlib.Path(__file__).parent / "producer_state.json").read_text(encoding="utf-8")
    )],
    key=lambda x: -len(x[0]),
)

# Field names that indicate a member/loyalty-only price in scraped data.
_MEMBER_PRICE_KEYS = frozenset({
    "member_price", "loyalty_price", "rewards_price",
    "club_price", "everyday_price", "everyday_rewards_price",
})


def _infer_state_from_producer(name: str) -> str | None:
    """Match the wine name against known Australian producer brands."""
    lower = name.lower()
    for producer, state in _PRODUCER_STATE:
        if lower.startswith(producer) or f" {producer} " in lower:
            return state
    return None


def _infer_country_keywords(name: str) -> str:
    """Keyword fallback for country inference when no region matches."""
    lower = name.lower()
    for country, markers in _COUNTRY_MARKERS:
        if any(m in lower for m in markers):
            return country
    for brand, country in _BRAND_COUNTRY:
        if brand in lower:
            return country
    return "Australia"


def _infer_origin(name: str) -> tuple[str, str | None]:
    """
    Return (country, state) for a wine product name.

    Resolution order:
      1. Region lookup table (place names, most accurate)
      2. Producer-brand lookup (covers brands without region in name)
      3. Country keyword matching
      4. Default to Australia with no state
    """
    from region_lookup import lookup_region
    match = lookup_region(name)
    if match:
        country = match["country"]
        state   = match.get("state") or (
            _infer_state_from_producer(name) if country == "Australia" else None
        )
        return country, state

    country = _infer_country_keywords(name)
    state   = _infer_state_from_producer(name) if country == "Australia" else None
    return country, state


def _infer_varietal(name: str) -> Optional[str]:
    """Extract the best-matching canonical varietal from a product name."""
    for pattern, compound in _COMPOUND_OVERRIDES:
        if pattern.search(name):
            return compound
    lower = name.lower()
    for kw in _CATALOG_KEYWORDS:
        if kw in lower:
            raw = _VARIETAL_CANONICAL.get(kw, kw.title())
            return _normalise_varietal(raw)
    return None


# ── Known catalog varietal keywords (lowercase) ───────────────────────────────
# Items whose name/varietal don't match any of these are rejected so only
# wines in our known catalog land in the database.
# Sorted longest-first so "cabernet sauvignon" matches before "cabernet".
_CATALOG_KEYWORDS: list[str] = sorted([
    # ── Still reds & whites ──────────────────────────────────────────────────
    "cabernet sauvignon", "cabernet franc", "sauvignon blanc",
    "pinot noir", "pinot grigio", "pinot gris",
    "grüner veltliner", "gruner veltliner",
    "gewürztraminer", "gewurztraminer",
    "nero d'avola", "chenin blanc", "trebbiano",
    "tempranillo", "sangiovese", "carménère", "carmenere",
    "mourvèdre", "mourvedre", "vermentino",
    "chardonnay", "grenache", "viognier", "riesling",
    "marsanne", "semillon", "malbec", "merlot",
    "shiraz", "syrah", "gamay", "fiano", "barbera",
    "nebbiolo", "zinfandel", "moscato", "muscat",
    "airén", "airen", "albariño", "albarino",
    "torrontés", "torrontes", "friulano",
    "white blend", "semillon sauvignon blanc", "sauvignon blanc semillon",
    "cabernet",   # catch-all — must stay after more specific entries
    # ── Sparkling ────────────────────────────────────────────────────────────
    "sparkling shiraz", "champagne", "prosecco", "cava",
    # ── Rosé ─────────────────────────────────────────────────────────────────
    "rosé", "rose wine", "rose",
    # ── Dessert ──────────────────────────────────────────────────────────────
    "botrytis semillon", "late harvest riesling",
    "botrytis", "late harvest", "sauternes", "trockenbeerenauslese",
    # ── Fortified ────────────────────────────────────────────────────────────
    "muscat liqueur", "rutherglen muscat", "tawny port", "vintage port", "fino sherry",
    "topaque", "tokay",    # alternative names for Muscat Liqueur
    "amontillado", "oloroso", "manzanilla",  # sherry styles
    "tawny", "sherry", "port",
], key=lambda s: -len(s))


def _matches_catalog(varietal: Optional[str], name: str) -> bool:
    """Return True if this wine maps to a known catalog varietal."""
    haystack = (varietal or "").lower() + " " + name.lower()
    return any(kw in haystack for kw in _CATALOG_KEYWORDS)


# ── Helpers ──────────────────────────────────────────────────────────────────

# Non-750ml size patterns — anything matching this is rejected.
# Standard 750ml bottles often omit the size entirely, so we reject only
# explicit non-standard sizes rather than requiring "750ml" to be present.
_NON_STD_SIZE_RE = re.compile(
    r'(?<![0-9])(375\s?m[lL]|187\s?m[lL]|500\s?m[lL]|250\s?m[lL]|200\s?m[lL]|330\s?m[lL]'
    r'|1[.·]5\s?[lL]|1500\s?m[lL]'
    r'|1\s?[lL](?!\s?[0-9])|1000\s?m[lL]|[2-9]\s?[lL]|[2-9]000\s?m[lL]'
    r'|\bcan\b|\bcans\b|\bpicolo\b|\bpiccolino\b)',
    re.IGNORECASE,
)


def _is_standard_bottle(name: str, item: dict) -> bool:
    """Return False if the product is clearly not a standard 750ml bottle."""
    size_field = str(item.get("size") or item.get("volume") or item.get("pack_size") or "")
    haystack = name + " " + size_field
    return not _NON_STD_SIZE_RE.search(haystack)


def _extract_vintage(text: str) -> Optional[int]:
    """Pull a 4-digit year (1980–2030) out of a product name."""
    if not text:
        return None
    match = re.search(r'\b(19[89]\d|20[012]\d)\b', text)
    return int(match.group()) if match else None


def _coerce_price(raw) -> Optional[float]:
    """Accept int, float, or price strings like '$24.99' / '24,99'."""
    if raw is None:
        return None
    try:
        return float(str(raw).replace(',', '.').replace('$', '').strip())
    except (ValueError, TypeError):
        return None


def _first(*keys, src: dict):
    """Return the value of the first matching key found in src."""
    for k in keys:
        if k in src and src[k] not in (None, '', []):
            return src[k]
    return None


# ── Per-merchant normalizers ──────────────────────────────────────────────────

def _normalize_liquorland(item: dict, retailer: str) -> Optional[tuple[WineRecord, MerchantOffer]]:
    name = _first('title', 'name', 'product_name', src=item)
    if not name:
        return None

    price_raw = _first('price_now', 'currentPrice', 'price', 'salePrice', src=item)
    price = _coerce_price(price_raw)
    if price is None or price <= 0:
        return None

    vintage  = _extract_vintage(name)
    region   = _first('region', 'wine_region', 'area', src=item)
    varietal = _first('varietal', 'variety', 'grape', 'type', src=item)
    url      = _first('source_url', 'url', 'productUrl', 'link', src=item)

    # Rating: prefer top-level field; fall back to attributes.review_stats
    _attrs        = item.get('attributes') or {}
    _review_stats = _attrs.get('review_stats') or {}
    rating_raw    = item.get('rating') or _review_stats.get('average')
    rating        = _coerce_price(rating_raw)
    review_count  = int(item.get('review_count') or _review_stats.get('total') or 0)

    # Member price detection: explicit flag fields take priority; fallback is
    # checking whether price_now < a separately listed standard price, which
    # indicates the scraped price is the member/loyalty rate.
    is_member_price = any(k in item for k in _MEMBER_PRICE_KEYS)
    if not is_member_price and item.get('price_now'):
        _std = _coerce_price(item.get('price') or item.get('was_price') or item.get('rrp'))
        _now = _coerce_price(item['price_now'])
        if _std and _now and _now < _std - 0.01:
            is_member_price = True

    if not _matches_catalog(varietal, name):
        log.debug("liquorland item skipped — not in known catalog: %r", name)
        return None

    if not _is_standard_bottle(name, item):
        log.debug("liquorland item skipped — non-standard bottle size: %r", name)
        return None

    if _BUNDLE_NAME_RE.search(name):
        log.debug("liquorland item skipped — bundle product: %r", name)
        return None

    if varietal is not None:
        varietal = _refine_compound_varietal(varietal, name)
    else:
        varietal = _infer_varietal(name)

    country, state = _infer_origin(name)
    clean_name     = re.sub(r'\s*\b(19[89]\d|20[012]\d)\b\s*', ' ', name).strip()

    wine  = WineRecord(name=clean_name, vintage=vintage, region=region,
                       varietal=varietal, country=country, state=state)
    offer = MerchantOffer(wine_name=clean_name, vintage=vintage,
                          retailer=retailer, price=price, url=url,
                          rating=rating, review_count=review_count,
                          is_member_price=is_member_price)
    return wine, offer


def _normalize_cellarbrations(item: dict, retailer: str) -> Optional[tuple[WineRecord, MerchantOffer]]:
    name = _first("name", src=item)
    if not name:
        return None

    price = _coerce_price(_first("priceNumeric", "wholePrice", "price", src=item))
    if price is None or price <= 0:
        return None

    if not _is_standard_bottle(name, item):
        log.debug("cellarbrations item skipped — non-standard bottle size: %r", name)
        return None

    # Varietal from the API's category data
    def_cats = item.get("defaultCategory") or []
    varietal_raw = def_cats[0].get("category") if def_cats else None
    varietal = _first("varietal", src=item) or varietal_raw
    if varietal and varietal.lower() in ("grocery", "alcohol", "wine"):
        varietal = None

    if not _matches_catalog(varietal, name):
        log.debug("cellarbrations item skipped — not in known catalog: %r", name)
        return None

    if _BUNDLE_NAME_RE.search(name):
        log.debug("cellarbrations item skipped — bundle product: %r", name)
        return None

    vintage    = _extract_vintage(name)
    clean_name = re.sub(r'\s*\b(19[89]\d|20[012]\d)\b\s*', ' ', name).strip()
    url        = item.get("url")
    country, state = _infer_origin(clean_name)

    if varietal is None:
        varietal = _infer_varietal(clean_name)

    wine  = WineRecord(name=clean_name, vintage=vintage, varietal=varietal,
                       country=country, state=state)
    offer = MerchantOffer(wine_name=clean_name, vintage=vintage,
                          retailer=retailer, price=price, url=url)
    return wine, offer


def _normalize_laithwaites(item: dict, retailer: str) -> Optional[tuple[WineRecord, MerchantOffer]]:
    name = (item.get("name") or "").strip()
    if not name:
        return None

    price = _coerce_price(item.get("price"))
    if price is None or price <= 0:
        return None

    if not _is_standard_bottle(name, item):
        log.debug("laithwaites item skipped — non-standard size: %r", name)
        return None

    if not _matches_catalog(None, name):
        log.debug("laithwaites item skipped — not in catalog: %r", name)
        return None

    if _BUNDLE_NAME_RE.search(name):
        log.debug("laithwaites item skipped — bundle product: %r", name)
        return None

    vintage    = _extract_vintage(name)
    clean_name = re.sub(r'\s*\b(19[89]\d|20[012]\d)\b\s*', ' ', name).strip()
    varietal   = _infer_varietal(clean_name)
    country, state = _infer_origin(clean_name)
    url          = item.get("url", "")
    rating       = item.get("rating")
    review_count = int(item.get("review_count") or 0)

    wine  = WineRecord(name=clean_name, vintage=vintage, varietal=varietal,
                       country=country, state=state)
    offer = MerchantOffer(wine_name=clean_name, vintage=vintage,
                          retailer=retailer, price=price, url=url,
                          rating=rating, review_count=review_count)
    return wine, offer


def _normalize_boozeit(item: dict, retailer: str) -> Optional[tuple[WineRecord, MerchantOffer]]:
    name = (item.get("name") or "").strip()
    if not name:
        return None

    price = _coerce_price(item.get("price"))
    if price is None or price <= 0:
        return None

    if not _is_standard_bottle(name, item):
        log.debug("boozeit item skipped — non-standard size: %r", name)
        return None

    varietal = item.get("varietal") or None

    if not _matches_catalog(varietal, name):
        log.debug("boozeit item skipped — not in catalog: %r", name)
        return None

    if _BUNDLE_NAME_RE.search(name):
        log.debug("boozeit item skipped — bundle product: %r", name)
        return None

    vintage    = _extract_vintage(name)
    clean_name = re.sub(r'\s*\b(19[89]\d|20[012]\d)\b\s*', ' ', name).strip()

    if varietal is not None:
        varietal = _refine_compound_varietal(varietal, name)
        # Shopify product_type may be generic ("Red Wine", "White Wine") —
        # fall through to keyword inference when no specific varietal is found.
        if varietal.lower() in ("red wine", "white wine", "wine", "spirits", "beer"):
            varietal = _infer_varietal(clean_name)
    else:
        varietal = _infer_varietal(clean_name)

    country, state = _infer_origin(clean_name)
    url = item.get("url") or ""

    wine  = WineRecord(name=clean_name, vintage=vintage, varietal=varietal,
                       country=country, state=state)
    offer = MerchantOffer(wine_name=clean_name, vintage=vintage,
                          retailer=retailer, price=price, url=url)
    return wine, offer


def _normalize_danmurphys(item: dict, retailer: str) -> Optional[tuple[WineRecord, MerchantOffer]]:
    name = _first('name', 'title', 'productName', src=item)
    if not name:
        return None

    price = _coerce_price(_first('price', 'currentPrice', 'priceValue', src=item))
    if price is None or price <= 0:
        return None

    vintage  = _extract_vintage(name)
    clean_name = re.sub(r'\s*\b(19[89]\d|20[012]\d)\b\s*', ' ', name).strip()
    region   = _first('region', 'wine_region', src=item)
    varietal = _first('varietal', 'variety', 'type', src=item)
    url      = _first('url', 'link', src=item)

    if not _matches_catalog(varietal, name):
        log.debug("danmurphys item skipped — not in known catalog: %r", name)
        return None

    if not _is_standard_bottle(name, item):
        log.debug("danmurphys item skipped — non-standard bottle size: %r", name)
        return None

    wine  = WineRecord(name=clean_name, vintage=vintage, region=region, varietal=varietal)
    offer = MerchantOffer(wine_name=clean_name, vintage=vintage,
                          retailer=retailer, price=price, url=url)
    return wine, offer


# ── Dispatch ──────────────────────────────────────────────────────────────────

_NORMALIZERS = {
    "liquorland":                   _normalize_liquorland,
    "liquorland_premium":           _normalize_liquorland,
    "liquorland_fortified":         _normalize_liquorland,
    "liquorland_dessert":           _normalize_liquorland,
    "liquorland_search_merlot":          _normalize_liquorland,
    "liquorland_search_merlot_premium":  _normalize_liquorland,
    "liquorland_search_pinot":           _normalize_liquorland,
    "liquorland_search_grenache":        _normalize_liquorland,
    "liquorland_search_riesling":        _normalize_liquorland,
    "liquorland_search_tempranillo":     _normalize_liquorland,
    "liquorland_search_prosecco":        _normalize_liquorland,
    "liquorland_search_gewurztraminer":  _normalize_liquorland,
    "liquorland_search_moscato":         _normalize_liquorland,
    "liquorland_search_semillon":        _normalize_liquorland,
    "liquorland_search_pinot_grigio":    _normalize_liquorland,
    "liquorland_search_pinot_gris":      _normalize_liquorland,
    "liquorland_search_chardonnay":      _normalize_liquorland,
    "liquorland_search_shiraz":          _normalize_liquorland,
    "liquorland_search_cabernet":        _normalize_liquorland,
    "liquorland_search_rose":            _normalize_liquorland,
    "liquorland_search_sauvignon_blanc": _normalize_liquorland,
    "cellarbrations":          _normalize_cellarbrations,
    "cellarbrations_sunbury":  _normalize_cellarbrations,  # same WYNSHOP format, single store
    "portersliquor":           _normalize_cellarbrations,  # same WYNSHOP format
    "bottleo":                 _normalize_cellarbrations,  # same WYNSHOP format
    "laithwaites":          _normalize_laithwaites,
    "boozeit":              _normalize_boozeit,
    "danmurphys":           _normalize_danmurphys,
}


# Maps composite merchant keys → the canonical retailer name stored in the DB.
# Keeps DB retailer values consistent regardless of how many scrape configs
# a single retailer has (e.g. liquorland + liquorland_fortified → "liquorland").
_MERCHANT_TO_RETAILER: dict[str, str] = {
    "liquorland_premium":           "liquorland",
    "liquorland_fortified":         "liquorland",
    "liquorland_dessert":           "liquorland",
    "liquorland_search_merlot":          "liquorland",
    "liquorland_search_merlot_premium":  "liquorland",
    "liquorland_search_pinot":           "liquorland",
    "liquorland_search_grenache":        "liquorland",
    "liquorland_search_riesling":        "liquorland",
    "liquorland_search_tempranillo":     "liquorland",
    "liquorland_search_prosecco":        "liquorland",
    "liquorland_search_gewurztraminer":  "liquorland",
    "liquorland_search_moscato":         "liquorland",
    "liquorland_search_semillon":        "liquorland",
    "liquorland_search_pinot_grigio":    "liquorland",
    "liquorland_search_pinot_gris":      "liquorland",
    "liquorland_search_chardonnay":      "liquorland",
    "liquorland_search_shiraz":          "liquorland",
    "liquorland_search_cabernet":        "liquorland",
    "liquorland_search_rose":            "liquorland",
    "liquorland_search_sauvignon_blanc": "liquorland",
}


def normalize(items: list[dict], merchant: str) -> list[tuple[WineRecord, MerchantOffer]]:
    """
    Normalize a list of raw scraped items for a given merchant.
    Skips and logs any item that can't be mapped cleanly.
    """
    fn = _NORMALIZERS.get(merchant)
    if not fn:
        raise ValueError(f"No normalizer registered for merchant: {merchant!r}")
    retailer = _MERCHANT_TO_RETAILER.get(merchant, merchant)

    results = []
    for item in items:
        try:
            pair = fn(item, retailer)
            if pair:
                results.append(pair)
        except Exception as exc:
            log.warning("Normalizer skipped item for %s: %s — %r", merchant, exc, item)

    log.info("Normalised %d/%d items for %s", len(results), len(items), merchant)
    return results
