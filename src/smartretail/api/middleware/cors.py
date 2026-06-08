from urllib.parse import urlparse
from smartretail.config import settings

def get_allowed_origin(origin_header: str) -> str | None:
    """Validate Origin against allowed CORS origins."""
    if not origin_header:
        return None
    origin = origin_header.strip()
    
    if origin in settings.cors_origins or "*" in settings.cors_origins:
        return origin
        
    try:
        parsed = urlparse(origin)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        if domain in settings.cors_origins:
            return domain
    except Exception:
        pass
    return None
