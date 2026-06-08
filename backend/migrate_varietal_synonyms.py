"""
One-off migration: normalise varietal labels already in the wines table
to match our canonical catalog labels.

Fixes:
  Shiraz / Syrah       → Syrah/Shiraz
  Tawny                → Tawny Port
  Topaque / Tokay      → Muscat Liqueur

Safe to re-run — uses conditional UPDATE so unchanged rows are skipped.

Usage:
    cd backend
    python migrate_varietal_synonyms.py
"""
import os, sys, psycopg2, psycopg2.extras

for line in open(os.path.join(os.path.dirname(__file__), ".env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL not set.")

conn = psycopg2.connect(url)
cur  = conn.cursor()

migrations = [
    ("Syrah/Shiraz",   "LOWER(varietal) IN ('shiraz', 'syrah')"),
    ("Tawny Port",     "LOWER(varietal) = 'tawny'"),
    ("Muscat Liqueur", "LOWER(varietal) IN ('topaque', 'tokay', 'liqueur muscat', 'rutherglen muscat')"),
]

total = 0
for canonical, condition in migrations:
    cur.execute(
        f"UPDATE wines SET varietal = %s WHERE {condition} AND varietal != %s",
        (canonical, canonical),
    )
    n = cur.rowcount
    print(f"  {canonical:<20} — {n} row(s) updated")
    total += n

conn.commit()
cur.close()
conn.close()
print(f"\nDone. {total} wine record(s) updated.")
