from smartretail.api.middleware.security_headers import json_response
from smartretail.services.auth_service import verify_jwt

def require_auth(allowed_roles=None):
    """
    Decorator to protect API routes.
    allowed_roles: list of roles allowed to access this route. If None, any logged-in user is allowed.
    """
    def decorator(handler_func):
        def wrapper(request, *args, **kwargs):
            from smartretail.config import settings
            
            if not settings.require_auth:
                request.user = {"user_id": 1, "username": "admin", "role": "Admin"}
                return handler_func(request, *args, **kwargs)

            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return json_response(request, {"error": "Missing or invalid token"}, 401)
            
            token = auth_header.split(" ")[1]
            user = verify_jwt(token)
            
            if not user:
                return json_response(request, {"error": "Invalid or expired token"}, 401)
                
            if allowed_roles and user.get("role") not in allowed_roles:
                return json_response(request, {"error": "Access denied. Requires appropriate role."}, 403)
                
            # Attach user to request for handlers to use
            request.user = user
            
            return handler_func(request, *args, **kwargs)
        return wrapper
    return decorator
