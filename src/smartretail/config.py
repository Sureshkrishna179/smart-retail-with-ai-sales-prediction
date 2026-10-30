# src/smartretail/config.py
# ALL environment variables must be read here and only here.
# Other modules import from config, never call os.getenv() directly.

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    db_host:     str = os.getenv("DB_HOST", "localhost")
    db_port:     int = int(os.getenv("DB_PORT", "3306"))
    db_user:     str = os.getenv("DB_USER", "retail_app")
    db_password: str = os.getenv("DB_PASSWORD", "")
    db_name:     str = os.getenv("DB_NAME", "retail_sales_db")
    port:        int = int(os.getenv("PORT", "8765"))
    jwt_secret:  str = os.getenv("JWT_SECRET", "") or "smartretail-ai-jwt-secret-key-production-fallback-32chars"
    jwt_expiry_hours: int = int(os.getenv("JWT_EXPIRY_HOURS", "8"))
    
    # REQUIRE_AUTH: 1 to enforce login overlay, 0 to bypass in dev/demo
    require_auth: bool = os.getenv("REQUIRE_AUTH", "0").lower() not in ("0", "false", "no")
    cors_origins: list = None
    rate_limit_max: int = int(os.getenv("RATE_LIMIT_MAX", "60"))
    rate_limit_login: int = int(os.getenv("RATE_LIMIT_LOGIN", "5"))
    debug: bool = os.getenv("LOG_DEBUG", "0") == "1"
    
    # ML Cache Sign Key
    ml_cache_sign_key: str = os.getenv("ML_CACHE_SIGN_KEY", "") or "smartretail-ai-ml-cache-signing-key-fallback-32chars"

    def __post_init__(self):
        object.__setattr__(self, "cors_origins",
            [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()])
        if not self.jwt_secret or len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET env var is required and must be at least 32 characters long for security.")
        if not self.ml_cache_sign_key or len(self.ml_cache_sign_key) < 32:
            raise RuntimeError("ML_CACHE_SIGN_KEY env var is required and must be at least 32 characters long for security.")

settings = Settings()
