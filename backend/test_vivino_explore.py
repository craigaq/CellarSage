from dotenv import load_dotenv
load_dotenv()
import os
from apify_client import ApifyClient

client = ApifyClient(os.environ['APIFY_API_TOKEN'])

# Try different parameter names
tests = [
    {"wines": ["Penfolds Grange"]},
    {"wine_names": ["Penfolds Grange"]},
    {"wineNames": ["Penfolds Grange"]},
    {"searchTerms": ["Penfolds Grange"]},
    {"names": ["Penfolds Grange"]},
]

for i, params in enumerate(tests):
    print(f"\nTest {i+1}: {list(params.keys())}")
    try:
        run = client.actor("mrbridge/vivino-wine-data-scraper").call(run_input=params)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"  Results: {len(items)}")
    except Exception as e:
        print(f"  Error: {e}")
