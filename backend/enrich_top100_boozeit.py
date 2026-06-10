"""
Enrich top 100 Boozeit wines with Vivino data.
Runs enrichment and exports results to CSV for manual verification.
"""

from dotenv import load_dotenv
load_dotenv()

import os, psycopg2, psycopg2.extras, logging
from sync.enrich_vivino import enrich_vivino

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

print("=" * 70)
print("PHASE 2 HYBRID: Running Vivino enrichment on top 100 Boozeit wines")
print("=" * 70)
print()

# Run enrichment with a high limit to cover all 100
enriched_count = enrich_vivino(limit=100)

print()
print("=" * 70)
print(f"Enrichment complete: {enriched_count} wines enriched")
print("=" * 70)
print()

# Now export results to CSV
conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

# Get the enriched Boozeit wines
cur.execute("""
    SELECT
        w.id,
        w.name,
        w.varietal,
        COUNT(DISTINCT mo.id) as offer_count,
        w.vivino_rating,
        w.vivino_url,
        CASE WHEN w.vivino_rating IS NOT NULL THEN 'enriched' ELSE 'unenriched' END as status
    FROM merchant_offers mo
    JOIN wines w ON w.id = mo.wine_id
    WHERE mo.retailer = 'boozeit'
    GROUP BY w.id, w.name, w.varietal, w.vivino_rating, w.vivino_url
    ORDER BY offer_count DESC
    LIMIT 100
""")

results = cur.fetchall()

# Export to CSV
with open('boozeit_enrichment_results.csv', 'w') as f:
    f.write('id,name,varietal,offers,status,vivino_rating,vivino_url\n')
    for r in results:
        status = r['status']
        rating = r['vivino_rating'] or ''
        url = r['vivino_url'] or ''
        f.write(f"{r['id']},\"{r['name']}\",{r['varietal']},{r['offer_count']},{status},{rating},{url}\n")

print(f"Exported results to: boozeit_enrichment_results.csv")
print()

# Summary
enriched = [r for r in results if r['vivino_rating'] is not None]
unenriched = [r for r in results if r['vivino_rating'] is None]

print(f"Total wines processed:  {len(results)}")
print(f"Successfully enriched:  {len(enriched)} ({len(enriched)/len(results)*100:.0f}%)")
print(f"Need manual entry:      {len(unenriched)}")
print()

if len(unenriched) > 0:
    print("Top 20 wines needing manual verification:")
    print(f"{'ID':>6} {'Offers':>7} {'Wine Name':<50}")
    print("=" * 70)
    for i, wine in enumerate(unenriched[:20]):
        print(f"{wine['id']:>6} {wine['offer_count']:>7} {wine['name'][:48]:<48}")

conn.close()
