from dotenv import load_dotenv
load_dotenv()
import os
from sync.scraper import run_actor

# Test with one well-known wine
test_name = "Penfolds Grange"

print("Test 1: WITH AU country filter")
try:
    results = run_actor(
        actor_id="mrbridge/vivino-wine-data-scraper",
        actor_input={
            'wineNames': [test_name],
            'searchMode': 'name_and_vintage',
            'maxResultsPerSearch': 3,
            'includeTasteProfile': True,
            'includeReviews': False,
            'countryCode': 'AU',
            'shipTo': 'AU',
        },
        max_items=3,
    )
    print(f"Results: {len(results)}")
    for r in results:
        print(f"  {r.get('winery')} {r.get('name')} ({r.get('country')})")
except Exception as e:
    print(f"Error: {e}")

print("\nTest 2: WITHOUT country filter")
try:
    results = run_actor(
        actor_id="mrbridge/vivino-wine-data-scraper",
        actor_input={
            'wineNames': [test_name],
            'searchMode': 'name_and_vintage',
            'maxResultsPerSearch': 3,
            'includeTasteProfile': True,
            'includeReviews': False,
        },
        max_items=3,
    )
    print(f"Results: {len(results)}")
    for r in results:
        print(f"  {r.get('winery')} {r.get('name')} ({r.get('country')})")
except Exception as e:
    print(f"Error: {e}")
