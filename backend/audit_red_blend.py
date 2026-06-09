import os, psycopg2, psycopg2.extras
for line in open(".env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
conn = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()
cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE o.price < 20)                AS under20,
        COUNT(*) FILTER (WHERE o.price BETWEEN 20 AND 35)   AS t20_35,
        COUNT(*) FILTER (WHERE o.price BETWEEN 36 AND 60)   AS t36_60,
        COUNT(*) FILTER (WHERE o.price BETWEEN 61 AND 100)  AS t61_100,
        COUNT(*) FILTER (WHERE o.price > 100)               AS over100,
        COUNT(*)                                            AS total
    FROM wines w
    JOIN merchant_offers o ON o.wine_id = w.id
    WHERE w.varietal = 'Red Blend'
      AND o.price IS NOT NULL
""")
r = cur.fetchone()
print(f"Red Blend offers by budget tier:\n")
print(f"  Under $20   : {r['under20']}")
print(f"  $20 – $35   : {r['t20_35']}")
print(f"  $36 – $60   : {r['t36_60']}")
print(f"  $61 – $100  : {r['t61_100']}")
print(f"  Over $100   : {r['over100']}")
print(f"  {'─'*20}")
print(f"  TOTAL       : {r['total']}")
cur.close(); conn.close()
