import uuid
import logging
import traceback
from smartretail.api.middleware.security_headers import json_response

logger = logging.getLogger(__name__)

# SECURITY-FIX applied: Global error handler (Fix 10)
def safe_error(handler, request):
    try:
        return handler(request)
    except Exception as exc:
        ref = str(uuid.uuid4())[:8]
        logger.error("[%s] Unhandled: %s\n%s", ref, exc, traceback.format_exc())
        return json_response(request, {"error": "Internal server error", "ref": ref}, 500)

class Router:
    """Basic routing logic mapping paths to handler functions."""
    def __init__(self):
        self.routes = {}

    def add_route(self, method: str, path: str, handler_func):
        self.routes[(method.upper(), path)] = handler_func

    def handle(self, method: str, path: str, request):
        # Strip query parameters if any
        base_path = path.split("?")[0]
        # Strip trailing slash if any, except for root
        if base_path != "/" and base_path.endswith("/"):
            base_path = base_path[:-1]
            
        handler_func = self.routes.get((method.upper(), base_path))
        if handler_func:
            return safe_error(handler_func, request)
        
        logger.error(f"Route not found: {method} {path} (checked {method.upper()} {base_path})")
        return json_response(request, {"error": "Not found"}, 404)
