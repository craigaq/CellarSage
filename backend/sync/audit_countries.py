"""
Country classification audit for the wines table.

Run from the backend directory:
    python -m sync.audit_countries [--fix]

Without --fix: reports mis-classifications and suspects, no DB writes.
With    --fix: applies all known brand→country corrections then reports
               remaining suspects for manual review.
"""

import argparse
import json
import os
import pathlib
import sys

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).parent.parent / ".env")

import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Brand → country table (expand this list whenever new brands are spotted)
# ---------------------------------------------------------------------------
BRAND_COUNTRY: list[tuple[str, str]] = [
    # New Zealand
    ("oyster bay",      "New Zealand"),
    ("villa maria",     "New Zealand"),
    ("kim crawford",    "New Zealand"),
    ("selaks",          "New Zealand"),
    ("saint clair",     "New Zealand"),
    ("babich",          "New Zealand"),
    ("cloudy bay",      "New Zealand"),
    ("spy valley",      "New Zealand"),
    ("stoneleigh",      "New Zealand"),
    ("brancott",        "New Zealand"),
    ("montana",         "New Zealand"),
    ("mud house",       "New Zealand"),
    ("tohu",            "New Zealand"),
    ("nautilus",        "New Zealand"),
    ("craggy range",    "New Zealand"),
    ("dog point",       "New Zealand"),
    ("man o' war",      "New Zealand"),
    ("matawhero",       "New Zealand"),
    ("catalina sounds", "New Zealand"),
    ("counting sheep",  "New Zealand"),
    ("giesen",          "New Zealand"),
    ("kamana",          "New Zealand"),
    ("lana's bike",     "New Zealand"),
    ("matua",           "New Zealand"),
    ("nanny goat",      "New Zealand"),
    ("rapaura springs", "New Zealand"),
    ("rochecombe",      "New Zealand"),
    ("rock paper scissors", "New Zealand"),
    ("secret stone",    "New Zealand"),
    ("sheep shape",     "New Zealand"),
    ("squealing pig",   "New Zealand"),
    ("ta ku",           "New Zealand"),
    ("upside down",     "New Zealand"),
    # France
    ("veuve clicquot",  "France"),
    ("champteloup",     "France"),
    ("b francois",      "France"),
    ("tussock jumper",  "France"),
    ("fat bastard",     "France"),
    ("mouton cadet",    "France"),
    ("baron de rothschild", "France"),
    ("fortant",         "France"),
    ("gerard bertrand", "France"),
    ("paul mas",        "France"),
    ("louis jadot",     "France"),
    ("joseph drouhin",  "France"),
    ("georges duboeuf", "France"),
    # Italy
    ("santa margherita", "Italy"),
    ("antinori",        "Italy"),
    ("frescobaldi",     "Italy"),
    ("ruffino",         "Italy"),
    ("bolla",           "Italy"),
    # Spain
    ("torres",          "Spain"),
    ("campo viejo",     "Spain"),
    ("faustino",        "Spain"),
    # USA
    ("wente",           "USA"),
    ("beringer",        "USA"),
    ("robert mondavi",  "USA"),
    ("kendall jackson", "USA"),
    ("kendall-jackson", "USA"),
    ("barefoot",        "USA"),
    ("bota box",        "USA"),
    ("clos du bois",    "USA"),
    ("sonoma cutrer",   "USA"),
    ("la crema",        "USA"),
    ("stags' leap",     "USA"),
    ("sterling",        "USA"),
    # Argentina
    ("alamos",          "Argentina"),
    ("zuccardi",        "Argentina"),
    ("catena",          "Argentina"),
    ("achaval ferrer",  "Argentina"),
    ("luigi bosca",     "Argentina"),
    ("trapiche",        "Argentina"),
    ("norton",          "Argentina"),
    # Chile
    ("concha y toro",   "Chile"),
    ("casillero del diablo", "Chile"),
    ("santa rita",      "Chile"),
    ("santa carolina",  "Chile"),
    ("montes",          "Chile"),
    ("errazuriz",       "Chile"),
    ("cono sur",        "Chile"),
    # South Africa
    ("meerlust",        "South Africa"),
    ("kanonkop",        "South Africa"),
    ("boschendal",      "South Africa"),
    ("ken forrester",   "South Africa"),
    ("neil ellis",      "South Africa"),
    # Germany / Austria
    ("dr loosen",       "Germany"),
    ("egon muller",     "Germany"),
    ("schloss vollrads", "Germany"),
    ("hirsch",          "Austria"),
    ("gobelsburg",      "Austria"),
    # Portugal
    ("quinta do crasto", "Portugal"),
    ("ramos pinto",     "Portugal"),
    ("niepoort",        "Portugal"),
]

# Australian region keywords — if ANY of these appear in the name, it's
# almost certainly Australian even without a matching producer entry.
AU_REGION_KEYWORDS: list[str] = [
    "barossa", "mclaren vale", "coonawarra", "clare valley", "eden valley",
    "adelaide hills", "langhorne creek", "riverland", "padthaway",
    "yarra valley", "mornington peninsula", "heathcote", "rutherglen",
    "hunter valley", "mudgee", "orange nsw", "cowra", "hilltops",
    "margaret river", "great southern", "pemberton", "frankland",
    "swan valley", "geographe",
    "tamar valley", "coal river", "huon valley",
    "canberra district",
    "south australia", "victoria", "new south wales", "western australia",
    "tasmania", "queensland",
    "south east australia", "multi-regional",
]


def _load_au_producers() -> list[str]:
    p = pathlib.Path(__file__).parent / "producer_state.json"
    return [pair[0].lower() for pair in json.loads(p.read_text())]


def _is_known_au(name: str, au_producers: list[str]) -> bool:
    lower = name.lower()
    if any(r in lower for r in AU_REGION_KEYWORDS):
        return True
    return any(
        lower.startswith(prod) or f" {prod} " in lower
        for prod in au_producers
    )


def run(fix: bool = False):
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set"); sys.exit(1)

    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    cur  = conn.cursor()

    # ------------------------------------------------------------------
    # Step 1: apply brand corrections
    # ------------------------------------------------------------------
    fixed_total = 0
    if fix:
        print("=== Applying brand->country corrections ===")
        for brand, country in BRAND_COUNTRY:
            if country == "Australia":
                continue  # nothing to fix
            cur.execute(
                """
                UPDATE wines
                SET country = %s, state = NULL
                WHERE country = 'Australia'
                  AND LOWER(name) LIKE %s
                """,
                (country, f"%{brand}%"),
            )
            if cur.rowcount:
                print(f"  [{cur.rowcount:2d}] {brand!r} -> {country}")
                fixed_total += cur.rowcount
        conn.commit()
        print(f"\nTotal corrected: {fixed_total} wines\n")
    else:
        print("(Dry run - pass --fix to apply corrections)\n")
        print("=== Brand corrections that WOULD be applied ===")
        for brand, country in BRAND_COUNTRY:
            if country == "Australia":
                continue
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM wines
                WHERE country = 'Australia' AND LOWER(name) LIKE %s
                """,
                (f"%{brand}%",),
            )
            n = cur.fetchone()["n"]
            if n:
                print(f"  [{n:2d}] {brand!r} -> {country}")
        print()

    # ------------------------------------------------------------------
    # Step 2: flag remaining suspects
    # ------------------------------------------------------------------
    cur.execute(
        """
        SELECT id, name, country, state, varietal
        FROM wines
        WHERE country = 'Australia' AND state IS NULL
        ORDER BY name
        """
    )
    au_no_state = cur.fetchall()
    au_producers = _load_au_producers()

    suspects = [
        r for r in au_no_state
        if not _is_known_au(r["name"], au_producers)
    ]

    print(f"=== Suspect wines (country=Australia, state=NULL, no AU marker) ===")
    print(f"    {len(suspects)} suspect / {len(au_no_state)} total AU-no-state wines\n")
    for r in suspects:
        print(f"  [{r['id']:5}] {r['name']}")

    conn.close()
    return suspects


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true",
                        help="Apply brand corrections to the DB (default: dry run)")
    args = parser.parse_args()
    run(fix=args.fix)
