"""
Investigate thin/zero coverage for Muscat Liqueur, Botrytis Semillon, Port and Shiraz.
Shows what names/varietals actually exist in the DB for these categories.
"""
import os, sys, psycopg2, psycopg2.extras

for line in open(os.path.join(os.path.dirname(__file__), ".env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

conn = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def search(keywords, label):
    section(label)
    patterns = [f"%{kw}%" for kw in keywords]
    conditions = " OR ".join(["LOWER(w.name) LIKE LOWER(%s)" for _ in patterns])
    conditions += " OR " + " OR ".join(["LOWER(w.varietal) LIKE LOWER(%s)" for _ in patterns])
    all_params = patterns + patterns

    cur.execute(f"""
        SELECT
            w.name, w.varietal, w.vintage,
            COUNT(o.id)          AS offer_count,
            MIN(o.price)         AS min_price,
            MAX(o.price)         AS max_price,
            STRING_AGG(DISTINCT o.retailer, ', ' ORDER BY o.retailer) AS retailers
        FROM wines w
        LEFT JOIN merchant_offers o ON o.wine_id = w.id AND o.price IS NOT NULL
        WHERE {conditions}
        GROUP BY w.name, w.varietal, w.vintage
        ORDER BY offer_count DESC, w.name
        LIMIT 50
    """, all_params)
    rows = cur.fetchall()
    if not rows:
        print("  *** No matching wines found in DB at all ***")
        return
    print(f"  Found {len(rows)} wine(s) matching search terms\n")
    print(f"  {'Name':<45} {'Varietal':<22} {'Offers':>6} {'Min$':>6} {'Max$':>6}  Retailers")
    print(f"  {'-'*45} {'-'*22} {'-'*6} {'-'*6} {'-'*6}  {'-'*30}")
    for r in rows:
        name = (r['name'] or '')[:44]
        var  = (r['varietal'] or '')[:21]
        cnt  = r['offer_count'] or 0
        lo   = f"${r['min_price']:.0f}" if r['min_price'] else '-'
        hi   = f"${r['max_price']:.0f}" if r['max_price'] else '-'
        ret  = (r['retailers'] or '-')[:40]
        print(f"  {name:<45} {var:<22} {cnt:>6} {lo:>6} {hi:>6}  {ret}")

# 1. Shiraz — why only 6 offers under "Syrah/Shiraz"?
search(["shiraz", "syrah"], "SHIRAZ / SYRAH — what's in the DB?")

# 2. Muscat Liqueur — 0 offers
search(["muscat", "liqueur", "rutherglen"], "MUSCAT LIQUEUR — what's in the DB?")

# 3. Botrytis Semillon — 0 offers
search(["botrytis", "noble", "sauternes"], "BOTRYTIS SEMILLON — what's in the DB?")

# 4. Port — Vintage Port only 1 offer; check all port styles
search(["port", "porto", "tawny", "vintage port", "ruby port"], "PORT (all styles) — what's in the DB?")

cur.close()
conn.close()
