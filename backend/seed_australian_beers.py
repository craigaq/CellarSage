"""
Seed the beers table with Australian craft and commercial beers.

Attributes estimated from real beer profiles:
  IBU: International Bitterness Units (0–100+)
  Body: 1-5 expert rating (Light → Full)
  Malt Sweetness: 1-5 (dry → sweet)
  Hop Intensity: 1-10 (clean → intensely hoppy)
  ABV: Alcohol by Volume %
  Carbonation: 1-5 (flat → highly effervescent)
"""

from dotenv import load_dotenv
import os, psycopg2, psycopg2.extras

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

# Australian beers: (name, ibu, body, malt_sweetness, hop_intensity, abv, carbonation, style, location_tag)
BEERS = [
    # ── Coopers (Adelaide, SA) — iconic Australian brewery ──
    ("Coopers Sparkling Ale", 20, 3.5, 3, 3, 4.5, 3, "Ale", "National"),
    ("Coopers Pale Ale", 25, 3.2, 2, 4, 4.0, 3, "Pale Ale", "National"),
    ("Coopers Stout", 45, 4.2, 3, 5, 4.0, 3, "Stout", "National"),
    ("Coopers Extra Strong", 30, 3.8, 3, 3, 6.3, 2, "Strong Ale", "National"),

    # ── James Squire (Sydney, NSW) — mega-chain ──
    ("James Squire 150 Lashes Pale Ale", 50, 3.8, 2, 7, 4.7, 3, "Pale Ale", "National"),
    ("James Squire The Quaff Golden Ale", 20, 3.0, 2, 3, 4.2, 3, "Golden Ale", "National"),
    ("James Squire Amber Ale", 30, 3.5, 3, 4, 4.3, 3, "Amber Ale", "National"),
    ("James Squire IPA", 55, 3.6, 2, 8, 5.2, 3, "IPA", "National"),

    # ── Little Creatures (Fremantle, WA) — craft pioneer ──
    ("Little Creatures Pale Ale", 55, 3.8, 2, 8, 4.3, 3, "Pale Ale", "National"),
    ("Little Creatures Bright Ale", 25, 3.2, 2, 5, 3.9, 3, "Golden Ale", "National"),
    ("Little Creatures Pilsner", 35, 3.0, 1, 6, 4.5, 4, "Pilsner", "National"),
    ("Little Creatures Rogers", 35, 3.8, 3, 4, 4.8, 3, "Amber Ale", "National"),

    # ── Stone & Wood (Byron Bay, NSW) — coastal craft ──
    ("Stone & Wood Pacific Ale", 35, 3.2, 2, 6, 4.4, 3, "Ale", "National"),  # AU Pacific Ale (was mis-seeded Blonde Ale; "Ale" matches the other Pacific Ales)
    ("Stone & Wood Green Coast IPA", 60, 3.6, 2, 8, 5.3, 3, "IPA", "National"),
    ("Stone & Wood Lager", 25, 3.0, 1, 3, 4.2, 3, "Lager", "National"),

    # ── Tooheys (Sydney, NSW) — major commercial ──
    ("Tooheys Extra Dry", 20, 2.8, 1, 2, 4.6, 4, "Lager", "National"),
    ("Tooheys New", 18, 2.5, 1, 2, 4.7, 4, "Lager", "National"),
    ("Tooheys Old", 22, 3.5, 3, 3, 4.6, 3, "Ale", "National"),

    # ── Carlton (Victoria) — mega-brand ──
    ("Carlton Draught", 18, 2.6, 1, 2, 4.9, 4, "Lager", "National"),
    ("Carlton Pale Ale", 30, 3.2, 2, 4, 4.5, 3, "Pale Ale", "National"),
    ("Carlton Black", 45, 4.0, 3, 5, 4.8, 3, "Stout", "National"),

    # ── Cascade (Hobart, Tasmania) — heritage ──
    ("Cascade Pale Ale", 35, 3.3, 2, 5, 4.8, 3, "Pale Ale", "National"),
    ("Cascade Premium Lager", 22, 3.0, 1, 3, 5.0, 4, "Lager", "National"),
    ("Cascade Stout", 50, 4.2, 3, 6, 5.2, 3, "Stout", "National"),

    # ── Asahi (Brewed in Australia) ──
    ("Asahi Super Dry", 20, 2.8, 1, 2, 5.0, 4, "Lager", "National"),

    # ── Boag's (Hobart, Tasmania) ──
    ("Boag's Premium Lager", 25, 3.0, 1, 3, 5.0, 3, "Lager", "National"),
    ("Boag's Draught", 18, 2.8, 1, 2, 4.8, 4, "Lager", "National"),

    # ── Mountain Goat (Melbourne, Victoria) — craft ──
    ("Mountain Goat Pale Ale", 50, 3.5, 2, 7, 5.0, 3, "Pale Ale", "National"),
    ("Mountain Goat Hightail Ale", 35, 3.0, 2, 5, 4.8, 3, "Golden Ale", "National"),
    ("Mountain Goat Rare Breed", 65, 3.8, 2, 8, 6.2, 3, "IPA", "National"),

    # ── Feral (Perth, Western Australia) — craft ──
    ("Feral Hop Hog IPA", 70, 3.6, 2, 9, 5.6, 3, "IPA", "National"),
    ("Feral Sly Fox Amber Ale", 40, 3.5, 3, 5, 4.8, 3, "Amber Ale", "National"),
    ("Feral One Hop Stand Ale", 45, 3.2, 2, 6, 5.0, 3, "Pale Ale", "National"),

    # ── Balter (Gold Coast, Queensland) ──
    ("Balter XPA", 50, 3.2, 2, 7, 5.3, 3, "Extra Pale Ale", "National"),
    ("Balter Hazy Dream", 35, 3.2, 2, 6, 5.2, 3, "Hazy IPA", "National"),

    # ── Young Henrys (Newtown, Sydney) — indie craft ──
    ("Young Henrys Natural Lager", 20, 2.8, 1, 2, 4.5, 4, "Lager", "Local"),
    ("Young Henrys Hop Hog", 65, 3.6, 2, 9, 5.8, 3, "IPA", "Local"),

    # ── Hawkers (Adelaide, South Australia) ──
    ("Hawkers Pale Ale", 48, 3.4, 2, 7, 5.1, 3, "Pale Ale", "National"),
    ("Hawkers Pilsner", 32, 2.9, 1, 5, 4.9, 4, "Pilsner", "National"),

    # ── Lobethal Bierhaus (Adelaide, SA) ──
    ("Lobethal Amberizer", 40, 3.6, 3, 5, 4.8, 3, "Amber Ale", "Local"),

    # ── Holgate (Melbourne, Victoria) ──
    ("Holgate Brewing Pale Ale", 50, 3.4, 2, 7, 5.0, 3, "Pale Ale", "National"),
    ("Holgate Brewing Temptress", 65, 4.0, 3, 8, 6.0, 3, "Black IPA", "National"),

    # ── Pirate Life (Adelaide, SA) ──
    ("Pirate Life IPA", 70, 3.5, 2, 9, 6.5, 3, "IPA", "National"),
    ("Pirate Life Pale Ale", 55, 3.3, 2, 7, 5.2, 3, "Pale Ale", "National"),

    # ── Moo Brew (Hobart, Tasmania) ──
    ("Moo Brew Pale Ale", 45, 3.3, 2, 6, 4.8, 3, "Pale Ale", "National"),
    ("Moo Brew Pilsner", 35, 2.9, 1, 5, 5.1, 4, "Pilsner", "National"),

    # ── Stoney Creek (Kyneton, Victoria) ──
    ("Stoney Creek Blonde", 20, 3.0, 2, 3, 4.5, 4, "Golden Ale", "Local"),

    # ── West City (Perth, WA) ──
    ("West City Brewing Pale Ale", 48, 3.4, 2, 6, 5.0, 3, "Pale Ale", "Local"),

    # ── Bright Brewery (Bright, Victoria) ──
    ("Bright Brewery East India Pale Ale", 55, 3.5, 2, 8, 5.4, 3, "IPA", "Local"),

    # ── Motelier (Melbourne, Victoria) ──
    ("Motelier Lager", 18, 3.0, 1, 2, 4.5, 4, "Lager", "Local"),

    # International brands brewed in Australia (for comparison)
    ("Heineken Australia", 21, 2.8, 1, 2, 5.0, 4, "Lager", "International"),
    ("Budweiser Australia", 12, 2.5, 1, 1, 5.0, 4, "Lager", "International"),
    ("Corona Extra (AU)", 25, 2.5, 2, 1, 4.6, 4, "Pale Lager", "International"),
]

print(f"Inserting {len(BEERS)} beers into the database...")

for beer in BEERS:
    name, ibu, body, malt_sweet, hop_intensity, abv, carb, style, location = beer
    try:
        cur.execute(
            """
            INSERT INTO beers
            (name, ibu_bitterness, body, malt_sweetness, hop_intensity, abv_percentage, carbonation_level, beer_style, location_tag)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (name, ibu, body, malt_sweet, hop_intensity, abv, carb, style, location),
        )
        print(f"  OK {name}")
    except Exception as e:
        print(f"  ERROR {name}: {e}")

conn.commit()
cur.execute("SELECT COUNT(*) as total FROM beers")
total = cur.fetchone()['total']
print(f"\nSuccessfully seeded {total} beers!")

cur.close()
conn.close()
