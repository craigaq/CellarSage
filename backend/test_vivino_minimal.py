from dotenv import load_dotenv
load_dotenv()
import os
from apify_client import ApifyClient

client = ApifyClient(os.environ['APIFY_API_TOKEN'])

# Try the ABSOLUTE minimal input
print("Minimal test: just wine names")
run = client.actor("mrbridge/vivino-wine-data-scraper").call(
    run_input={
        "wineNames": ["Penfolds Grange"],
        "maxResultsPerSearch": 3,
    }
)

items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
print(f"Results: {len(items)}")
for item in items:
    if isinstance(item, dict):
        print(f"  {item}")
    elif isinstance(item, list):
        for subitem in item:
            print(f"  {subitem}")
