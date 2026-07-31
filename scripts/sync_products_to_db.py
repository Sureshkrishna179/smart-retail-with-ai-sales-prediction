"""
Sync CSV Products → MySQL
=========================
Reads files/products.csv and inserts/updates all 100 products into the
MySQL `products` table so the web UI dropdown matches the ML model.

Usage:
    $env:PYTHONPATH = "c:\MY Projects\Project AI Sales\src"
    & "c:\MY Projects\Project AI Sales\.venv\Scripts\python.exe" "c:\MY Projects\Project AI Sales\scripts\sync_products_to_db.py"
"""

import sys
import os
import csv
from pathlib import Path

# Add src to path so we can import smartretail
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smartretail.db.connection import get_connection

BASE_DIR    = Path(__file__).resolve().parents[1]
PRODUCTS_CSV = BASE_DIR / "files" / "products.csv"
STORES_CSV   = BASE_DIR / "files" / "stores.csv"


def parse_unit(pack_size: str) -> str:
    """Extract unit from Pack_Size like '1 kg' → 'kg', '500 g' → 'g', '200 ml' → 'ml'."""
    parts = pack_size.strip().split()
    if len(parts) >= 2:
        return parts[-1].lower()
    return "piece"


def sync_products():
    """Insert or update all products from CSV into MySQL."""
    if not PRODUCTS_CSV.exists():
        print(f"ERROR: {PRODUCTS_CSV} not found!")
        return False

    # Read CSV
    with open(PRODUCTS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Read {len(rows)} products from {PRODUCTS_CSV.name}")
    print(f"Columns: {list(rows[0].keys()) if rows else 'EMPTY'}")

    conn = get_connection()
    if conn is None:
        print("ERROR: Cannot connect to MySQL. Check your .env DB settings.")
        return False

    cursor = conn.cursor(dictionary=True)
    inserted = 0
    updated  = 0
    errors   = 0

    for row in rows:
        pid       = row.get("Product_ID", "").strip()
        name      = row.get("Product_Name", "").strip()
        category  = row.get("Category", "General").strip()
        pack_size = row.get("Pack_Size", "piece").strip()
        price     = float(row.get("Base_Price_2021_INR", "0").strip())
        unit      = parse_unit(pack_size)

        # Display name includes pack size for clarity
        display_name = f"{name} ({pack_size})" if pack_size else name

        try:
            # Check if product already exists (by name match)
            cursor.execute("SELECT id FROM products WHERE name = %s", (display_name,))
            existing = cursor.fetchone()

            if existing:
                # Update price and category
                cursor.execute(
                    "UPDATE products SET category=%s, unit=%s, price=%s WHERE id=%s",
                    (category, unit, price, existing["id"])
                )
                updated += 1
            else:
                # Insert new product with reasonable defaults
                cursor.execute(
                    """INSERT INTO products (name, category, unit, price, current_stock, min_stock_level)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (display_name, category, unit, price, 200, 50)
                )
                inserted += 1
        except Exception as e:
            print(f"  ERROR for {pid} ({name}): {e}")
            errors += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n{'='*60}")
    print(f"  Sync Complete!")
    print(f"  Inserted: {inserted}")
    print(f"  Updated:  {updated}")
    print(f"  Errors:   {errors}")
    print(f"  Total in CSV: {len(rows)}")
    print(f"{'='*60}")
    return True


def sync_stores():
    """Insert stores into a stores table (creates it if needed)."""
    if not STORES_CSV.exists():
        print(f"Stores CSV not found at {STORES_CSV}, skipping.")
        return

    with open(STORES_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r.get("Store_ID", "").strip()]

    if not rows:
        return

    conn = get_connection()
    if conn is None:
        return

    cursor = conn.cursor()

    # Create stores table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stores (
            id INT AUTO_INCREMENT PRIMARY KEY,
            store_id VARCHAR(10) NOT NULL UNIQUE,
            store_name VARCHAR(100) NOT NULL,
            city VARCHAR(50),
            region VARCHAR(50)
        )
    """)

    for row in rows:
        sid   = row.get("Store_ID", "").strip()
        sname = row.get("Store_Name", "").strip()
        city  = row.get("City", "").strip()
        region = row.get("Region", "").strip()
        try:
            cursor.execute(
                """INSERT INTO stores (store_id, store_name, city, region)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE store_name=%s, city=%s, region=%s""",
                (sid, sname, city, region, sname, city, region)
            )
        except Exception as e:
            print(f"  Store error {sid}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"Synced {len(rows)} stores to MySQL.")


if __name__ == "__main__":
    print("=" * 60)
    print("  CSV → MySQL Product Sync")
    print("=" * 60)
    print()

    ok = sync_products()
    if ok:
        sync_stores()
        print("\nDone! Restart the server and refresh the browser to see the updated products.")
    else:
        print("\nSync failed. Fix the errors above and try again.")
        sys.exit(1)
