import logging
from smartretail.db.connection import db_query, get_connection
from smartretail.services.auth_service import verify_password, issue_jwt, hash_password_pbkdf2
from smartretail.api.middleware.security_headers import json_response
from smartretail.api.utils import read_json_body

logger = logging.getLogger(__name__)

def handle_login(request):
    body = read_json_body(request)
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    
    if not username or not password:
        return json_response(request, {"error": "Missing username or password"}, 400)

    # Check if MySQL is available
    conn = None
    try:
        conn = get_connection()
    except Exception:
        conn = None

    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        # MySQL is reachable: strictly authenticate against database
        try:
            user_rows = db_query("SELECT id, username, password_hash, role, is_active FROM users WHERE username=%s", (username,))
            if not user_rows:
                return json_response(request, {"error": "Invalid username or password"}, 401)
                
            user = user_rows[0]
            if not user.get("is_active", True):
                return json_response(request, {"error": "Account is disabled"}, 403)
                
            if not verify_password(password, user["password_hash"]):
                return json_response(request, {"error": "Invalid username or password"}, 401)
                
            token = issue_jwt(user["id"], user["username"], user["role"])
            try:
                db_query("UPDATE users SET last_login=NOW() WHERE id=%s", (user["id"],), fetch=False)
            except Exception:
                pass
                
            return json_response(request, {
                "success": True,
                "token": token,
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "role": user["role"]
                }
            })
        except Exception as e:
            logger.error("Database login exception: %s", e, exc_info=True)
            return json_response(request, {"error": "Internal server error"}, 500)

    # MySQL is completely unreachable: In-Memory Fallback Credentials (only for offline demos)
    fallback_users = {
        "admin": ("admin123", "Admin", 1),
        "manager": ("manager123", "Manager", 2),
        "cashier": ("cashier123", "Staff", 3),
    }
    if username in fallback_users and password == fallback_users[username][0]:
        role = fallback_users[username][1]
        uid = fallback_users[username][2]
        token = issue_jwt(uid, username, role)
        return json_response(request, {
            "success": True,
            "token": token,
            "user": {
                "id": uid,
                "username": username,
                "role": role
            }
        })
        
    return json_response(request, {"error": "Invalid username or password"}, 401)
