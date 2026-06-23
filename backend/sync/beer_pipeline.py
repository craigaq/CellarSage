"""
Beer scraping pipeline — Boozeit (direct Shopify JSON) + Liquorland (Apify actor).

Parallel to the wine sync but self-contained: beer product titles, pack
formats, and attribute estimation differ enough from wine that sharing the
varietal normalizer would hurt both.

Flow per retailer:
  fetch → parse (clean name, pack, ABV) → infer style → match/insert into
  `beers` → upsert `beer_merchant_offers`.

Attribute estimation for NEW beers (retailers don't publish IBU/body):
  classify style from title/description, then inherit that style's typical
  attribute vector from beer_pairing.STYLE_TRAITS; ABV from the listing.

Run: python -m sync.beer_pipeline            (Boozeit only — free, no actor)
     python -m sync.beer_pipeline --liquorland  (also runs the Apify actor)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

_BOOZEIT_BASE = "https://www.boozeit.com.au"
_PAGE_SIZE = 250
_CRAWL_DELAY = 0.5

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-AU,en;q=0.9",
}

# ── Style inference ───────────────────────────────────────────────────────────
# Ordered: first match wins. Checked against title + product_type + body text.
# Beer-world traps handled: "Victoria Bitter" is a lager, "draught" means
# lager in AU retail, ginger beer / cider / seltzer are not beer at all.

_NOT_BEER_RE = re.compile(
    r"ginger\s+beer|cider|seltzer|hard\s+(lemonade|rated)|premix|rtd|"
    r"vodka|whisky|whiskey|gin\b|rum\b|tequila|brandy|liqueur|soda",
    re.IGNORECASE,
)

# Order matters — first match wins. Explicit, unambiguous styles are checked
# before brand-ish words. "lager" sits ABOVE amber/brown/golden so an explicit
# "...Lager" title (e.g. "Pure Blonde Ultra Low Carb Lager") isn't hijacked by
# the brand word "blonde" → Golden Ale.
_STYLE_RULES: list[tuple[str, str]] = [
    (r"hazy|neipa|new\s+england", "Hazy IPA"),
    (r"black\s+ipa|cascadian", "Black IPA"),
    (r"\bipa\b|india[n]?\s+pale", "IPA"),
    (r"\bxpa\b|extra\s+pale", "Pale Ale"),
    (r"pale\s+ale", "Pale Ale"),
    (r"pilsner|pilsener|\bpils\b", "Pilsner"),
    (r"stout", "Stout"),
    (r"porter", "Porter"),
    (r"wheat|hefe|weiss|weizen|witbier|white\s+ale", "Wheat"),
    (r"sour|gose|berliner", "Sour"),
    # Only an explicit "lager" word — NOT "draught"/"bitter"/"dry", which
    # misfire (Guinness Draught is a stout). Macro lagers that use those
    # words are curated in the seed, so inference needn't guess them.
    (r"\blager\b|pale\s+lager", "Lager"),
    (r"amber|red\s+ale|red\s+ipa", "Amber Ale"),
    (r"brown\s+ale|dark\s+ale|toohey'?s\s+old", "Brown Ale"),
    (r"golden\s+ale|summer\s+ale|blonde|k[oö]lsch", "Golden Ale"),
    (r"barley\s*wine|strong\s+ale|imperial|double\s+\w+\s*ale", "Strong Ale"),
    (r"sparkling\s+ale|session\s+ale|\bale\b", "Ale"),
]

_ABV_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*%")

# Tokens stripped from titles to get a clean beer name for matching/display.
_PACK_NOISE_RE = re.compile(
    r"\b(cans?|bottles?|stubbies|longneck|\d+\s*ml|\d+\s*x\s*\d+\s*ml|"
    r"\d+\s*(pack|block|case)|case\s+of\s+\d+|carton|slab|single)\b",
    re.IGNORECASE,
)


def _match_style(text: str) -> str | None:
    for pattern, style in _STYLE_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return style
    return None


def infer_style(title: str, extra: str = "") -> str | None:
    """Canonical style for a product, or None if it's not a beer.

    The TITLE is authoritative — a beer's name carries its true style
    ("...Lager", "...IPA"). Marketing body copy ('amber hue', 'pilsner-style')
    is only consulted as a fallback when the title has no style word, so it
    can't override an explicit title style.
    """
    if _NOT_BEER_RE.search(f"{title} {extra}"):
        return None
    return _match_style(title) or _match_style(extra)


# ── Location inference (origin tier) ──────────────────────────────────────────
# Brand-based, NOT keyword-based: "Japanese Style"/"Mexican Style" lagers are
# Australian-made, so only genuine overseas BRANDS are flagged International.
# Licensed-in-AU brands (Heineken Australia, Corona (AU)) still read by brand.
_INTERNATIONAL_BRANDS: tuple[str, ...] = (
    "asahi", "kirin", "sapporo", "orion", "heineken", "beck", "carlsberg",
    "henninger", "paulaner", "schofferhofer", "weihenstephaner", "stella artois",
    "benediktiner", "erdinger", "franziskaner",
    "hoegaarden", "duvel", "birra moretti", "peroni", "budvar", "praga",
    "budweiser", "corona", "sol cerveza", "san miguel", "estrella", "singha",
    "efes", "almaza", "kingfisher", "guinness", "coors", "miller genuine",
    "karlovacko", "jelen", "lav premium", "zajecarsko", "henninger",
)
def infer_location(name: str) -> str:
    """Origin marker from the beer's brand: International (overseas) | Domestic.

    'Local' vs 'Interstater' is decided at query time by matching brewery_state
    to the user's state (see infer_brewery_state + /beer-picks). This only flags
    overseas brands; everything else is Australian ('National')."""
    n = name.lower()
    if any(b in n for b in _INTERNATIONAL_BRANDS):
        return "International"
    return "National"


# Australian brewery → state, for geo-personalised "Local Hero" (beer analogue
# of wine's producer_state.json). Brand-fragment match, lowercased. Order
# matters where one fragment is a substring of another — more specific first.
# Unmapped Australian brands stay state=NULL → "The Interstater" (safe default;
# better to under-claim Local than wrongly claim it).
_BREWERY_STATE: tuple[tuple[str, str], ...] = (
    # SA
    ("coopers", "SA"), ("pirate life", "SA"), ("vale brewing", "SA"),
    ("vale crisp", "SA"), ("lobethal", "SA"), ("fox hat", "SA"),
    ("mismatch", "SA"), ("prancing pony", "SA"), ("big shed", "SA"),
    ("uraidla", "SA"), ("west end", "SA"),
    # VIC
    ("carlton", "VIC"), ("victoria bitter", "VIC"), ("melbourne bitter", "VIC"),
    ("crown lager", "VIC"), ("pure blonde", "VIC"), ("mountain goat", "VIC"),
    ("moon dog", "VIC"), ("holgate", "VIC"), ("hawkers", "VIC"),
    ("furphy", "VIC"), ("white rabbit", "VIC"), ("brick lane", "VIC"),
    ("bright brewery", "VIC"), ("west city", "VIC"),
    # NSW (note: 'hawkers' (VIC) is matched above before "hawke's")
    ("tooheys", "NSW"), ("resch", "NSW"), ("hahn", "NSW"),
    ("james squire", "NSW"), ("kosciuszko", "NSW"), ("young henrys", "NSW"),
    ("stone & wood", "NSW"), ("stone and wood", "NSW"), ("4 pines", "NSW"),
    ("mountain culture", "NSW"), ("philter", "NSW"), ("grifter", "NSW"),
    ("lord nelson", "NSW"), ("byron bay", "NSW"), ("hawke's", "NSW"),
    ("heaps normal", "NSW"),
    # QLD
    ("balter", "QLD"), ("great northern", "QLD"), ("xxxx", "QLD"),
    ("burleigh", "QLD"),
    # WA
    ("little creatures", "WA"), ("feral", "WA"), ("gage roads", "WA"),
    ("colonial", "WA"), ("matso", "WA"),
    # TAS
    ("cascade", "TAS"), ("boag", "TAS"), ("moo brew", "TAS"),
    # ACT
    ("bentspoke", "ACT"),
)


def infer_brewery_state(name: str) -> str | None:
    """Australian state of the brewery, or None if overseas/unknown."""
    n = name.lower()
    for fragment, state in _BREWERY_STATE:
        if fragment in n:
            return state
    return None


def extract_abv(text: str) -> float | None:
    m = _ABV_RE.search(text)
    if m:
        abv = float(m.group(1))
        if 0.5 <= abv <= 15.0:
            return abv
    return None


def clean_name(title: str) -> str:
    """Strip pack-format noise from a retail title."""
    name = _PACK_NOISE_RE.sub(" ", title)
    return re.sub(r"\s{2,}", " ", name).strip(" -–—")


def parse_pack_count(package_info: str | None, title: str = "") -> int:
    """Number of drinks in an offer's pack. Defaults to 1 (single) when unknown.

    Handles AU retail formats: 'Can', '6 Pack', 'PACK6', 'Case (24)', 'CTN24',
    '4 Pack', plus 'NN x MMml' multipacks embedded in titles.
    """
    text = f"{package_info or ''} {title}".lower()
    # CTNnn / PACKnn / "Case (24)" / "24 pack" / "24pk"
    m = re.search(r"(?:ctn|pack|case[^0-9]{0,4}|carton[^0-9]{0,4})\(?\s*(\d{1,2})", text)
    if m:
        return max(1, int(m.group(1)))
    m = re.search(r"\b(\d{1,2})\s*(?:x\b|pack|pk|pk\.|cans?|bottles?|stubbies)", text)
    if m:
        return max(1, int(m.group(1)))
    if re.search(r"\b(can|bottle|stubby|longneck|single)\b", text):
        return 1
    return 1


def _norm_tokens(name: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]", " ", name.lower()).split())


# ── Boozeit fetcher ───────────────────────────────────────────────────────────

def fetch_boozeit_beers() -> list[dict]:
    """Paginate Boozeit's beer collection; one offer per product (cheapest variant)."""
    products: list[dict] = []
    page = 1
    while True:
        url = f"{_BOOZEIT_BASE}/collections/beer/products.json?limit={_PAGE_SIZE}&page={page}"
        if page > 1:
            time.sleep(_CRAWL_DELAY)
        req = urllib.request.Request(url, headers=_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                items = json.loads(r.read().decode("utf-8")).get("products", [])
        except (urllib.error.HTTPError, Exception) as e:  # noqa: BLE001
            log.warning("boozeit beer: page %d failed: %s", page, e)
            break
        if not items:
            break
        products.extend(items)
        log.info("boozeit beer: page %d -> %d items (total %d)", page, len(items), len(products))
        if len(items) < _PAGE_SIZE:
            break
        page += 1

    offers: list[dict] = []
    for p in products:
        title = (p.get("title") or "").strip()
        if not title:
            continue
        extra = " ".join([p.get("product_type") or "", p.get("body_html") or ""])
        style = infer_style(title, extra)
        if style is None:
            continue
        blob = f"{title} {extra}"

        # Cheapest available variant = the entry-level pack for this product.
        variants = [v for v in (p.get("variants") or []) if v.get("price")]
        if not variants:
            continue
        try:
            best = min(variants, key=lambda v: float(v["price"]))
            price = float(best["price"])
        except (ValueError, TypeError):
            continue
        if price <= 0:
            continue

        handle = p.get("handle", "")
        offers.append({
            "raw_title": title,
            "name": clean_name(title),
            "style": style,
            "abv": extract_abv(blob),
            "price": price,
            "package_info": (best.get("title") or "").strip() or None,
            "url": f"{_BOOZEIT_BASE}/products/{handle}" if handle else None,
            "retailer": "boozeit",
        })

    log.info("boozeit beer: %d products -> %d beer offers", len(products), len(offers))
    return offers


# ── Liquorland fetcher (Apify actor, /beer category) ──────────────────────────

def fetch_liquorland_beers(pages: int = 4) -> list[dict]:
    """Fetch Liquorland's /beer category via the same actor the wine sync uses."""
    from .scraper import run_actor

    raw: list = []
    for page in range(1, pages + 1):
        items = run_actor(
            actor_id="dromb/liquorland-au-catalog-product-lookup-unofficial",
            actor_input={
                "operation": "category",
                "path": "/beer",
                "show": 50,
                "includeRaw": False,
                "page": page,
            },
            max_items=50,
        )
        raw.extend(items)
        log.info("liquorland beer: page %d -> %d items (total %d)", page, len(items), len(raw))
        if len(items) < 50:
            break

    offers: list[dict] = []
    for item in raw:
        title = (item.get("title") or item.get("name") or item.get("product_name") or "").strip()
        if not title:
            continue
        extra = str(item.get("description") or "")
        style = infer_style(title, extra)
        if style is None:
            continue
        blob = f"{title} {extra}"
        price = (item.get("current_price") or item.get("discount_price")
                 or item.get("price") or item.get("currentPrice"))
        try:
            price = float(price)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        offers.append({
            "raw_title": title,
            "name": clean_name(title),
            "style": style,
            "abv": extract_abv(blob),
            "price": price,
            "package_info": (item.get("size") or item.get("packSize") or None),
            "url": (item.get("source_url") or item.get("url")
                    or item.get("productUrl") or item.get("link")),
            "retailer": "liquorland",
        })

    log.info("liquorland beer: %d raw -> %d beer offers", len(raw), len(offers))
    return offers


# ── Matching + upsert ─────────────────────────────────────────────────────────

# Style-typical ABV used only when a listing doesn't state one. Alcohol is a
# scored axis in the v2 engine (spicy targets low, BBQ tolerates high), so a
# flat fallback would mis-rank styles like Strong Ale or Stout. Keyed to the
# canonical STYLE_TRAITS styles.
_STYLE_TYPICAL_ABV: dict[str, float] = {
    "Lager": 4.6, "Pilsner": 4.6, "Pale Ale": 4.9, "IPA": 6.0, "Hazy IPA": 5.6,
    "Black IPA": 6.2, "Golden Ale": 4.5, "Amber Ale": 5.0, "Brown Ale": 5.0,
    "Porter": 5.2, "Stout": 5.2, "Wheat": 5.0, "Sour": 4.2, "Strong Ale": 8.0,
    "Ale": 4.8,
}
_DEFAULT_ABV = 4.7  # last-resort fallback for an unmapped style


def _style_defaults(style: str, abv: float | None) -> dict:
    """Derive seedable attributes for a new beer from its style's typical profile."""
    from beer_pairing import canonical_style, style_traits

    typ = style_traits(style)["typical"]
    if abv is None:
        abv = _STYLE_TYPICAL_ABV.get(canonical_style(style), _DEFAULT_ABV)
    return {
        # bitterness 1-5 → IBU via the inverse of BeerProfile's IBU/20 mapping
        "ibu": round((typ["bitterness"] - 1.0) * 20.0),
        "body": round(typ["body"], 1),
        "malt_sweetness": max(1, min(5, round(typ["sweetness"]))),
        "hop_intensity": max(1, min(10, round(typ["aromatics"] * 2))),
        "abv": abv,
        "carbonation": max(1, min(5, round(typ["carbonation"]))),
    }


def upsert_beer_offers(offers: list[dict]) -> tuple[int, int, int]:
    """Match offers to the beers table (insert new beers as needed), upsert offers.

    Returns (beers_matched, beers_created, offers_upserted).
    """
    import psycopg2
    import psycopg2.extras
    from dotenv import load_dotenv

    load_dotenv()
    conn = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()

    cur.execute("SELECT id, name, beer_style FROM beers")
    catalog = [(r["id"], r["name"], _norm_tokens(r["name"])) for r in cur.fetchall()]

    matched = created = upserted = 0
    for o in offers:
        offer_tokens = _norm_tokens(o["name"])
        beer_id = None
        # Match to an existing beer only when its name is BOTH a subset of the
        # offer's tokens AND covers most of them (>=70%). The coverage guard
        # stops a short name absorbing a distinct product — e.g. "Balter XPA"
        # (2 tokens) must NOT swallow "Balter Hazy XPA" (3 tokens, 0.67).
        best_cov = 0.0
        for cid, _cname, ctokens in catalog:
            if len(ctokens) >= 2 and ctokens <= offer_tokens:
                cov = len(ctokens) / len(offer_tokens)
                if cov >= 0.7 and cov > best_cov:
                    beer_id, best_cov = cid, cov

        if beer_id is not None:
            matched += 1
        else:
            d = _style_defaults(o["style"], o["abv"])
            cur.execute(
                """INSERT INTO beers (name, ibu_bitterness, body, malt_sweetness,
                                      hop_intensity, abv_percentage, carbonation_level,
                                      beer_style, location_tag, brewery_state)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (o["name"], d["ibu"], d["body"], d["malt_sweetness"],
                 d["hop_intensity"], d["abv"], d["carbonation"], o["style"],
                 infer_location(o["name"]), infer_brewery_state(o["name"])),
            )
            beer_id = cur.fetchone()["id"]
            catalog.append((beer_id, o["name"], _norm_tokens(o["name"])))
            created += 1

        pack = parse_pack_count(o["package_info"], o["raw_title"])
        unit_price = round(o["price"] / pack, 2)
        cur.execute(
            """INSERT INTO beer_merchant_offers
                   (beer_id, retailer, price, url, package_info, pack_count, unit_price, scraped_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())
               ON CONFLICT (beer_id, retailer)
               DO UPDATE SET price = EXCLUDED.price, url = EXCLUDED.url,
                             package_info = EXCLUDED.package_info,
                             pack_count = EXCLUDED.pack_count,
                             unit_price = EXCLUDED.unit_price, scraped_at = NOW()""",
            (beer_id, o["retailer"], o["price"], o["url"], o["package_info"], pack, unit_price),
        )
        upserted += 1

    conn.commit()
    conn.close()
    return matched, created, upserted


def main() -> None:
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

    offers = fetch_boozeit_beers()
    if "--liquorland" in sys.argv:
        try:
            offers += fetch_liquorland_beers()
        except Exception as e:  # noqa: BLE001
            log.error("liquorland beer fetch failed (continuing with boozeit): %s", e)

    if not offers:
        log.error("No beer offers scraped — aborting upsert")
        return

    matched, created, upserted = upsert_beer_offers(offers)
    log.info("DONE: %d offers | matched %d existing beers, created %d new, upserted %d offers",
             len(offers), matched, created, upserted)


if __name__ == "__main__":
    main()
