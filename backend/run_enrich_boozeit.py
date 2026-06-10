"""Enrich Boozeit wines with Vivino ratings — run once to bootstrap."""
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")

from dotenv import load_dotenv
load_dotenv()

from sync.enrich_vivino import enrich_vivino

# Boozeit added 607 new wines — run a large batch to cover as many as possible
enriched = enrich_vivino(limit=624)
print(f"\nEnriched: {enriched} wines")
