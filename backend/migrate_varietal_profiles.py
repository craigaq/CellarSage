"""
Migrate wine_catalog.py profiles to the varietal_profiles PostgreSQL table.

Creates the table if it doesn't exist, then upserts all bundled profiles.
Safe to re-run — uses ON CONFLICT DO UPDATE to keep DB in sync with code.

Usage:
    cd backend
    DATABASE_URL=... python migrate_varietal_profiles.py
"""

import os, sys, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

for line in open(os.path.join(os.path.dirname(__file__), '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL not set — run from the backend/ directory with .env loaded.")

import psycopg2, psycopg2.extras
sys.path.insert(0, os.path.dirname(__file__))
from wine_catalog import WINE_DATABASE

DDL = """
CREATE TABLE IF NOT EXISTS varietal_profiles (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(120) NOT NULL UNIQUE,
    varietal         VARCHAR(120) NOT NULL DEFAULT '',
    sku_id           VARCHAR(40)  NOT NULL DEFAULT '',
    acidity_ph       NUMERIC(5,3) NOT NULL,
    body             NUMERIC(4,2) NOT NULL,
    tannin_structure SMALLINT     NOT NULL,
    aromatic_intensity SMALLINT   NOT NULL,
    abv_percentage   NUMERIC(5,2) NOT NULL DEFAULT 13.0,
    residual_sugar_gl NUMERIC(8,2) NOT NULL DEFAULT 2.0,
    style            VARCHAR(20)  NOT NULL DEFAULT 'Dry',
    location_tag     VARCHAR(40)  NOT NULL DEFAULT '',
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
"""

UPSERT = """
INSERT INTO varietal_profiles
    (name, varietal, sku_id, acidity_ph, body, tannin_structure,
     aromatic_intensity, abv_percentage, residual_sugar_gl, style, location_tag, updated_at)
VALUES
    (%(name)s, %(varietal)s, %(sku_id)s, %(acidity_ph)s, %(body)s, %(tannin_structure)s,
     %(aromatic_intensity)s, %(abv_percentage)s, %(residual_sugar_gl)s, %(style)s, %(location_tag)s, now())
ON CONFLICT (name) DO UPDATE SET
    varietal           = EXCLUDED.varietal,
    sku_id             = EXCLUDED.sku_id,
    acidity_ph         = EXCLUDED.acidity_ph,
    body               = EXCLUDED.body,
    tannin_structure   = EXCLUDED.tannin_structure,
    aromatic_intensity = EXCLUDED.aromatic_intensity,
    abv_percentage     = EXCLUDED.abv_percentage,
    residual_sugar_gl  = EXCLUDED.residual_sugar_gl,
    style              = EXCLUDED.style,
    location_tag       = EXCLUDED.location_tag,
    updated_at         = now()
WHERE
    varietal_profiles.acidity_ph         != EXCLUDED.acidity_ph
    OR varietal_profiles.body            != EXCLUDED.body
    OR varietal_profiles.tannin_structure != EXCLUDED.tannin_structure
    OR varietal_profiles.aromatic_intensity != EXCLUDED.aromatic_intensity
    OR varietal_profiles.abv_percentage  != EXCLUDED.abv_percentage
    OR varietal_profiles.residual_sugar_gl != EXCLUDED.residual_sugar_gl
    OR varietal_profiles.style           != EXCLUDED.style
    OR varietal_profiles.location_tag    != EXCLUDED.location_tag;
"""

conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
            logging.info("Table varietal_profiles ensured.")
            rows = [
                {
                    "name":               w.name,
                    "varietal":           w.varietal,
                    "sku_id":             w.sku_id,
                    "acidity_ph":         w.acidity_ph,
                    "body":               w.body,
                    "tannin_structure":   w.tannin_structure,
                    "aromatic_intensity": w.aromatic_intensity,
                    "abv_percentage":     w.abv_percentage,
                    "residual_sugar_gl":  w.residual_sugar_gl,
                    "style":              w.style,
                    "location_tag":       w.location_tag,
                }
                for w in WINE_DATABASE
            ]
            psycopg2.extras.execute_batch(cur, UPSERT, rows)
            logging.info("Upserted %d varietal profiles.", len(rows))
finally:
    conn.close()

print(f"\nDone: {len(WINE_DATABASE)} varietal profiles synced to DB.")
print("The API will now load profiles from the database on next startup (or cache flush).")
