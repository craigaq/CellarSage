import os
from dotenv import load_dotenv; load_dotenv()
import psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("ALTER TABLE merchant_offers ADD COLUMN IF NOT EXISTS rating FLOAT")
cur.execute("ALTER TABLE merchant_offers ADD COLUMN IF NOT EXISTS review_count INT DEFAULT 0")
conn.commit()
cur.execute("SELECT COUNT(*) FROM merchant_offers WHERE rating IS NOT NULL")
print(f"Offers with rating before sync: {cur.fetchone()[0]}")
cur.close(); conn.close()
print("Migration done.")
