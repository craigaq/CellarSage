import os, psycopg2, psycopg2.extras
for line in open(".env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
conn = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()
cur.execute("""
    SELECT retailer, COUNT(*) as offers
    FROM merchant_offers
    WHERE price IS NOT NULL
    GROUP BY retailer ORDER BY offers DESC
""")
print(f"{'Retailer':<35} {'Offers':>7}")
print("-" * 45)
total = 0
for r in cur.fetchall():
    print(f"{r['retailer']:<35} {r['offers']:>7}")
    total += r['offers']
print("-" * 45)
print(f"{'TOTAL':<35} {total:>7}")
cur.close(); conn.close()
