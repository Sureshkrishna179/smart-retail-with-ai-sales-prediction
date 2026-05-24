"""
serve_dashboard.py — Main Backend Server for SmartRetail AI
Serves the SPA dashboard and provides REST API endpoints for
MySQL operations, ML predictions, and festival logic.

Security: OWASP-hardened with JWT auth, rate limiting, strict CORS,
HTTP security headers, PBKDF2 password hashing, and input validation.
"""

import http.server
import json
import os
import io
import csv
import hashlib
import secrets
import re
import time
import traceback
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta
from dotenv import load_dotenv

import jwt  # PyJWT
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

import mysql.connector
from mysql.connector import pooling, Error

load_dotenv()

# ─── Database Configuration ───────────────────────────────────────
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "retail_sales_db"),
}

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="retail_pool", pool_size=5,
            pool_reset_session=True, **DB_CONFIG
        )
    return _pool

def db_query(query, params=None, fetch=True):
    conn = get_pool().get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, params or ())
        if fetch:
            return cur.fetchall()
        conn.commit()
        return cur.lastrowid
    finally:
        cur.close()
        conn.close()

def db_transaction(queries):
    conn = get_pool().get_connection()
    try:
        cur = conn.cursor()
        for q, p in queries:
            cur.execute(q, p or ())
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


# ─── Security Configuration ───────────────────────────────────────

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "8"))

# CORS
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8080").split(",") if o.strip()]

# Rate limiting
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "60"))
RATE_LIMIT_LOGIN = int(os.getenv("RATE_LIMIT_LOGIN", "10"))
RATE_LIMIT_WINDOW = 60  # seconds


# ─── Rate Limiter ──────────────────────────────────────────────────
class RateLimiter:
    """IP-based sliding-window rate limiter."""

    def __init__(self):
        self._requests = {}  # ip -> [(timestamp, ...)]
        self._cleanup_interval = 120
        self._last_cleanup = time.time()

    def is_allowed(self, ip, max_requests=RATE_LIMIT_MAX, window=RATE_LIMIT_WINDOW):
        """Check if an IP is within its rate limit. Returns (allowed: bool, retry_after: int)."""
        now = time.time()

        # Periodic cleanup of stale entries
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup(now, window)

        key = ip
        if key not in self._requests:
            self._requests[key] = []

        # Trim old requests outside the window
        self._requests[key] = [t for t in self._requests[key] if now - t < window]

        if len(self._requests[key]) >= max_requests:
            oldest = self._requests[key][0]
            retry_after = int(window - (now - oldest)) + 1
            return False, max(1, retry_after)

        self._requests[key].append(now)
        return True, 0

    def _cleanup(self, now, window):
        """Remove stale IP entries."""
        stale_keys = [k for k, v in self._requests.items() if not v or now - v[-1] > window * 2]
        for k in stale_keys:
            del self._requests[k]
        self._last_cleanup = now


_rate_limiter = RateLimiter()


# ─── PBKDF2 Password Hashing ──────────────────────────────────────
PBKDF2_ITERATIONS = 100_000

def hash_password(password):
    """Hash a password with a random salt using PBKDF2-HMAC-SHA256.
    Returns 'salt_hex:hash_hex' string."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return salt.hex() + ":" + dk.hex()


def verify_password(password, stored_hash):
    """Verify a password against a stored 'salt_hex:hash_hex' string.
    Also supports legacy SHA-256 hashes for migration."""
    if ":" in stored_hash:
        # PBKDF2 format
        salt_hex, hash_hex = stored_hash.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        return dk.hex() == hash_hex
    else:
        # Legacy SHA-256 fallback (for migration period)
        legacy = hashlib.sha256(password.encode()).hexdigest()
        return legacy == stored_hash


# ─── JWT Token Functions ───────────────────────────────────────────

def create_jwt(user_id, username, role):
    """Create a signed JWT token with user claims and expiry."""
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token):
    """Decode and verify a JWT token. Returns payload dict or None."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ─── Input Validation ──────────────────────────────────────────────
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,50}$")
VALID_ROLES = ("Admin", "Manager", "Staff")
VALID_CATEGORIES = ("Grocery", "Beverages", "Snacks", "Personal Care", "Spices", "Dairy", "Cleaning", "General")
VALID_UNITS = ("kg", "litre", "pack", "packet", "bottle", "piece")


def validate_login(body):
    """Validate login input. Returns (ok, error_msg)."""
    username = body.get("username", "")
    password = body.get("password", "")
    if not isinstance(username, str) or not isinstance(password, str):
        return False, "Invalid input types"
    if len(username) < 1 or len(username) > 50:
        return False, "Username must be 1-50 characters"
    if len(password) < 1 or len(password) > 128:
        return False, "Password must be 1-128 characters"
    return True, ""


def validate_create_user(body):
    """Validate user creation input. Returns (ok, error_msg)."""
    username = body.get("username", "")
    password = body.get("password", "")
    role = body.get("role", "Staff")
    if not isinstance(username, str) or not isinstance(password, str):
        return False, "Invalid input types"
    if not USERNAME_RE.match(username):
        return False, "Username must be 3-50 chars (alphanumeric/underscore only)"
    if len(password) < 6 or len(password) > 128:
        return False, "Password must be 6-128 characters"
    if role not in VALID_ROLES:
        return False, f"Role must be one of: {', '.join(VALID_ROLES)}"
    return True, ""


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
            if (e - s).days > 365:
                return False, "Date range cannot exceed 365 days"
            if e < s:
                return False, "end_date cannot be before start_date"
        except ValueError:
            return False, "end_date must be YYYY-MM-DD format"
    return True, ""


def validate_train(body):
    """Validate training request input. Returns (ok, error_msg)."""
    product = body.get("product", "")
    if not isinstance(product, str) or len(product.strip()) < 1 or len(product) > 100:
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


# ─── Festival Intelligence ─────────────────────────────────────────
FESTIVALS = [
    # Tamil Nadu
    ("Pongal", 1, 14, 1, 17, 1.5), ("Thai Poosam", 1, 25, 1, 25, 1.3),
    ("Masi Magam", 2, 24, 2, 24, 1.2), ("Panguni Uthiram", 3, 25, 3, 25, 1.2),
    ("Chithirai Festival", 4, 14, 4, 28, 1.4), ("Aadi Perukku", 7, 18, 7, 18, 1.3),
    ("Vinayagar Chaturthi", 9, 7, 9, 7, 1.4), ("Navaratri", 10, 3, 10, 12, 1.5),
    ("Karthigai Deepam", 11, 25, 11, 25, 1.4),
    # National
    ("Republic Day", 1, 26, 1, 26, 1.2), ("Holi", 3, 14, 3, 14, 1.3),
    ("Ram Navami", 4, 6, 4, 6, 1.2), ("Independence Day", 8, 15, 8, 15, 1.2),
    ("Janmashtami", 8, 26, 8, 26, 1.3), ("Gandhi Jayanti", 10, 2, 10, 2, 1.1),
    ("Dussehra", 10, 12, 10, 12, 1.4), ("Diwali", 10, 24, 11, 3, 1.5),
    ("Christmas", 12, 24, 12, 25, 1.3), ("New Year", 12, 31, 1, 2, 1.4),
    ("Eid ul-Fitr", 4, 10, 4, 12, 1.4), ("Eid ul-Adha", 6, 17, 6, 19, 1.3),
    ("Onam", 9, 5, 9, 5, 1.3), ("Raksha Bandhan", 8, 9, 8, 9, 1.3),
    ("Makar Sankranti", 1, 14, 1, 14, 1.3), ("Guru Nanak Jayanti", 11, 15, 11, 15, 1.2),
    # Shopping Seasons
    ("Wedding Season Summer", 4, 15, 6, 15, 1.3),
    ("Wedding Season Winter", 11, 15, 12, 15, 1.3),
    ("Back to School", 6, 1, 6, 15, 1.2),
    ("Deepavali Shopping", 10, 15, 10, 28, 1.5),
    ("Pongal Shopping", 1, 7, 1, 14, 1.4),
]

FESTIVAL_WINDOW = 5  # +-5 days boost window


def is_festival_period(target_date):
    """Check if date falls within +-5 days of any festival. Returns (bool, name, multiplier)."""
    for name, sm, sd, em, ed, mult in FESTIVALS:
        try:
            start = datetime(target_date.year, sm, sd) - timedelta(days=FESTIVAL_WINDOW)
            end = datetime(target_date.year, em, ed) + timedelta(days=FESTIVAL_WINDOW)
            if start <= target_date <= end:
                return True, name, mult
        except ValueError:
            continue
    return False, None, 1.0


def get_demand_multiplier(target_date):
    """Calculate total demand multiplier including weekend + festival boosts."""
    multiplier = 1.0
    boosts = []
    if target_date.weekday() >= 5:
        multiplier *= 1.15
        boosts.append("Weekend Boost (+15%)")
    is_fest, fest_name, fest_mult = is_festival_period(target_date)
    if is_fest:
        multiplier *= fest_mult
        boosts.append(f"{fest_name} ({fest_mult}x)")
    return round(multiplier, 2), boosts


# ─── ML Prediction Engine ──────────────────────────────────────────
_models = {}

def train_model_from_csv(csv_text, product_name):
    """Train a RandomForest model from ANY user CSV.
    Auto-detects column names — works with any retailer's dataset format.
    """
    df = pd.read_csv(io.StringIO(csv_text))
    # Smart column detection — case-insensitive, works with any naming
    date_col = next((c for c in df.columns if 'date' in c.lower()), None)
    prod_col = next((c for c in df.columns if any(k in c.lower() for k in ['product','item','name','goods','sku'])), None)
    qty_col  = next((c for c in df.columns if any(k in c.lower() for k in ['qty','quantity','sales','sold','units','count'])), None)
    if not all([date_col, prod_col, qty_col]):
        return False, f"CSV must have Date, Product, and Quantity columns. Found columns: {list(df.columns)}"
    df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
    df = df.dropna(subset=[date_col])
    prod_data = df[df[prod_col].astype(str).str.strip().str.lower() == product_name.strip().lower()].copy()
    if len(prod_data) < 10:
        available = df[prod_col].dropna().unique().tolist()[:10]
        return False, f"Need >=10 records for '{product_name}', found {len(prod_data)}. Products in CSV: {available}"
    prod_data['Year']      = prod_data[date_col].dt.year
    prod_data['Month']     = prod_data[date_col].dt.month
    prod_data['Day']       = prod_data[date_col].dt.day
    prod_data['DayOfWeek'] = prod_data[date_col].dt.dayofweek
    X = prod_data[['Year','Month','Day','DayOfWeek']]
    y = pd.to_numeric(prod_data[qty_col], errors='coerce').fillna(0)
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    avg = float(y.mean())
    _models[product_name] = {"model": model, "avg": avg, "source": "csv"}
    return True, f"Trained on {len(prod_data)} records from your CSV (avg: {avg:.1f} units/day)"


def train_model_from_db(product_name):
    """Train model using database sales records as fallback when no CSV is provided."""
    try:
        rows = db_query("""
            SELECT s.sale_date as date, p.name as product, s.quantity
            FROM sales s JOIN products p ON s.product_id=p.id
            WHERE p.name LIKE %s ORDER BY s.sale_date
        """, (f"%{product_name}%",))
        if len(rows) < 10:
            # list available products
            prods = db_query("SELECT DISTINCT name FROM products ORDER BY name")
            names = [r['name'] for r in prods]
            return False, f"Not enough data in DB for '{product_name}'. Available: {names}"
        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        df['Year']      = df['date'].dt.year
        df['Month']     = df['date'].dt.month
        df['Day']       = df['date'].dt.day
        df['DayOfWeek'] = df['date'].dt.dayofweek
        X = df[['Year','Month','Day','DayOfWeek']]
        y = df['quantity'].astype(float)
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X, y)
        avg = float(y.mean())
        _models[product_name] = {"model": model, "avg": avg, "source": "database"}
        return True, f"Trained from database: {len(df)} records (avg: {avg:.1f} units/day)"
    except Exception as e:
        return False, str(e)


def predict_sales(product_name, target_date):
    """Predict sales for a product on a given date with festival/weekend adjustments."""
    info = _models.get(product_name)
    if not info:
        return None, "Model not trained for this product"
    features = np.array([[target_date.year, target_date.month, target_date.day, target_date.weekday()]])
    base_pred = max(0, float(info["model"].predict(features)[0]))
    mult, boosts = get_demand_multiplier(target_date)
    adjusted = round(base_pred * mult, 1)
    return adjusted, {"base": round(base_pred, 1), "multiplier": mult, "boosts": boosts, "adjusted": adjusted}


def predict_range(product_name, start_date, end_date):
    """Predict sales over a date range."""
    results = []
    current = start_date
    while current <= end_date:
        pred, details = predict_sales(product_name, current)
        if pred is not None:
            results.append({
                "date": current.strftime("%Y-%m-%d"),
                "day": current.strftime("%A"),
                "predicted_qty": details["adjusted"],
                "base_qty": details["base"],
                "multiplier": details["multiplier"],
                "boosts": details["boosts"],
            })
        current += timedelta(days=1)
    return results


# ─── API Request Handler ───────────────────────────────────────────
class APIHandler(http.server.SimpleHTTPRequestHandler):

    # ── CORS Origin Validation ──
    def _get_allowed_origin(self):
        """Check if the request's Origin is in the allowlist. Returns origin or None."""
        origin = self.headers.get("Origin", "")
        if origin in CORS_ORIGINS:
            return origin
        # Same-origin requests may not have an Origin header
        if not origin:
            return CORS_ORIGINS[0] if CORS_ORIGINS else None
        return None

    # ── Security Headers ──
    def end_headers(self):
        # Prevent browser caching of HTML, CSS, JS so changes show immediately
        if self.path.endswith(('.html', '.css', '.js')) or '?' in self.path:
            self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')

        # ── OWASP Security Headers ──
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy',
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )

        super().end_headers()

    # ── Rate Limiting Check ──
    def _check_rate_limit(self, max_requests=RATE_LIMIT_MAX):
        """Returns True if allowed, False if rate limited (sends 429)."""
        ip = self.client_address[0]
        allowed, retry_after = _rate_limiter.is_allowed(ip, max_requests)
        if not allowed:
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", str(retry_after))
            origin = self._get_allowed_origin()
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": "Too many requests. Please slow down.",
                "retry_after": retry_after
            }).encode())
            return False
        return True

    # ── JWT Authentication Middleware ──
    def _authenticate(self, require_role=None):
        """Verify JWT token from Authorization header.
        Returns user payload dict, or None (and sends 401/403).
        require_role: if set, checks the user has that specific role.
        """
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            self._json_response({"error": "Authentication required. Please log in."}, 401)
            return None
        token = auth_header[7:]  # strip "Bearer "
        payload = decode_jwt(token)
        if payload is None:
            self._json_response({"error": "Session expired or invalid token. Please log in again."}, 401)
            return None
        if require_role and payload.get("role") != require_role:
            self._json_response({"error": f"Access denied. Requires {require_role} role."}, 403)
            return None
        return payload

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "":
            self.path = "/dashboard.html"
            return super().do_GET()
        elif path == "/api/products":
            if not self._check_rate_limit(): return
            user = self._authenticate()
            if not user: return
            self._handle_get_products()
        elif path == "/api/festivals":
            if not self._check_rate_limit(): return
            user = self._authenticate()
            if not user: return
            self._handle_get_festivals()
        elif path == "/api/reports":
            if not self._check_rate_limit(): return
            user = self._authenticate()
            if not user: return
            self._handle_get_reports()
        elif path == "/api/db-status":
            if not self._check_rate_limit(): return
            user = self._authenticate()
            if not user: return
            self._handle_db_status()
        elif path == "/api/inventory-alerts":
            if not self._check_rate_limit(): return
            user = self._authenticate()
            if not user: return
            self._handle_inventory_alerts()
        elif path == "/api/audit-log":
            if not self._check_rate_limit(): return
            user = self._authenticate(require_role="Admin")
            if not user: return
            self._handle_audit_log()
        elif path == "/api/users":
            if not self._check_rate_limit(): return
            user = self._authenticate(require_role="Admin")
            if not user: return
            self._handle_get_users()
        elif path == "/api/csv-template":
            if not self._check_rate_limit(): return
            user = self._authenticate()
            if not user: return
            self._handle_csv_template()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()

        if path == "/api/login":
            # Login has stricter rate limit and no auth required
            if not self._check_rate_limit(RATE_LIMIT_LOGIN): return
            self._handle_login(body)
        elif path == "/api/billing":
            if not self._check_rate_limit(): return
            user = self._authenticate()
            if not user: return
            self._handle_billing(body)
        elif path == "/api/restock":
            if not self._check_rate_limit(): return
            user = self._authenticate()
            if not user: return
            if user.get("role") not in ("Admin", "Manager"):
                self._json_response({"error": "Access denied. Requires Manager or Admin role."}, 403)
                return
            self._handle_restock(body)
        elif path == "/api/predict":
            if not self._check_rate_limit(): return
            user = self._authenticate()
            if not user: return
            self._handle_predict(body)
        elif path == "/api/train":
            if not self._check_rate_limit(): return
            user = self._authenticate()
            if not user: return
            self._handle_train(body)
        elif path == "/api/add-product":
            if not self._check_rate_limit(): return
            user = self._authenticate()
            if not user: return
            if user.get("role") not in ("Admin", "Manager"):
                self._json_response({"error": "Access denied. Requires Manager or Admin role."}, 403)
                return
            self._handle_add_product(body)
        elif path == "/api/create-user":
            if not self._check_rate_limit(): return
            user = self._authenticate(require_role="Admin")
            if not user: return
            self._handle_create_user(body)
        elif path == "/api/toggle-user":
            if not self._check_rate_limit(): return
            user = self._authenticate(require_role="Admin")
            if not user: return
            self._handle_toggle_user(body)
        else:
            self._json_response({"error": "Not found"}, 404)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 10 * 1024 * 1024:  # 10MB max body size
            return {"_error": "Request body too large"}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}

    def _json_response(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        origin = self._get_allowed_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    # ── Products ──
    def _handle_get_products(self):
        try:
            rows = db_query("SELECT * FROM products ORDER BY category, name")
            self._json_response({"products": rows})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── DB Status ──
    def _handle_db_status(self):
        try:
            conn = get_pool().get_connection()
            info = conn.server_info
            conn.close()
            self._json_response({"status": "connected", "version": info, "database": DB_CONFIG["database"]})
        except Exception as e:
            self._json_response({"status": "disconnected", "error": str(e)})

    # ── Billing ──
    def _handle_billing(self, body):
        try:
            ok, err = validate_billing(body)
            if not ok:
                self._json_response({"error": err}, 400)
                return
            cart = body.get("cart", [])
            queries = []
            receipt = []
            for item in cart:
                pid, qty = int(item["product_id"]), int(item["quantity"])
                prod = db_query("SELECT * FROM products WHERE id=%s", (pid,))
                if not prod:
                    self._json_response({"error": f"Product {pid} not found"}, 404)
                    return
                p = prod[0]
                if p["current_stock"] < qty:
                    self._json_response({"error": f"Insufficient stock for {p['name']}"}, 400)
                    return
                total = float(p["price"]) * qty
                queries.append(("UPDATE products SET current_stock=current_stock-%s WHERE id=%s", (qty, pid)))
                queries.append(("INSERT INTO sales (product_id, quantity, unit_price, total_amount, sale_date) VALUES (%s,%s,%s,%s,NOW())", (pid, qty, float(p["price"]), total)))
                queries.append(("INSERT INTO inventory_log (product_id, change_type, quantity, previous_stock, new_stock) VALUES (%s,'sale',%s,%s,%s)", (pid, qty, p["current_stock"], p["current_stock"]-qty)))
                receipt.append({"name": p["name"], "unit": p["unit"], "qty": qty, "price": float(p["price"]), "total": total})
            if db_transaction(queries):
                grand = sum(r["total"] for r in receipt)
                self._json_response({"success": True, "receipt": receipt, "grand_total": grand, "timestamp": datetime.now().isoformat()})
            else:
                self._json_response({"error": "Transaction failed"}, 500)
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── Restock ──
    def _handle_restock(self, body):
        try:
            ok, err = validate_restock(body)
            if not ok:
                self._json_response({"error": err}, 400)
                return
            pid = int(body.get("product_id"))
            qty = int(body.get("quantity", 50))
            prod = db_query("SELECT * FROM products WHERE id=%s", (pid,))
            if not prod:
                self._json_response({"error": "Product not found"}, 404)
                return
            p = prod[0]
            new_stock = p["current_stock"] + qty
            db_query("UPDATE products SET current_stock=%s WHERE id=%s", (new_stock, pid), fetch=False)
            db_query("INSERT INTO inventory_log (product_id, change_type, quantity, previous_stock, new_stock) VALUES (%s,'restock',%s,%s,%s)", (pid, qty, p["current_stock"], new_stock), fetch=False)
            self._json_response({"success": True, "name": p["name"], "old_stock": p["current_stock"], "new_stock": new_stock})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── Festivals ──
    def _handle_get_festivals(self):
        fests = []
        for name, sm, sd, em, ed, mult in FESTIVALS:
            cat = "Tamil Nadu" if any(x in name for x in ["Pongal","Thai","Masi","Panguni","Chithirai","Aadi","Vinayagar","Navaratri","Karthigai"]) else "Shopping" if any(x in name for x in ["Wedding","Back to","Shopping"]) else "National"
            fests.append({"name": name, "category": cat, "start": f"{sm:02d}-{sd:02d}", "end": f"{em:02d}-{ed:02d}", "multiplier": mult})
        self._json_response({"festivals": fests})

    # ── Inventory Alerts ──
    def _handle_inventory_alerts(self):
        try:
            rows = db_query("SELECT * FROM products WHERE current_stock < min_stock_level ORDER BY current_stock ASC")
            self._json_response({"alerts": rows})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── Reports ──
    def _handle_get_reports(self):
        try:
            monthly = db_query("""
                SELECT DATE_FORMAT(sale_date, '%%Y-%%m') as month, SUM(total_amount) as revenue, SUM(quantity) as units
                FROM sales GROUP BY month ORDER BY month DESC LIMIT 12
            """)
            top_products = db_query("""
                SELECT p.name, p.category, SUM(s.quantity) as total_qty, SUM(s.total_amount) as total_revenue
                FROM sales s JOIN products p ON s.product_id=p.id
                GROUP BY p.id ORDER BY total_revenue DESC LIMIT 10
            """)
            today_rev = db_query("SELECT COALESCE(SUM(total_amount),0) as rev FROM sales WHERE DATE(sale_date)=CURDATE()")
            total_rev = db_query("SELECT COALESCE(SUM(total_amount),0) as rev FROM sales")
            stock_count = db_query("SELECT COUNT(*) as total, SUM(CASE WHEN current_stock < min_stock_level THEN 1 ELSE 0 END) as low FROM products")
            self._json_response({
                "monthly_revenue": monthly, "top_products": top_products,
                "today_revenue": float(today_rev[0]["rev"]) if today_rev else 0,
                "total_revenue": float(total_rev[0]["rev"]) if total_rev else 0,
                "stock_summary": stock_count[0] if stock_count else {}
            })
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── Train ML — CSV or DB fallback ──
    def _handle_train(self, body):
        try:
            ok, err = validate_train(body)
            if not ok:
                self._json_response({"error": err}, 400)
                return
            csv_data = body.get("csv_data", "")
            product  = body.get("product", "").strip()
            if csv_data:
                ok, msg = train_model_from_csv(csv_data, product)
                source = "csv"
            else:
                ok, msg = train_model_from_db(product)
                source = "database"
            self._json_response({"success": ok, "message": msg, "source": source})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── Predict ──
    def _handle_predict(self, body):
        try:
            ok, err = validate_predict(body)
            if not ok:
                self._json_response({"error": err}, 400)
                return
            product = body.get("product", "")
            start   = body.get("start_date", "")
            end     = body.get("end_date", start)
            s = datetime.strptime(start, "%Y-%m-%d")
            e = datetime.strptime(end, "%Y-%m-%d")
            results = predict_range(product, s, e)
            if not results:
                self._json_response({"error": "No predictions. Train the model first."}, 400)
                return
            total_predicted = sum(r["predicted_qty"] for r in results)
            source = _models.get(product, {}).get("source", "unknown")
            self._json_response({"predictions": results, "total_predicted": round(total_predicted, 1), "product": product, "source": source})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── Login (public — no auth required) ──
    def _handle_login(self, body):
        try:
            ok, err = validate_login(body)
            if not ok:
                self._json_response({"error": err}, 400)
                return
            username = body.get("username", "")
            password = body.get("password", "")

            # Fetch user with password hash
            user = db_query("SELECT id, username, role, password_hash FROM users WHERE username=%s AND is_active=1", (username,))
            if not user:
                self._json_response({"error": "Invalid credentials or account disabled"}, 401)
                return

            u = user[0]
            if not verify_password(password, u["password_hash"]):
                self._json_response({"error": "Invalid credentials or account disabled"}, 401)
                return

            # Generate JWT
            token = create_jwt(u["id"], u["username"], u["role"])

            # Update last login + audit
            db_query("UPDATE users SET last_login=NOW() WHERE id=%s", (u["id"],), fetch=False)
            db_query("INSERT INTO audit_log (user_id, action, details) VALUES (%s, 'LOGIN', 'Successful login')", (u["id"],), fetch=False)

            self._json_response({
                "success": True,
                "token": token,
                "user": {"id": u["id"], "username": u["username"], "role": u["role"]}
            })
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── Audit Log ──
    def _handle_audit_log(self):
        try:
            logs = db_query("""
                SELECT a.*, u.username FROM audit_log a
                LEFT JOIN users u ON a.user_id=u.id ORDER BY a.created_at DESC LIMIT 50
            """)
            self._json_response({"logs": logs})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── Get Users ──
    def _handle_get_users(self):
        try:
            users = db_query("SELECT id, username, role, is_active, last_login, created_at FROM users ORDER BY role, username")
            self._json_response({"users": users})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── Create User ──
    def _handle_create_user(self, body):
        try:
            ok, err = validate_create_user(body)
            if not ok:
                self._json_response({"error": err}, 400)
                return
            username = body.get("username","").strip()
            password = body.get("password","").strip()
            role     = body.get("role","Staff")
            existing = db_query("SELECT id FROM users WHERE username=%s", (username,))
            if existing:
                self._json_response({"error": "Username already exists"}, 409)
                return
            pw_hash = hash_password(password)
            uid = db_query("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)", (username, pw_hash, role), fetch=False)
            self._json_response({"success": True, "id": uid, "username": username, "role": role})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── Toggle User Active/Disabled ──
    def _handle_toggle_user(self, body):
        try:
            ok, err = validate_toggle_user(body)
            if not ok:
                self._json_response({"error": err}, 400)
                return
            uid = int(body.get("user_id"))
            db_query("UPDATE users SET is_active = NOT is_active WHERE id=%s", (uid,), fetch=False)
            user = db_query("SELECT id, username, is_active FROM users WHERE id=%s", (uid,))
            self._json_response({"success": True, "user": user[0] if user else {}})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── Add Product ──
    def _handle_add_product(self, body):
        try:
            ok, err = validate_add_product(body)
            if not ok:
                self._json_response({"error": err}, 400)
                return
            name      = body.get("name","").strip()
            category  = body.get("category","General")
            unit      = body.get("unit","piece")
            price     = float(body.get("price", 0))
            stock     = int(body.get("stock", 0))
            min_stock = int(body.get("min_stock", 50))
            pid = db_query("INSERT INTO products (name, category, unit, price, current_stock, min_stock_level) VALUES (%s,%s,%s,%s,%s,%s)",
                           (name, category, unit, price, stock, min_stock), fetch=False)
            self._json_response({"success": True, "id": pid})
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    # ── CSV Template Download ──
    def _handle_csv_template(self):
        template = "Date,Product,Sales_Qty\n2025-01-01,Rice,25\n2025-01-02,Rice,30\n2025-01-03,Rice,22\n2025-01-01,Wheat,18\n2025-01-02,Wheat,20\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Disposition", "attachment; filename=sales_template.csv")
        origin = self._get_allowed_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.end_headers()
        self.wfile.write(template.encode())

    def do_OPTIONS(self):
        """Handle CORS preflight requests with strict origin policy."""
        origin = self._get_allowed_origin()
        self.send_response(200)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def log_message(self, format, *args):
        if "/api/" in str(args[0]) if args else False:
            print(f"  API: {args[0]}")


# ─── Main ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 8080))
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print(f"\n{'='*50}")
    print(f"  SmartRetail AI -- Secure Server")
    print(f"{'='*50}")
    print(f"  Security: JWT Auth | PBKDF2 | Rate Limit | CSP")
    print(f"  CORS Origins: {CORS_ORIGINS}")
    print(f"  Rate Limit: {RATE_LIMIT_MAX}/min (login: {RATE_LIMIT_LOGIN}/min)")
    print(f"  JWT Expiry: {JWT_EXPIRY_HOURS} hours")
    try:
        conn = get_pool().get_connection()
        print(f"  MySQL: [OK] Connected ({DB_CONFIG['database']})")
        conn.close()
    except Exception as e:
        print(f"  MySQL: [WARN] {e}")
    print(f"  Dashboard: http://localhost:{PORT}/")
    print(f"{'='*50}\n")
    server = http.server.HTTPServer(("", PORT), APIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()
