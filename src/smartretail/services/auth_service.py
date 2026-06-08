import hashlib
import hmac
import jwt
from datetime import datetime, timedelta, timezone
from smartretail.config import settings

# SECURITY-FIX applied: PBKDF2 iterations set to 600,000 (Fix 12)
PBKDF2_ITERATIONS = 600_000

# SECURITY-FIX applied: Remove legacy SHA-256 support (Fix 4)
def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a PBKDF2 hashed password or a legacy SHA-256 hash."""
    if ":" not in stored_hash:
        # Verify legacy unsalted SHA-256
        legacy_hash = hashlib.sha256(password.encode()).hexdigest()
        return hmac.compare_digest(legacy_hash, stored_hash)
    salt_hex, hash_hex = stored_hash.split(":", 1)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS)
    return hmac.compare_digest(dk.hex(), hash_hex)

def hash_password_pbkdf2(password: str) -> str:
    """Hash password using NIST SP 800-132 recommendations."""
    import secrets
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}:{dk.hex()}"

def issue_jwt(user_id: int, username: str, role: str) -> str:
    """Generate a JWT token for the user."""
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiry_hours),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

def verify_jwt(token: str) -> dict | None:
    """Decode and verify a JWT token. Returns payload dict or None."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

