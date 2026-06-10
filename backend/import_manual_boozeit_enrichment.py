"""
Import manually enriched Boozeit wines from CSV.

Expected CSV format:
  id,name,varietal,offers,vivino_rating,vivino_url

Example:
  20390,McWilliam's Fruitwood Red,Moscato,1,3.5,https://www.vivino.com/wines/...
"""

from dotenv import load_dotenv
load_dotenv()

import os, psycopg2, psycopg2.extras, csv, sys

if len(sys.argv) < 2:
    print("Usage: python import_manual_boozeit_enrichment.py <csv_file>")
    print("\nExample: python import_manual_boozeit_enrichment.py boozeit_manual_entries.csv")
    sys.exit(1)

csv_file = sys.argv[1]

if not os.path.exists(csv_file):
    print(f"Error: File '{csv_file}' not found")
    sys.exit(1)

conn = psycopg2.connect(os.environ['DATABASE_URL'], cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

updated = 0
skipped = 0
errors = 0

print(f"Importing manual enrichment from: {csv_file}\n")

with open(csv_file, 'r') as f:
    reader = csv.DictReader(f)

    for i, row in enumerate(reader, start=2):  # start=2 because row 1 is header
        try:
            wine_id = int(row['id'].strip())
            rating = row['vivino_rating'].strip()
            url = row['vivino_url'].strip()

            # Skip if rating is empty
            if not rating:
                skipped += 1
                continue

            rating = float(rating)

            # Validate rating (0-5)
            if rating < 0 or rating > 5:
                print(f"Row {i}: Invalid rating {rating} (must be 0-5)")
                errors += 1
                continue

            # Update wine with vivino data
            cur.execute("""
                UPDATE wines
                SET vivino_rating = %s, vivino_url = %s
                WHERE id = %s
            """, (rating, url, wine_id))

            if cur.rowcount > 0:
                updated += 1
            else:
                print(f"Row {i}: Wine ID {wine_id} not found")
                errors += 1

        except ValueError as e:
            print(f"Row {i}: Parse error — {e}")
            errors += 1
        except Exception as e:
            print(f"Row {i}: Error — {e}")
            errors += 1

conn.commit()
conn.close()

print()
print("=" * 70)
print(f"Import complete")
print(f"  Updated:  {updated} wines")
print(f"  Skipped:  {skipped} wines (empty rating)")
print(f"  Errors:   {errors} wines")
print("=" * 70)
