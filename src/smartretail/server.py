import http.server
import json
from smartretail.config import settings
from smartretail.api.router import Router
from smartretail.api.middleware.cors import get_allowed_origin
from smartretail.api.middleware.security_headers import json_response
from smartretail.api.middleware.rate_limiter import RateLimiter

router = Router()
rate_limiter = RateLimiter()

from smartretail.api.handlers.auth import handle_login
from smartretail.api.handlers.products import handle_get_products, handle_add_product
from smartretail.api.handlers.inventory import handle_inventory_alerts, handle_restock
from smartretail.api.handlers.sales import handle_billing, handle_get_reports, handle_csv_template
from smartretail.api.handlers.ml import handle_train, handle_predict, handle_model_info, handle_get_trained_products
from smartretail.api.handlers.users import handle_get_users, handle_create_user, handle_toggle_user, handle_audit_log
from smartretail.api.handlers.system import handle_db_status, handle_get_festivals, handle_get_csv_products
from smartretail.etl.ingestion import handle_etl_upload

# Register routes
router.add_route("POST", "/api/login", handle_login)
router.add_route("GET", "/api/products", handle_get_products)
router.add_route("POST", "/api/add-product", handle_add_product)
router.add_route("GET", "/api/inventory-alerts", handle_inventory_alerts)
router.add_route("POST", "/api/restock", handle_restock)
router.add_route("POST", "/api/billing", handle_billing)
router.add_route("GET", "/api/reports", handle_get_reports)
router.add_route("GET", "/api/csv-template", handle_csv_template)
router.add_route("POST", "/api/train", handle_train)
router.add_route("POST", "/api/predict", handle_predict)
router.add_route("GET", "/api/users", handle_get_users)
router.add_route("POST", "/api/create-user", handle_create_user)
router.add_route("POST", "/api/toggle-user", handle_toggle_user)
router.add_route("GET", "/api/audit-log", handle_audit_log)
router.add_route("GET", "/api/db-status", handle_db_status)
router.add_route("GET", "/api/festivals", handle_get_festivals)
router.add_route("GET", "/api/model-info", handle_model_info)
router.add_route("GET", "/api/products-csv", handle_get_csv_products)
router.add_route("GET", "/api/trained-products", handle_get_trained_products)
router.add_route("POST", "/api/v1/etl/upload", handle_etl_upload)


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="frontend", **kwargs)

    def end_headers(self):
        # Force browser to always revalidate — prevents stale JS/CSS from being served
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):
        if self.path == '/':
            self.path = '/dashboard.html'
        if self.path.startswith("/api/"):
            self._handle_api()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._handle_api()
        else:
            self.send_error(404, "Not Found")

    def _handle_api(self):
        origin = get_allowed_origin(self.headers.get("Origin", ""))
        
        # Rate limit check per-endpoint (Fix 13)
        client_ip = self.client_address[0]
        # In a real setup, we'd use X-Forwarded-For if behind a proxy
        key = rate_limiter.make_key(client_ip, "anonymous", self.path)
        
        # Apply stricter limits for the login endpoint
        limit = settings.rate_limit_login if self.path == "/api/login" else settings.rate_limit_max
        if not rate_limiter.is_allowed(key, limit, 60):
            return json_response(self, {"error": "Rate limit exceeded. Too many requests."}, 429, origin)

        # Delegate to router
        router.handle(self.command, self.path, self)

def run():
    print(f"Starting SmartRetail AI server on port {settings.port}...")
    server_address = ('', settings.port)
    httpd = http.server.ThreadingHTTPServer(server_address, DashboardHandler)
    httpd.serve_forever()

if __name__ == '__main__':
    run()
