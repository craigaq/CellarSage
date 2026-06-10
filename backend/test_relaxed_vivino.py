"""
Test relaxed Vivino search params for Boozeit wines.
Compares: strict params vs relaxed params
"""

from dotenv import load_dotenv
load_dotenv()

import os, psycopg2, psycopg2.extras
from sync.scraper import run_actor
from sync.enrich_vivino import _match_wine, _extract

conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

# Get first 20 unenriched Boozeit wines
cur.execute("""
    SELECT DISTINCT w.id, w.name
    FROM merchant_offers mo
    JOIN wines w ON w.id = mo.wine_id
    WHERE mo.retailer = 'boozeit' AND w.vivino_rating IS NULL
    ORDER BY w.id
    LIMIT 20
""")

test_wines = [r['name'] for r in cur.fetchall()]
print(f"Testing {len(test_wines)} Boozeit wines with different params\n")

# Test 1: Current (strict) params
print("=" * 70)
print("TEST 1: STRICT PARAMS (current)")
print("=" * 70)
print("searchMode: 'name_and_vintage', shipTo: 'AU'")

try:
    results_strict = run_actor(
        actor_id="mrbridge/vivino-wine-data-scraper",
        actor_input={
            'wines': test_wines[:10],
            'searchMode': 'name_and_vintage',
            'maxResultsPerSearch': 3,
            'includeTasteProfile': True,
            'includeReviews': False,
            'shipTo': 'AU',
        },
        max_items=30,
    )
    print(f"Returned {len(results_strict)} results")
    matches_strict = len([r for r in results_strict if r.get('average_rating')])
    print(f"Valid results (with ratings): {matches_strict}\n")
except Exception as e:
    print(f"Error: {e}\n")

# Test 2: name_only search (ignore vintage)
print("=" * 70)
print("TEST 2: RELAXED PARAMS (searchMode: 'name_only')")
print("=" * 70)
print("searchMode: 'name_only', no vintage matching")

try:
    results_relaxed = run_actor(
        actor_id="mrbridge/vivino-wine-data-scraper",
        actor_input={
            'wines': test_wines[:10],
            'searchMode': 'name_only',
            'maxResultsPerSearch': 3,
            'includeTasteProfile': True,
            'includeReviews': False,
            'shipTo': 'AU',
        },
        max_items=30,
    )
    print(f"Returned {len(results_relaxed)} results")
    matches_relaxed = len([r for r in results_relaxed if r.get('average_rating')])
    print(f"Valid results (with ratings): {matches_relaxed}\n")
except Exception as e:
    print(f"Error: {e}\n")

# Test 3: Auto search mode
print("=" * 70)
print("TEST 3: AUTO MODE (searchMode: 'auto')")
print("=" * 70)
print("searchMode: 'auto', let actor decide")

try:
    results_most_relaxed = run_actor(
        actor_id="mrbridge/vivino-wine-data-scraper",
        actor_input={
            'wines': test_wines[:10],
            'searchMode': 'auto',
            'maxResultsPerSearch': 5,
            'includeTasteProfile': True,
            'includeReviews': False,
            'shipTo': 'AU',
        },
        max_items=50,
    )
    print(f"Returned {len(results_most_relaxed)} results")
    matches_most_relaxed = len([r for r in results_most_relaxed if r.get('average_rating')])
    print(f"Valid results (with ratings): {matches_most_relaxed}\n")
except Exception as e:
    print(f"Error: {e}\n")

# Summary
print("=" * 70)
print("SUMMARY")
print("=" * 70)
try:
    print(f"Strict params:       {matches_strict} valid results from {len(results_strict)} returned")
    print(f"Relaxed params:      {matches_relaxed} valid results from {len(results_relaxed)} returned")
    print(f"Most relaxed params: {matches_most_relaxed} valid results from {len(results_most_relaxed)} returned")

    if matches_relaxed > matches_strict:
        improvement = ((matches_relaxed - matches_strict) / matches_strict * 100) if matches_strict > 0 else 0
        print(f"\nRelaxed improves by: +{improvement:.0f}%")

    if matches_most_relaxed > matches_relaxed:
        improvement = ((matches_most_relaxed - matches_relaxed) / matches_relaxed * 100) if matches_relaxed > 0 else 0
        print(f"Most relaxed improves by: +{improvement:.0f}%")
except:
    pass

conn.close()
