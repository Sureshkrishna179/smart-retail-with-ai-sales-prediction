import hmac
import hashlib
import joblib
import logging
from pathlib import Path
from smartretail.config import settings

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/ml_models")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_PATH = CACHE_DIR / "rf_models.joblib"
SIG_PATH = CACHE_DIR / "rf_models.sig"

# SECURITY-FIX applied: ML Cache Sign Key used to sign joblib (Fix 3)
SIGN_KEY = settings.ml_cache_sign_key.encode()

def _hmac(data: bytes) -> str:
    """Generate HMAC-SHA256 signature for data."""
    return hmac.new(SIGN_KEY, data, hashlib.sha256).hexdigest()

def load_models() -> dict:
    """Load models safely, dropping pickle in favor of joblib with HMAC verification."""
    if not CACHE_PATH.is_file() or not SIG_PATH.is_file():
        return {}
    
    raw = CACHE_PATH.read_bytes()
    expected_sig = SIG_PATH.read_text().strip()
    
    # Timing-safe comparison
    if not hmac.compare_digest(_hmac(raw), expected_sig):
        logger.error("SECURITY WARNING: ML cache HMAC mismatch — possible tampering detected!")
        return {}
        
    try:
        return joblib.load(CACHE_PATH)
    except Exception as e:
        logger.error(f"Error loading joblib cache: {e}")
        return {}

def save_models(models: dict):
    """Save models using joblib and generate an HMAC-SHA256 signature."""
    try:
        joblib.dump(models, CACHE_PATH)
        raw = CACHE_PATH.read_bytes()
        SIG_PATH.write_text(_hmac(raw))
    except Exception as e:
        logger.error(f"Error saving ML cache: {e}")
