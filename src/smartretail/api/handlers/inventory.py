from smartretail.db.connection import db_query
from smartretail.api.middleware.security_headers import json_response
from smartretail.api.middleware.auth import require_auth
from smartretail.api.utils import read_json_body
from smartretail.api.validators.core import validate_restock
from smartretail.db.inmemory_store import get_inmemory_alerts, restock_inmemory_product

@require_auth()
def handle_inventory_alerts(request):
    try:
        rows = db_query("SELECT * FROM products WHERE current_stock < min_stock_level ORDER BY current_stock ASC")
        if rows is not None:
            return json_response(request, {"alerts": rows})
    except Exception:
        pass
    # Decoupled Fallback Mode: Serve stock alerts from in-memory catalog
    return json_response(request, {"alerts": get_inmemory_alerts()})

@require_auth(allowed_roles=["Admin", "Manager"])
def handle_restock(request):
    try:
        body = read_json_body(request)
        ok, err = validate_restock(body)
        if not ok:
            return json_response(request, {"error": err}, 400)
            
        pid = int(body.get("product_id"))
        qty = int(body.get("quantity", 50))
        
        try:
            prod = db_query("SELECT * FROM products WHERE id=%s", (pid,))
            if prod:
                p = prod[0]
                new_stock = p["current_stock"] + qty
                db_query("UPDATE products SET current_stock=%s WHERE id=%s", (new_stock, pid), fetch=False)
                db_query(
                    "INSERT INTO inventory_log (product_id, change_type, quantity, previous_stock, new_stock) VALUES (%s,'restock',%s,%s,%s)",
                    (pid, qty, p["current_stock"], new_stock),
                    fetch=False
                )
                return json_response(request, {
                    "success": True, 
                    "name": p["name"], 
                    "old_stock": p["current_stock"], 
                    "new_stock": new_stock
                })
        except Exception:
            pass

        # In-Memory Fallback
        res = restock_inmemory_product(pid, qty)
        if res:
            return json_response(request, {
                "success": True,
                "name": res["name"],
                "old_stock": res["old_stock"],
                "new_stock": res["new_stock"]
            })
        return json_response(request, {"error": "Product not found"}, 404)
    except Exception as e:
        return json_response(request, {"error": str(e)}, 500)
