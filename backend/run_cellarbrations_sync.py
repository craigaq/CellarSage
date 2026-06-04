"""
Run this script locally (not on Fly.io) to sync Cellarbrations Sunbury wines.
Residential IP is not blocked by Cellarbrations CDN; Fly.io server IP is.

Usage:
    cd backend
    python run_cellarbrations_sync.py
"""

import os, sys, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
sys.path.insert(0, os.path.dirname(__file__))

for line in open(os.path.join(os.path.dirname(__file__), '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())

from sync.scraper_cellarbrations_sunbury import scrape_cellarbrations_sunbury
from sync.normalizer import normalize
from sync.upsert import upsert_batch

print("=== Cellarbrations Sunbury — Local Sync ===\n")

raw = scrape_cellarbrations_sunbury()
if not raw:
    print("ERROR: No products returned. The API may be blocking this IP too.")
    print("Try again later or check your internet connection.")
    sys.exit(1)

print(f"Scraped {len(raw)} products")

pairs = normalize(raw, 'cellarbrations_sunbury')
print(f"Normalised {len(pairs)} wine/offer pairs")

wines_saved, offers_saved = upsert_batch(pairs)
print(f"\nDone: {wines_saved} wines, {offers_saved} offers upserted to DB")
