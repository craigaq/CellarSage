import os
for line in open('.env'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1); os.environ.setdefault(k.strip(), v.strip())
import psycopg2, psycopg2.extras
conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()
cur.execute("SELECT id, name, region, state, country, varietal FROM wines WHERE name ILIKE '%seppelt%sparkling%'")
rows = cur.fetchall()
for r in rows:
    print(dict(r))
conn.close()
