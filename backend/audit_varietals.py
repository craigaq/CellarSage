import os, sys, psycopg2, psycopg2.extras

for line in open(os.path.join(os.path.dirname(__file__), ".env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, os.path.dirname(__file__))
from wine_catalog import WINE_DATABASE

varietals = sorted({w.varietal for w in WINE_DATABASE})

conn = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

cur.execute("""
    SELECT
        w.varietal,
        COUNT(*) FILTER (WHERE o.price < 20)                      AS under20,
        COUNT(*) FILTER (WHERE o.price BETWEEN 20 AND 35)         AS t20_35,
        COUNT(*) FILTER (WHERE o.price BETWEEN 36 AND 60)         AS t36_60,
        COUNT(*) FILTER (WHERE o.price BETWEEN 61 AND 100)        AS t61_100,
        COUNT(*) FILTER (WHERE o.price > 100)                     AS over100,
        COUNT(*)                                                   AS total
    FROM wines w
    JOIN merchant_offers o ON o.wine_id = w.id
    WHERE o.price IS NOT NULL
      AND w.varietal = ANY(%s)
    GROUP BY w.varietal
    ORDER BY w.varietal
""", (varietals,))

rows = cur.fetchall()
found = {r["varietal"] for r in rows}
missing = sorted(set(varietals) - found)

print(f"{'Varietal':<30} {'<$20':>6} {'$20-35':>7} {'$36-60':>7} {'$61-100':>8} {'>$100':>6} {'TOTAL':>6}")
print("-" * 80)
for r in rows:
    print(f"{r['varietal']:<30} {r['under20']:>6} {r['t20_35']:>7} {r['t36_60']:>7} {r['t61_100']:>8} {r['over100']:>6} {r['total']:>6}")
print("-" * 80)

cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE o.price < 20)               AS t1,
        COUNT(*) FILTER (WHERE o.price BETWEEN 20 AND 35)  AS t2,
        COUNT(*) FILTER (WHERE o.price BETWEEN 36 AND 60)  AS t3,
        COUNT(*) FILTER (WHERE o.price BETWEEN 61 AND 100) AS t4,
        COUNT(*) FILTER (WHERE o.price > 100)              AS t5,
        COUNT(*)                                           AS total
    FROM wines w
    JOIN merchant_offers o ON o.wine_id = w.id
    WHERE o.price IS NOT NULL AND w.varietal = ANY(%s)
""", (varietals,))
t = cur.fetchone()
print(f"{'TOTAL (in-stock offers)':<30} {t['t1']:>6} {t['t2']:>7} {t['t3']:>7} {t['t4']:>8} {t['t5']:>6} {t['total']:>6}")

if missing:
    print(f"\nVarietals with NO in-stock offers ({len(missing)}):")
    for v in missing:
        print(f"  - {v}")

cur.close()
conn.close()
