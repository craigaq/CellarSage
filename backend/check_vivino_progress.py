from dotenv import load_dotenv
load_dotenv()
import os, psycopg2, psycopg2.extras
from datetime import datetime

conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

# Total Boozeit wines
cur.execute("SELECT COUNT(*) as total FROM merchant_offers WHERE retailer = 'boozeit'")
total = cur.fetchone()['total']

# Boozeit wines with Vivino rating
cur.execute("""
    SELECT COUNT(*) as rated FROM merchant_offers mo
    JOIN wines w ON w.id = mo.wine_id
    WHERE mo.retailer = 'boozeit' AND w.vivino_rating IS NOT NULL
""")
rated = cur.fetchone()['rated']

# Enrichment timestamp
cur.execute("""
    SELECT MAX(w.vivino_enriched_at) as latest
    FROM merchant_offers mo
    JOIN wines w ON w.id = mo.wine_id
    WHERE mo.retailer = 'boozeit' AND w.vivino_enriched_at IS NOT NULL
""")
latest = cur.fetchone()['latest']

progress_pct = (rated / total * 100) if total > 0 else 0

print(f"Boozeit Vivino Enrichment Progress")
print(f"=" * 50)
print(f"Total Boozeit wines:     {total}")
print(f"With Vivino ratings:     {rated} ({progress_pct:.1f}%)")
print(f"Last update:             {latest or 'Not started'}")
print(f"\nEstimated completion:    {total - rated} wines remaining")

if rated > 0:
    # Sample enriched wines
    cur.execute("""
        SELECT DISTINCT w.name, w.vivino_rating, w.vivino_review_count
        FROM merchant_offers mo
        JOIN wines w ON w.id = mo.wine_id
        WHERE mo.retailer = 'boozeit' AND w.vivino_rating IS NOT NULL
        ORDER BY w.vivino_enriched_at DESC
        LIMIT 5
    """)
    print(f"\nRecent enrichments:")
    for r in cur.fetchall():
        print(f"  {r['name'][:50]:50} | Rating: {r['vivino_rating']}")

conn.close()
