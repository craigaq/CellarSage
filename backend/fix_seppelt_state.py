"""
Fix Seppelt Original Sparkling Shiraz state: SA -> VIC.
Seppelt Great Western is in Victoria, not South Australia.
"""
import os
for line in open('.env'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1); os.environ.setdefault(k.strip(), v.strip())
import psycopg2, psycopg2.extras
conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()
cur.execute(
    "UPDATE wines SET state = 'VIC', region = 'Great Western' WHERE name ILIKE '%seppelt%sparkling%'",
)
print(f"Updated {cur.rowcount} record(s).")
conn.commit()
conn.close()
