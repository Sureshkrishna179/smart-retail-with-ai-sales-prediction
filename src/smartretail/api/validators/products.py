import re

# SECURITY-FIX applied: Strict input validation (Fix 18)
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,50}$")
PASSWORD_MIN_LEN = 12

def validate_create_user(body: dict) -> tuple[bool, str]:
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", "")).strip()
    role     = str(body.get("role", "")).strip()

    if not USERNAME_RE.match(username):
        return False, "Username: 3-50 alphanumeric/underscore"
    if len(password) < PASSWORD_MIN_LEN:
        return False, f"Password: minimum {PASSWORD_MIN_LEN} characters"
    if not any(c.isupper() for c in password):
        return False, "Password: needs uppercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password: needs digit"
    if not any(c in "!@#$%^&*()" for c in password):
        return False, "Password: needs special character"
    if role not in ("Admin", "Manager", "Staff"):
        return False, "Role: must be Admin, Manager, or Staff"
    return True, ""
