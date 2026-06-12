"""
Seed style-gap beers: Wheat, Sour, Porter + key internationals.

The original 53-beer AU seed had zero Wheat, Sour, or Porter entries, which
left the Cicerone engine's top affinities unreachable (e.g. spicy/congruent
ranks Wheat +1.0) and made the welcome-page "Wheat & Fruity" / "Sour & Tart"
anchor chips point at nothing. All picks below are stocked by Dan Murphy's /
BWS in Australia.

Also corrects one data error from the original seed: Holgate Temptress was
entered as "Black IPA" — it is Holgate's flagship chocolate PORTER.

Idempotent: skips any beer whose name already exists.
"""

from dotenv import load_dotenv
import os, psycopg2, psycopg2.extras

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

# (name, ibu, body, malt_sweetness, hop_intensity, abv, carbonation, style, location_tag)
BEERS = [
    # ── Wheat (was: zero in catalog) ──
    ("Hoegaarden Witbier",                    13, 2.8, 3, 2, 4.9, 4, "Wheat", "International"),
    ("Weihenstephaner Hefeweissbier",         14, 3.0, 3, 2, 5.4, 4, "Wheat", "International"),
    ("White Rabbit White Ale",                15, 2.8, 3, 2, 4.5, 4, "Wheat", "National"),

    # ── Sour (was: zero in catalog) ──
    ("Pirate Life Acai & Passionfruit Sour",   8, 2.4, 3, 2, 4.2, 4, "Sour", "National"),
    ("Moon Dog Fizzer Tropical Crush",         5, 2.0, 2, 1, 4.2, 5, "Sour", "National"),

    # ── Porter (was: zero in catalog) ──
    ("James Squire Jack of Spades Porter",    28, 3.8, 3, 3, 5.0, 3, "Porter", "National"),
    ("Colonial Porter",                       30, 3.9, 3, 3, 5.6, 3, "Porter", "National"),

    # ── Internationals that fill texture/strength gaps ──
    # Guinness: nitro pour — creamy-light body, very low carbonation.
    ("Guinness Draught",                      45, 3.4, 2, 3, 4.2, 1, "Stout", "International"),
    # Duvel: high-ABV, bottle-conditioned fizz — the strong golden benchmark.
    ("Duvel Belgian Strong Golden",           32, 3.4, 2, 4, 8.5, 5, "Strong Ale", "International"),
]

inserted, skipped = 0, 0
for (name, ibu, body, sweet, hop, abv, carb, style, loc) in BEERS:
    cur.execute("SELECT 1 FROM beers WHERE name = %s", (name,))
    if cur.fetchone():
        skipped += 1
        continue
    cur.execute(
        """INSERT INTO beers (name, ibu_bitterness, body, malt_sweetness, hop_intensity,
                              abv_percentage, carbonation_level, beer_style, location_tag)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (name, ibu, body, sweet, hop, abv, carb, style, loc),
    )
    inserted += 1

# Data correction: Temptress is a chocolate porter, not a Black IPA.
cur.execute(
    "UPDATE beers SET beer_style = 'Porter' WHERE name ILIKE '%Temptress%' AND beer_style = 'Black IPA'"
)
corrected = cur.rowcount

conn.commit()

cur.execute("SELECT COUNT(*) AS n FROM beers")
total = cur.fetchone()['n']
cur.execute("SELECT beer_style, COUNT(*) AS n FROM beers GROUP BY beer_style ORDER BY n DESC")
print(f"Inserted {inserted}, skipped {skipped} (already present), corrected {corrected} (Temptress -> Porter)")
print(f"Total beers: {total}")
for row in cur.fetchall():
    print(f"  {row['beer_style']:<16} {row['n']}")
conn.close()
