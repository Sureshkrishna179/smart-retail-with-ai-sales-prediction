from smartretail.db.connection import db_query
from smartretail.api.middleware.security_headers import json_response
from smartretail.api.middleware.auth import require_auth
from smartretail.api.utils import read_json_body
from smartretail.services.auth_service import hash_password_pbkdf2
from smartretail.api.validators.products import validate_create_user
from smartretail.api.validators.core import validate_toggle_user
from smartretail.db.inmemory_store import get_inmemory_users, get_inmemory_audit

@require_auth(allowed_roles=["Admin"])
def handle_get_users(request):
    try:
        users = db_query("SELECT id, username, role, is_active, last_login, created_at FROM users ORDER BY role, username")
        if users:
            return json_response(request, {"users": users})
    except Exception:
        pass
    # In-memory users for standalone demonstration
    return json_response(request, {"users": get_inmemory_users()})

@require_auth(allowed_roles=["Admin"])
def handle_create_user(request):
    try:
        body = read_json_body(request)
        ok, err = validate_create_user(body)
        if not ok:
            return json_response(request, {"error": err}, 400)
            
        username = body.get("username","").strip()
        password = body.get("password","").strip()
        role     = body.get("role","Staff")
        
        try:
            existing = db_query("SELECT id FROM users WHERE username=%s", (username,))
            if existing:
                return json_response(request, {"error": "Username already exists"}, 409)
                
            pw_hash = hash_password_pbkdf2(password)
            uid = db_query(
                "INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)", 
                (username, pw_hash, role), 
                fetch=False
            )
            return json_response(request, {"success": True, "id": uid, "username": username, "role": role})
        except Exception:
            # In-Memory append
            users = get_inmemory_users()
            new_id = len(users) + 1
            users.append({"id": new_id, "username": username, "role": role, "is_active": 1, "last_login": None, "created_at": "Just now"})
            return json_response(request, {"success": True, "id": new_id, "username": username, "role": role})
    except Exception as e:
        return json_response(request, {"error": str(e)}, 500)

@require_auth(allowed_roles=["Admin"])
def handle_toggle_user(request):
    try:
        body = read_json_body(request)
        ok, err = validate_toggle_user(body)
        if not ok:
            return json_response(request, {"error": err}, 400)
            
        uid = int(body.get("user_id"))
        try:
            db_query("UPDATE users SET is_active = NOT is_active WHERE id=%s", (uid,), fetch=False)
            user = db_query("SELECT id, username, is_active FROM users WHERE id=%s", (uid,))
            return json_response(request, {"success": True, "user": user[0] if user else {}})
        except Exception:
            users = get_inmemory_users()
            for u in users:
                if u["id"] == uid:
                    u["is_active"] = 0 if u.get("is_active") else 1
                    return json_response(request, {"success": True, "user": u})
            return json_response(request, {"error": "User not found"}, 404)
    except Exception as e:
        return json_response(request, {"error": str(e)}, 500)

@require_auth(allowed_roles=["Admin"])
def handle_audit_log(request):
    try:
        logs = db_query("""
            SELECT a.*, u.username FROM audit_log a
            LEFT JOIN users u ON a.user_id=u.id ORDER BY a.created_at DESC LIMIT 50
        """)
        if logs:
            return json_response(request, {"logs": logs})
    except Exception:
        pass
    # In-memory audit log for standalone demonstration
    return json_response(request, {"logs": get_inmemory_audit()})
