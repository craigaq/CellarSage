from dotenv import load_dotenv
load_dotenv()
import os
from sync.enrich_vivino import _call_actor

# Test with a few known wines
test_wines = [
    "Penfolds Grange",
    "Cloudy Bay Sauvignon Blanc",
    "Brown Brothers Moscato",
]

print("Testing fixed enrich_vivino._call_actor()...")
try:
    results = _call_actor(test_wines)
    print(f"Results: {len(results)}")
    for r in results[:5]:
        print(f"  {r.get('winery')} {r.get('name')} ({r.get('country')}) - rating: {r.get('average_rating')}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
