import jwt
import secrets
import hmac
from smartretail.config import settings

def _decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def authenticate(auth_header: str) -> dict | None:
    """Validate Bearer token from header."""
    if not settings.require_auth:
        return {"user_id": 0, "username": "local_dev", "role": "Admin"}
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    return _decode_jwt(token)

# SECURITY-FIX applied: CSRF Protection (Fix 9)
def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)

def validate_csrf_token(provided: str, stored: str) -> bool:
    if not provided or not stored:
        return False
    return hmac.compare_digest(provided, stored)
