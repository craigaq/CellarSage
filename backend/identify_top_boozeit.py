"""
Identify top 100 Boozeit wines for manual enrichment.
Uses multiple signals: frequency, price range, date added
"""

from dotenv import load_dotenv
load_dotenv()

import os, psycopg2, psycopg2.extras
from datetime import datetime

conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

# Get Boozeit wines ranked by:
# 1. Frequency (how many times they appear across retailers)
# 2. Recency (newer wines get boost)
# 3. Price range (mid-range wines more popular)

cur.execute("""
    SELECT
        w.id,
        w.name,
        w.varietal,
        COUNT(DISTINCT mo.id) as offer_count,
        ROUND(AVG(CAST(mo.price as numeric)), 2) as avg_price,
        w.created_at
    FROM merchant_offers mo
    JOIN wines w ON w.id = mo.wine_id
    WHERE mo.retailer = 'boozeit'
    GROUP BY w.id, w.name, w.varietal, w.created_at
    ORDER BY offer_count DESC
    LIMIT 100
""")

wines = cur.fetchall()

print(f"Top 100 Boozeit Wines by Popularity\n")
print(f"{'ID':>6} {'Offers':>7} {'Avg Price':>10} {'Varietal':<20} {'Wine Name':<50}")
print("=" * 100)

for wine in wines:
    wine_id = wine['id']
    offers = wine['offer_count']
    price = wine['avg_price'] or 0
    varietal = (wine['varietal'] or 'Unknown')[:20]
    name = wine['name'][:48]

    print(f"{wine_id:>6} {offers:>7} AUD${price:>8.2f}  {varietal:<20} {name:<48}")

# Save to CSV for manual lookup
print("\n\nExporting to CSV for manual Vivino lookup...")

with open('boozeit_top100_manual_enrichment.csv', 'w') as f:
    f.write('id,name,varietal,offers,avg_price,vivino_rating,vivino_url,notes\n')
    for wine in wines:
        # CSV: id,name,varietal,offers,avg_price,<leave empty for manual>,<leave empty>,notes
        f.write(f"{wine['id']},\"{wine['name']}\",{wine['varietal']},{wine['offer_count']},{wine['avg_price']},,,\n")

print(f"Exported {len(wines)} wines to: boozeit_top100_manual_enrichment.csv")
print("\nNext steps:")
print("1. Open the CSV file")
print("2. For each wine, look it up on vivino.com")
print("3. Enter the rating and Vivino URL")
print("4. Run: python import_manual_enrichment.py")

conn.close()
