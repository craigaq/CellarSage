"""One-shot cleanup: decode HTML entities in wine names already in the DB."""
import html
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

cur.execute("SELECT id, name FROM wines WHERE name ~ '&[a-zA-Z#0-9]+;'")
rows = cur.fetchall()
print(f"Found {len(rows)} wines with HTML entities")

updates = [
    (html.unescape(name), wid)
    for wid, name in rows
    if html.unescape(name) != name
]
print(f"Cleaning {len(updates)} names:")
for new_name, wid in updates:
    orig = next(n for i, n in rows if i == wid)
    print(f"  {orig!r}  ->  {new_name!r}")

if updates:
    cur.executemany("UPDATE wines SET name = %s WHERE id = %s", updates)
    conn.commit()
    print("Done.")
else:
    print("Nothing to update.")

conn.close()
