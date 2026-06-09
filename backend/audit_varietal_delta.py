"""
Compare current varietal offer counts against the pre-blend-fix baseline.
Baseline captured from audit_varietals.py run earlier tonight (post synonym fix).
"""
import os, psycopg2, psycopg2.extras

for line in open(".env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())

conn = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

cur.execute("""
    SELECT w.varietal, COUNT(*) AS total
    FROM wines w
    JOIN merchant_offers o ON o.wine_id = w.id
    WHERE o.price IS NOT NULL
    GROUP BY w.varietal
    ORDER BY w.varietal
""")
current = {r["varietal"]: r["total"] for r in cur.fetchall()}

# Baseline from audit run post-synonym-fix, pre-blend-fix (earlier tonight)
baseline = {
    "Albariño":            5,
    "Barbera":             4,
    "Cabernet Franc":      4,
    "Cabernet Sauvignon":  262,
    "Carménère":           1,
    "Cava":                1,
    "Champagne":           77,
    "Chardonnay":          210,
    "Chenin Blanc":        2,
    "Fiano":               3,
    "Gamay":               2,
    "Gewürztraminer":      3,
    "Grenache":            67,
    "Grüner Veltliner":    2,
    "Malbec":              25,
    "Marsanne":            3,
    "Merlot":              73,
    "Moscato":             68,
    "Mourvèdre":           3,
    "Muscat Liqueur":      1,
    "Nebbiolo":            1,
    "Nero d'Avola":        3,
    "Pinot Grigio":        102,
    "Pinot Noir":          120,
    "Prosecco":            61,
    "Red Blend":           136,
    "Riesling":            88,
    "Sangiovese":          10,
    "Sauvignon Blanc":     213,
    "Semillon":            35,
    "Sparkling Shiraz":    6,
    "Syrah/Shiraz":        404,
    "Tawny Port":          31,
    "Tempranillo":         53,
    "Torrontés":           1,
    "Vermentino":          2,
    "Vintage Port":        1,
    "Viognier":            2,
    "White Blend":         59,
    "Zinfandel":           1,
}

print(f"{'Varietal':<25} {'Before':>7} {'After':>7} {'Delta':>7}")
print("-" * 50)

changes = []
for varietal, before in sorted(baseline.items()):
    after = current.get(varietal, 0)
    delta = after - before
    if delta != 0:
        changes.append((varietal, before, after, delta))

for varietal, before, after, delta in sorted(changes, key=lambda x: x[3]):
    sign = "+" if delta > 0 else ""
    print(f"  {varietal:<23} {before:>7} {after:>7} {sign}{delta:>6}")

cur.close()
conn.close()
