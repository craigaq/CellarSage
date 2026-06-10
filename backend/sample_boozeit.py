from dotenv import load_dotenv
load_dotenv()
import os, psycopg2, psycopg2.extras

conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

cur.execute("""
    SELECT DISTINCT w.id, w.name, w.varietal, w.vintage
    FROM merchant_offers mo
    JOIN wines w ON w.id = mo.wine_id
    WHERE mo.retailer = 'boozeit'
    ORDER BY w.id
    LIMIT 20
""")

print("Sample Boozeit wines:")
for r in cur.fetchall():
    print(f"  [{r['id']:5}] {r['name']:50} | {r['varietal']:20} | {r['vintage']}")

conn.close()
