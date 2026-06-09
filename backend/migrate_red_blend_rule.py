"""
Apply the 'two red varietals in name = Red Blend' rule to all existing DB records.
Uses the same token list as the normalizer.
"""
import os, sys, psycopg2, psycopg2.extras

for line in open(os.path.join(os.path.dirname(__file__), ".env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, os.path.dirname(__file__))
from sync.normalizer import _count_red_varietals

conn = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=psycopg2.extras.RealDictCursor)
cur  = conn.cursor()

cur.execute("SELECT id, name, varietal FROM wines WHERE varietal != 'Red Blend'")
rows = cur.fetchall()

to_fix = [(r["id"], r["name"], r["varietal"]) for r in rows if _count_red_varietals(r["name"]) >= 2]

if not to_fix:
    print("No additional records to fix.")
else:
    print(f"Found {len(to_fix)} record(s) to reclassify as Red Blend:\n")
    for wid, name, old_var in to_fix:
        print(f"  [{old_var}]  {name}")

    fix_ids = [r[0] for r in to_fix]
    cur.execute(
        "UPDATE wines SET varietal = 'Red Blend' WHERE id = ANY(%s)",
        (fix_ids,)
    )
    conn.commit()
    print(f"\nDone. {len(to_fix)} record(s) updated.")

cur.close()
conn.close()
