"""
Generate realistic Indian grocery daily sales CSV for SmartRetail AI.
Output: data/grocery_sales_realistic.csv (Date, Product, Sales_Qty)
"""

import csv
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "backend"))
from paths import GROCERY_CSV  # noqa: E402

# SKU-level products aligned with setup_database.py catalog
PRODUCTS = {
    "Rice 1kg": {"base": 18, "category": "staple", "fest_mult": 1.6},
    "Rice 5kg": {"base": 8, "category": "staple", "fest_mult": 1.7},
    "Sona Masuri Rice 5kg": {"base": 6, "category": "staple", "fest_mult": 1.5},
    "Wheat 1kg": {"base": 14, "category": "staple", "fest_mult": 1.5},
    "Sugar 1kg": {"base": 12, "category": "staple", "fest_mult": 1.4},
    "Tata Salt 1kg": {"base": 10, "category": "staple", "fest_mult": 1.3},
    "Toor Dal 1kg": {"base": 11, "category": "staple", "fest_mult": 1.5},
    "Moong Dal 1kg": {"base": 9, "category": "staple", "fest_mult": 1.4},
    "Urad Dal 1kg": {"base": 7, "category": "staple", "fest_mult": 1.3},
    "Oil 1 litre": {"base": 9, "category": "staple", "fest_mult": 1.5},
    "Coconut Oil 500ml": {"base": 6, "category": "staple", "fest_mult": 1.4},
    "Tea 250g": {"base": 11, "category": "beverage", "fest_mult": 1.3},
    "Coffee 100g": {"base": 5, "category": "beverage", "fest_mult": 1.2},
    "Milk 500ml": {"base": 35, "category": "dairy", "fest_mult": 1.2},
    "Curd 500g": {"base": 22, "category": "dairy", "fest_mult": 1.15},
    "Butter 100g": {"base": 8, "category": "dairy", "fest_mult": 1.25},
    "Biscuits Medium": {"base": 28, "category": "snacks", "fest_mult": 1.4},
    "Biscuits Family": {"base": 12, "category": "snacks", "fest_mult": 1.5},
    "Soap Bar": {"base": 9, "category": "personal", "fest_mult": 1.2},
    "Shampoo 200ml": {"base": 6, "category": "personal", "fest_mult": 1.25},
    "Chilli Powder 100g": {"base": 7, "category": "spice", "fest_mult": 1.6},
    "Turmeric 100g": {"base": 8, "category": "spice", "fest_mult": 1.5},
    "Cardamom 50g": {"base": 3, "category": "spice", "fest_mult": 2.0},
    "Washing Powder 1kg": {"base": 7, "category": "cleaning", "fest_mult": 1.2},
    "Dish Soap 500ml": {"base": 6, "category": "cleaning", "fest_mult": 1.1},
    "Garlic 250g": {"base": 5, "category": "fresh", "fest_mult": 1.4},
}

# (month, day_start, day_end) festival windows — Tamil Nadu + national grocery peaks
FESTIVAL_WINDOWS = [
    (1, 7, 17),    # Pongal shopping
    (1, 26, 26),   # Republic Day
    (3, 10, 16),   # Holi week
    (4, 10, 14),   # Eid / Ramadan peak
    (8, 12, 18),   # Independence + Janmashtami
    (9, 1, 10),    # Onam / Vinayagar prep
    (10, 15, 31),  # Deepavali shopping
    (11, 1, 5),    # Diwali tail
    (12, 20, 31),  # Christmas / New Year
]


def in_festival_window(d: datetime) -> bool:
    m, day = d.month, d.day
    for fm, start, end in FESTIVAL_WINDOWS:
        if m == fm and start <= day <= end:
            return True
    return False


def daily_qty(product: str, meta: dict, d: datetime, rng: random.Random) -> int:
    base = meta["base"]
    # Month seasonality (summer drinks, monsoon staples)
    if meta["category"] == "dairy" and d.month in (4, 5, 6):
        base = int(base * 1.12)
    if meta["category"] == "staple" and d.month in (7, 8, 9):
        base = int(base * 1.08)
    if d.weekday() >= 5:
        base = int(base * 1.18)
    if in_festival_window(d):
        base = int(base * meta["fest_mult"])
    # Pay-day effect (1st and 15th)
    if d.day in (1, 2, 15, 16):
        base = int(base * 1.1)
    noise = rng.randint(-4, 5)
    return max(1, base + noise)


def main():
    rng = random.Random(42)
    out = GROCERY_CSV
    out.parent.mkdir(parents=True, exist_ok=True)

    start = datetime(2025, 1, 1)
    end = datetime(2025, 12, 31)
    rows = []
    current = start
    while current <= end:
        for product, meta in PRODUCTS.items():
            qty = daily_qty(product, meta, current, rng)
            rows.append((current.strftime("%Y-%m-%d"), product, qty))
        current += timedelta(days=1)

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Product", "Sales_Qty"])
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out}")
    print(f"Products: {len(PRODUCTS)}, days: {(end - start).days + 1}")


if __name__ == "__main__":
    main()
