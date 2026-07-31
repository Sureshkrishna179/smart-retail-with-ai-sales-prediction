from smartretail.db.connection import get_connection, DB_CONFIG
from smartretail.api.middleware.security_headers import json_response
from smartretail.api.middleware.auth import require_auth
from smartretail.api.handlers.ml import FESTIVALS
from smartretail.ml.trainer import get_csv_products

@require_auth()
def handle_db_status(request):
    try:
        conn = get_connection()
        if conn:
            info = conn.get_server_info()
            conn.close()
            return json_response(request, {"status": "connected", "version": info, "database": DB_CONFIG["database"]})
        else:
            return json_response(request, {"status": "disconnected", "error": "Failed to connect to database"})
    except Exception as e:
        return json_response(request, {"status": "disconnected", "error": str(e)})

@require_auth()
def handle_get_festivals(request):
    fests = []
    for name, sm, sd, em, ed, mult in FESTIVALS:
        cat = "Tamil Nadu" if any(x in name for x in ["Pongal","Thai","Masi","Panguni","Chithirai","Aadi","Vinayagar","Navaratri","Karthigai"]) else "Shopping" if any(x in name for x in ["Wedding","Back to","Shopping"]) else "National"
        fests.append({"name": name, "category": cat, "start": f"{sm:02d}-{sd:02d}", "end": f"{em:02d}-{ed:02d}", "multiplier": mult})
    return json_response(request, {"festivals": fests})

@require_auth()
def handle_get_csv_products(request):
    """Return products from products.csv (Product_ID, name, category)."""
    products = get_csv_products()
    return json_response(request, {"products": products})
