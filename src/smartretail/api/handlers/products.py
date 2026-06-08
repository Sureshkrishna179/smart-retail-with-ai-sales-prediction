from smartretail.db.connection import db_query
from smartretail.api.middleware.security_headers import json_response
from smartretail.api.middleware.auth import require_auth
from smartretail.api.utils import read_json_body
from smartretail.api.validators.core import validate_add_product

@require_auth()
def handle_get_products(request):
    try:
        rows = db_query("SELECT * FROM products ORDER BY category, name")
        return json_response(request, {"products": rows})
    except Exception as e:
        return json_response(request, {"error": str(e)}, 500)

@require_auth(allowed_roles=["Admin", "Manager"])
def handle_add_product(request):
    try:
        body = read_json_body(request)
        ok, err = validate_add_product(body)
        if not ok:
            return json_response(request, {"error": err}, 400)
            
        name      = body.get("name", "").strip()
        category  = body.get("category", "General")
        unit      = body.get("unit", "piece")
        price     = float(body.get("price", 0))
        stock     = int(body.get("stock", 0))
        min_stock = int(body.get("min_stock", 50))
        
        pid = db_query(
            "INSERT INTO products (name, category, unit, price, current_stock, min_stock_level) VALUES (%s,%s,%s,%s,%s,%s)",
            (name, category, unit, price, stock, min_stock),
            fetch=False
        )
        return json_response(request, {"success": True, "id": pid})
    except Exception as e:
        return json_response(request, {"error": str(e)}, 500)
