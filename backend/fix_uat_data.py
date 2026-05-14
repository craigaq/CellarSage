"""One-shot UAT data fixes:
1. Fix Split Rock wines: country Australia→New Zealand, state TAS→NULL
2. Fix Sparkling Shiraz varietal: Shiraz→Sparkling Shiraz where name says so
3. Remove obvious bundle products (dozen / add-on) from merchant_offers
"""
import re
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# 1. Split Rock: correct country and clear wrong state
cur.execute("""
    UPDATE wines
    SET country = 'New Zealand', state = NULL
    WHERE LOWER(name) LIKE 'split rock%'
      AND country = 'Australia'
""")
print(f"Split Rock country fix: {cur.rowcount} wine(s) updated")

# 2. Sparkling Shiraz: update varietal where name contains 'sparkling shiraz'
cur.execute("""
    UPDATE wines
    SET varietal = 'Sparkling Shiraz'
    WHERE LOWER(name) LIKE '%sparkling shiraz%'
      AND (varietal IS NULL OR LOWER(varietal) != 'sparkling shiraz')
""")
print(f"Sparkling Shiraz varietal fix: {cur.rowcount} wine(s) updated")

# 3. Remove bundle merchant_offers (dozen / add-on in name)
cur.execute("""
    DELETE FROM merchant_offers
    WHERE wine_id IN (
        SELECT id FROM wines
        WHERE name ~* '\m(dozen|add[- ]?on)\M'
    )
""")
print(f"Bundle merchant_offers removed: {cur.rowcount} offer(s) deleted")

# Remove orphaned wine records (no remaining offers)
cur.execute("""
    DELETE FROM wines
    WHERE name ~* '\m(dozen|add[- ]?on)\M'
      AND id NOT IN (SELECT DISTINCT wine_id FROM merchant_offers)
""")
print(f"Orphaned bundle wine records removed: {cur.rowcount} wine(s) deleted")

conn.commit()
conn.close()
print("Done.")
