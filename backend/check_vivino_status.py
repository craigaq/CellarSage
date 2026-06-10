import os, psycopg2, psycopg2.extras
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) as total FROM wines WHERE retailer = 'boozeit'")
total = cur.fetchone()['total']

cur.execute("SELECT COUNT(*) as rated FROM wines WHERE retailer = 'boozeit' AND vivino_rating IS NOT NULL")
rated = cur.fetchone()['rated']

cur.execute("SELECT COUNT(*) as enriched FROM wines WHERE retailer = 'boozeit' AND vivino_enriched_at IS NOT NULL")
enriched = cur.fetchone()['enriched']

cur.execute("SELECT COUNT(*) as unenriched FROM wines WHERE retailer = 'boozeit' AND vivino_enriched_at IS NULL")
unenriched = cur.fetchone()['unenriched']

print(f"Total Boozeit wines:       {total}")
print(f"Vivino rated:              {rated} ({rated/total*100:.1f}%)")
print(f"Enrichment attempted:      {enriched} ({enriched/total*100:.1f}%)")
print(f"Not yet attempted:         {unenriched}")

if unenriched > 0:
    cur.execute("SELECT id, name FROM wines WHERE retailer = 'boozeit' AND vivino_enriched_at IS NULL ORDER BY id LIMIT 10")
    rows = cur.fetchall()
    print("\nSample unenriched wines:")
    for r in rows:
        print(f"  [{r['id']}] {r['name']}")

conn.close()
