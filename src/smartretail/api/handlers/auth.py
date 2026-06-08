import json
from smartretail.db.connection import db_query
from smartretail.services.auth_service import verify_password, issue_jwt
from smartretail.api.middleware.security_headers import json_response

def read_json_body(request):
    length = int(request.headers.get("Content-Length", 0))
    if length <= 0 or length > 10 * 1024 * 1024:
        return {}
    raw = request.rfile.read(length).decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}

def handle_login(request):
    body = read_json_body(request)
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    
    if not username or not password:
        return json_response(request, {"error": "Missing username or password"}, 400)
        
    # Get user from database
    user_rows = db_query("SELECT id, username, password_hash, role, is_active FROM users WHERE username=%s", (username,))
    if not user_rows:
        return json_response(request, {"error": "Invalid username or password"}, 401)
        
    user = user_rows[0]
    if not user.get("is_active", True):
        return json_response(request, {"error": "Account is disabled"}, 403)
        
    # Verify password
    if not verify_password(password, user["password_hash"]):
        return json_response(request, {"error": "Invalid username or password"}, 401)
        
    # Upgrade legacy hashes to PBKDF2 automatically
    if ":" not in user["password_hash"]:
        new_hash = hash_password_pbkdf2(password)
        db_query("UPDATE users SET password_hash=%s WHERE id=%s", (new_hash, user["id"]), fetch=False)
        
    # Generate JWT
    token = issue_jwt(user["id"], user["username"], user["role"])
    
    # Update last login
    db_query("UPDATE users SET last_login=NOW() WHERE id=%s", (user["id"],), fetch=False)
    
    return json_response(request, {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"]
        }
    })
