import re
from datetime import datetime

VALID_CATEGORIES = ("Grocery", "Beverages", "Snacks", "Personal Care", "Spices", "Dairy", "Cleaning", "General")
VALID_UNITS = ("kg", "litre", "pack", "packet", "bottle", "piece")

def validate_add_product(body):
    """Validate product creation input. Returns (ok, error_msg)."""
    name = body.get("name", "")
    if not isinstance(name, str) or len(name.strip()) < 1 or len(name) > 100:
        return False, "Product name must be 1-100 characters"
    try:
        price = float(body.get("price", 0))
        if price <= 0 or price > 999999:
            return False, "Price must be between 0.01 and 999,999"
    except (ValueError, TypeError):
        return False, "Invalid price value"
    try:
        stock = int(body.get("stock", 0))
        if stock < 0 or stock > 999999:
            return False, "Stock must be between 0 and 999,999"
    except (ValueError, TypeError):
        return False, "Invalid stock value"
    try:
        min_stock = int(body.get("min_stock", 50))
        if min_stock < 0 or min_stock > 999999:
            return False, "Min stock must be between 0 and 999,999"
    except (ValueError, TypeError):
        return False, "Invalid min stock value"
    category = body.get("category", "General")
    if category not in VALID_CATEGORIES:
        return False, f"Category must be one of: {', '.join(VALID_CATEGORIES)}"
    unit = body.get("unit", "piece")
    if unit not in VALID_UNITS:
        return False, f"Unit must be one of: {', '.join(VALID_UNITS)}"
    return True, ""

def validate_billing(body):
    """Validate billing cart input. Returns (ok, error_msg)."""
    cart = body.get("cart", [])
    if not isinstance(cart, list) or len(cart) == 0:
        return False, "Cart must be a non-empty list"
    if len(cart) > 100:
        return False, "Cart cannot contain more than 100 items"
    for item in cart:
        if not isinstance(item, dict):
            return False, "Each cart item must be an object"
        try:
            pid = int(item.get("product_id", 0))
            qty = int(item.get("quantity", 0))
            if pid <= 0 or qty <= 0 or qty > 10000:
                return False, "Invalid product_id or quantity (must be positive, qty max 10000)"
        except (ValueError, TypeError):
            return False, "product_id and quantity must be integers"
    return True, ""

def validate_restock(body):
    """Validate restock input. Returns (ok, error_msg)."""
    try:
        pid = int(body.get("product_id", 0))
        qty = int(body.get("quantity", 0))
        if pid <= 0 or qty <= 0 or qty > 999999:
            return False, "Invalid product_id or quantity"
    except (ValueError, TypeError):
        return False, "product_id and quantity must be integers"
    return True, ""

def validate_predict(body):
    """Validate prediction request input. Returns (ok, error_msg)."""
    product = body.get("product", "")
    start = body.get("start_date", "")
    if not isinstance(product, str) or len(product.strip()) < 1 or len(product) > 100:
        return False, "Product name must be 1-100 characters"
    if not isinstance(start, str):
        return False, "start_date required"
    try:
        datetime.strptime(start, "%Y-%m-%d")
    except ValueError:
        return False, "start_date must be YYYY-MM-DD format"
    end = body.get("end_date", start)
    if end:
        try:
            s = datetime.strptime(start, "%Y-%m-%d")
            e = datetime.strptime(end, "%Y-%m-%d")
            if (e - s).days > 730:
                return False, "Date range cannot exceed 730 days"
            if e < s:
                return False, "end_date cannot be before start_date"
        except ValueError:
            return False, "end_date must be YYYY-MM-DD format"
    return True, ""

def validate_train(body):
    """Validate training request input. Returns (ok, error_msg)."""
    product = body.get("product", "ALL") or "ALL"
    if not isinstance(product, str) or len(product) > 100:
        return False, "Product name must be 1-100 characters"
    csv_data = body.get("csv_data", "")
    if csv_data and len(csv_data) > 10 * 1024 * 1024:  # 10MB max
        return False, "CSV data exceeds 10MB limit"
    return True, ""

def validate_toggle_user(body):
    """Validate toggle user input. Returns (ok, error_msg)."""
    try:
        uid = int(body.get("user_id", 0))
        if uid <= 0:
            return False, "Invalid user_id"
    except (ValueError, TypeError):
        return False, "user_id must be an integer"
    return True, ""
