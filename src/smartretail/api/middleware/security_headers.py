import json
from decimal import Decimal
from datetime import date, datetime

class _JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

# SECURITY-FIX applied: Added strict security headers (Fix 8)
SECURITY_HEADERS = {
    "X-Content-Type-Options":  "nosniff",
    "X-Frame-Options":         "DENY",
    "X-XSS-Protection":        "1; mode=block",
    "Referrer-Policy":         "strict-origin-when-cross-origin",
    "Cache-Control":           "no-store",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    # MED-07: Restrict powerful browser APIs — carried over from serve_dashboard.py
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data:; "
        "font-src 'self' https://fonts.gstatic.com; "
        "connect-src 'self'"
    ),
}


def apply_security_headers(handler):
    """Write strict security headers to the response."""
    for key, value in SECURITY_HEADERS.items():
        handler.send_header(key, value)

def json_response(handler, data: dict, status_code: int = 200, origin: str | None = None):
    """Helper to send JSON response with security headers and CORS."""
    payload = json.dumps(data, cls=_JSONEncoder).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    
    if origin:
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Access-Control-Allow-Credentials", "true")
        
    apply_security_headers(handler)
    handler.end_headers()
    handler.wfile.write(payload)
