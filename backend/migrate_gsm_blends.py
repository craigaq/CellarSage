import os, sys, psycopg2

for line in open(os.path.join(os.path.dirname(__file__), ".env")):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur  = conn.cursor()

patterns = [
    ("Shiraz Grenache Mourvedre", "shiraz.*grenache.*mourv"),
    ("Grenache + Mourvedre",      "grenache.*mourv"),
    ("Mourvedre + Shiraz",        "mourv.*(shiraz|syrah)"),
    ("Mourvedre + Grenache",      "mourv.*grenache"),
]

total = 0
for label, p in patterns:
    cur.execute(
        "UPDATE wines SET varietal = 'Red Blend' WHERE LOWER(name) ~ %s AND varietal != 'Red Blend'",
        (p,)
    )
    n = cur.rowcount
    if n:
        print(f"  {label:<35} — {n} row(s) updated")
    total += n

conn.commit()
cur.close()
conn.close()
print(f"\nDone. {total} record(s) updated to 'Red Blend'.")
