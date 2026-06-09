"""
Fix wines that are multi-varietal blends but stored under a single varietal label.
Targets Malbec-led and Durif blends that should be 'Red Blend'.

Usage:
    cd backend
    python migrate_blend_varietals.py
"""
import os, sys, psycopg2

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

# Each entry: (description, SQL WHERE clause)
migrations = [
    ("Malbec Shiraz blends",   "LOWER(name) ~ 'malbec.*(shiraz|syrah)'"),
    ("Syrah/Shiraz Malbec",    "LOWER(name) ~ '(syrah|shiraz).*malbec'"),
    ("Malbec Durif blends",    "LOWER(name) ~ 'malbec.*durif'"),
    ("Malbec Cabernet blends", "LOWER(name) ~ 'malbec.*(cabernet|cab)'"),
    ("Malbec Merlot blends",   "LOWER(name) ~ 'malbec.*merlot'"),
    ("Shiraz Durif blends",    "LOWER(name) ~ '(shiraz|durif).*(durif|shiraz)'"),
]

total = 0
for label, condition in migrations:
    cur.execute(
        f"UPDATE wines SET varietal = 'Red Blend' WHERE {condition} AND varietal != 'Red Blend'",
    )
    n = cur.rowcount
    if n:
        print(f"  {label:<30} — {n} row(s) updated")
    total += n

conn.commit()
cur.close()
conn.close()
print(f"\nDone. {total} wine record(s) updated to 'Red Blend'.")
