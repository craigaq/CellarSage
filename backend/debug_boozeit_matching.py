"""
Debug Boozeit wine matching against Vivino results.
Shows why matches are being rejected and what the actor returns.
"""

from dotenv import load_dotenv
load_dotenv()

import os, psycopg2, psycopg2.extras
from sync.enrich_vivino import _call_actor, _match_wine, _clean

conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

# Get first 10 unenriched Boozeit wines
cur.execute("""
    SELECT DISTINCT w.id, w.name
    FROM merchant_offers mo
    JOIN wines w ON w.id = mo.wine_id
    WHERE mo.retailer = 'boozeit' AND w.vivino_rating IS NULL
    ORDER BY w.id
    LIMIT 10
""")

boozeit_wines = cur.fetchall()
print(f"Testing {len(boozeit_wines)} Boozeit wines\n")

for wine_row in boozeit_wines:
    wine_id = wine_row['id']
    wine_name = wine_row['name']

    print(f"\n{'='*70}")
    print(f"Wine: [{wine_id}] {wine_name}")
    print(f"{'='*70}")

    # Call the actor for this single wine
    try:
        results = _call_actor([wine_name])
        print(f"Actor returned {len(results)} results:")

        if not results:
            print("  → No results from actor")
        else:
            for i, r in enumerate(results[:3], 1):
                winery = r.get('winery') or ''
                name = r.get('name') or ''
                country = r.get('country') or ''
                rating = r.get('average_rating') or 'N/A'
                print(f"\n  {i}. {winery} {name}")
                print(f"     Country: {country} | Rating: {rating}")

            # Try matching
            print(f"\nAttempting match...")
            matched = _match_wine({'id': wine_id, 'name': wine_name, 'vintage': None}, results)
            if matched:
                print(f"  ✓ MATCHED: {matched.get('winery')} {matched.get('name')}")
            else:
                print(f"  ✗ NO MATCH (brand guard or low confidence)")

                # Debug: show why it failed
                from sync.enrich_vivino import _vivino_label, _brand_token, _normalize_brand

                query = _clean(wine_name)
                brand = _brand_token(query)

                print(f"\n  Debug info:")
                print(f"    Cleaned query: '{query}'")
                print(f"    Brand token: '{brand}'")
                print(f"    Normalized brand: '{_normalize_brand(brand)}'")

                # Check each result's brand
                for i, r in enumerate(results[:3], 1):
                    label = _vivino_label(r)
                    normalized_label = _normalize_brand(label)
                    has_brand = _normalize_brand(brand) in normalized_label if brand else False
                    print(f"\n    Result {i}: '{label}'")
                    print(f"      Normalized: '{normalized_label}'")
                    print(f"      Contains brand '{brand}'? {has_brand}")

    except Exception as e:
        print(f"  Error calling actor: {e}")

conn.close()
