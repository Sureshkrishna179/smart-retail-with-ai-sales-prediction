"""
In-Memory Store (Decoupled Fallback Mode)
========================================
Provides complete in-memory fallback persistence for SmartRetail AI when
a live MySQL instance is not connected (e.g. during cloud demos, zero-cost
Render/Koyeb deployments, or offline local development).

Reads real product catalog from `files/products.csv` and provides:
  - Product catalog & inventory stock levels
  - Stock threshold alerts (Critical vs Warning vs Healthy)
  - Interactive POS cart checkout & thermal receipt generation
  - Revenue analytics & monthly KPI aggregates
  - Fallback authentication & user management
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("smartretail.db.inmemory")

BASE_DIR = Path(__file__).resolve().parents[3]
PRODUCTS_CSV = BASE_DIR / "files" / "products.csv"

_PRODUCTS: List[Dict[str, Any]] = []
_INVENTORY_LOG: List[Dict[str, Any]] = []
_AUDIT_LOG: List[Dict[str, Any]] = []
_INITIALIZED = False


def _parse_unit(pack_size: str) -> str:
    parts = pack_size.strip().split()
    if len(parts) >= 2:
        return parts[-1].lower()
    return "piece"


def _init_store():
    global _PRODUCTS, _AUDIT_LOG, _INITIALIZED
    if _INITIALIZED and _PRODUCTS:
        return

    _PRODUCTS = []
    if PRODUCTS_CSV.is_file():
        try:
            with open(PRODUCTS_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader):
                    pid = row.get("Product_ID", f"P{idx+1:03d}").strip()
                    name = row.get("Product_Name", f"Product {idx+1}").strip()
                    cat = row.get("Category", "Groceries").strip()
                    pack = row.get("Pack_Size", "").strip()
                    price = float(row.get("Base_Price_2021_INR", "50").strip() or "50")
                    unit = _parse_unit(pack)
                    display_name = f"{name} ({pack})" if pack else name

                    # Seed deterministic realistic stock
                    # 6 items have critical low stock (< 50) to demonstrate alerts
                    if idx in (3, 11, 19, 28, 42, 67):
                        stock = 15 + (idx % 25)
                    else:
                        stock = 75 + ((idx * 17) % 180)

                    _PRODUCTS.append({
                        "id": idx + 1,
                        "product_id": pid,
                        "name": display_name,
                        "category": cat,
                        "unit": unit,
                        "price": round(price, 2),
                        "current_stock": stock,
                        "min_stock_level": 50,
                    })
        except Exception as e:
            logger.warning("Could not read products.csv for inmemory store: %s", e)

    # Fallback seed if CSV wasn't found
    if not _PRODUCTS:
        seed = [
            ("Basmati Rice (1 kg)", "Rice & Grains", "kg", 99.96, 120),
            ("Sona Masoori Rice (1 kg)", "Rice & Grains", "kg", 88.28, 85),
            ("Toor Dal (1 kg)", "Pulses & Lentils", "kg", 142.17, 22),
            ("Moong Dal (1 kg)", "Pulses & Lentils", "kg", 130.99, 110),
            ("Sunflower Oil (1 L)", "Oils & Ghee", "L", 135.50, 18),
            ("Aashirvaad Atta (5 kg)", "Atta & Flour", "kg", 258.00, 95),
            ("Tata Salt (1 kg)", "Spices & Seasoning", "kg", 28.00, 240),
            ("Sugar (1 kg)", "Essentials", "kg", 45.00, 31),
        ]
        for idx, (n, c, u, p, s) in enumerate(seed):
            _PRODUCTS.append({
                "id": idx + 1,
                "product_id": f"P{idx+1:03d}",
                "name": n,
                "category": c,
                "unit": u,
                "price": p,
                "current_stock": s,
                "min_stock_level": 50,
            })

    _AUDIT_LOG = [
        {
            "id": 1,
            "username": "system",
            "action": "STARTUP",
            "details": f"In-Memory Decoupled Store initialized with {len(_PRODUCTS)} products",
            "ip_address": "127.0.0.1",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        {
            "id": 2,
            "username": "admin",
            "action": "ML_CORE_A",
            "details": "Detrended HGBR pre-trained model mounted successfully",
            "ip_address": "127.0.0.1",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    ]
    _INITIALIZED = True


def get_inmemory_products() -> List[Dict[str, Any]]:
    _init_store()
    return list(_PRODUCTS)


def get_inmemory_alerts() -> List[Dict[str, Any]]:
    _init_store()
    return [p for p in _PRODUCTS if p["current_stock"] < p["min_stock_level"]]


def restock_inmemory_product(product_id: int, quantity: int) -> Optional[Dict[str, Any]]:
    _init_store()
    for p in _PRODUCTS:
        if p["id"] == product_id or str(p.get("product_id")) == str(product_id):
            old = p["current_stock"]
            p["current_stock"] += quantity
            _INVENTORY_LOG.append({
                "product_id": p["id"],
                "change_type": "restock",
                "quantity": quantity,
                "previous_stock": old,
                "new_stock": p["current_stock"],
                "timestamp": datetime.now().isoformat(),
            })
            return {"name": p["name"], "old_stock": old, "new_stock": p["current_stock"]}
    return None


def bill_inmemory_products(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    _init_store()
    receipt = []
    grand = 0.0

    for item in items:
        pid = item.get("product_id")
        qty = int(item.get("quantity", 1))

        prod = next((p for p in _PRODUCTS if p["id"] == pid or str(p.get("product_id")) == str(pid)), None)
        if prod:
            prod["current_stock"] = max(0, prod["current_stock"] - qty)
            total = round(prod["price"] * qty, 2)
            grand += total
            receipt.append({
                "product_id": prod["id"],
                "name": prod["name"],
                "price": prod["price"],
                "quantity": qty,
                "total": total,
            })
        else:
            # Fallback for ad-hoc custom item
            price = float(item.get("price", 50))
            total = round(price * qty, 2)
            grand += total
            receipt.append({
                "product_id": pid,
                "name": item.get("name", f"Item #{pid}"),
                "price": price,
                "quantity": qty,
                "total": total,
            })

    return {
        "success": True,
        "receipt": receipt,
        "grand_total": round(grand, 2),
        "timestamp": datetime.now().isoformat(),
    }


def get_inmemory_reports() -> Dict[str, Any]:
    _init_store()
    total = len(_PRODUCTS)
    low = sum(1 for p in _PRODUCTS if p["current_stock"] < p["min_stock_level"])

    # 12-month historical revenue progression
    monthly = [
        {"month": "2025-10", "revenue": 142580.0, "units": 1840},
        {"month": "2025-11", "revenue": 168920.0, "units": 2150},
        {"month": "2025-12", "revenue": 195400.0, "units": 2680},
        {"month": "2026-01", "revenue": 210850.0, "units": 2920},
        {"month": "2026-02", "revenue": 155300.0, "units": 1990},
        {"month": "2026-03", "revenue": 172400.0, "units": 2240},
        {"month": "2026-04", "revenue": 188750.0, "units": 2490},
        {"month": "2026-05", "revenue": 194100.0, "units": 2580},
        {"month": "2026-06", "revenue": 161200.0, "units": 2080},
        {"month": "2026-07", "revenue": 179500.0, "units": 2320},
        {"month": "2026-08", "revenue": 184300.0, "units": 2410},
        {"month": "2026-09", "revenue": 201650.0, "units": 2710},
    ]

    top_prods = [
        {"name": p["name"], "category": p["category"], "total_qty": 450 + (p["id"] * 12), "total_revenue": round(p["price"] * (450 + p["id"] * 12), 2)}
        for p in _PRODUCTS[:10]
    ]

    return {
        "monthly_revenue": monthly,
        "top_products": top_prods,
        "today_revenue": 48250.0,
        "yesterday_revenue": 42100.0,
        "total_revenue": 2154950.0,
        "stock_summary": {"total": total, "low": low},
    }


def get_inmemory_users() -> List[Dict[str, Any]]:
    return [
        {"id": 1, "username": "admin", "role": "Admin", "is_active": 1, "last_login": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "created_at": "2025-01-01 00:00:00"},
        {"id": 2, "username": "manager", "role": "Manager", "is_active": 1, "last_login": None, "created_at": "2025-01-15 00:00:00"},
        {"id": 3, "username": "cashier", "role": "Staff", "is_active": 1, "last_login": None, "created_at": "2025-02-01 00:00:00"},
    ]


def get_inmemory_audit() -> List[Dict[str, Any]]:
    _init_store()
    return list(_AUDIT_LOG)

