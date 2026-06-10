from dotenv import load_dotenv
load_dotenv()
import os
from sync.scraper import run_actor

# Test with well-known wines that should definitely exist on Vivino
test_names = [
    "Penfolds Grange",
    "Cloudy Bay Sauvignon Blanc",
    "Brown Brothers Moscato",
    "Veuve Clicquot Yellow Label",
]

print("Testing Vivino actor with known wines...")
for wine_name in test_names:
    print(f"\nTesting: {wine_name}")
    try:
        results = run_actor(
            actor_id="mrbridge/vivino-wine-data-scraper",
            actor_input={
                'wineNames': [wine_name],
                'searchMode': 'name_and_vintage',
                'maxResultsPerSearch': 3,
                'includeTasteProfile': True,
                'includeReviews': False,
                'countryCode': 'AU',
                'shipTo': 'AU',
            },
            max_items=3,
        )
        print(f"  Results: {len(results)} matches")
        for r in results:
            print(f"    - {r.get('winery')} {r.get('name')} (rating: {r.get('average_rating')})")
    except Exception as e:
        print(f"  Error: {e}")

print("\n\nNow testing WITHOUT country restrictions...")
for wine_name in test_names[:2]:
    print(f"\n→ Testing (no AU filter): {wine_name}")
    try:
        results = run_actor(
            actor_id="mrbridge/vivino-wine-data-scraper",
            actor_input={
                'wineNames': [wine_name],
                'searchMode': 'name_and_vintage',
                'maxResultsPerSearch': 3,
                'includeTasteProfile': True,
                'includeReviews': False,
            },
            max_items=3,
        )
        print(f"  Results: {len(results)} matches")
        for r in results:
            print(f"    - {r.get('winery')} {r.get('name')} ({r.get('country')}) rating: {r.get('average_rating')}")
    except Exception as e:
        print(f"  Error: {e}")
