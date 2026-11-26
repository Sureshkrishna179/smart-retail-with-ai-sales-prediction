from urllib.parse import urlparse
from smartretail.config import settings

def get_allowed_origin(origin_header: str) -> str | None:
    """Validate Origin against allowed CORS origins."""
    allowed_origins = settings.cors_origins or []
    if not origin_header or not allowed_origins:
        return None
    origin = origin_header.strip()
    
    if origin in allowed_origins or "*" in allowed_origins:
        return origin
        
    try:
        parsed = urlparse(origin)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        if domain in allowed_origins:
            return domain
    except Exception:
        pass
    return None
