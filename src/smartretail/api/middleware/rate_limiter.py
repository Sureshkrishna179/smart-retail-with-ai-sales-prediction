import time
import threading
from collections import defaultdict, deque

# SECURITY-FIX applied: Rate limiter supports per-user + per-endpoint tracking
class RateLimiter:
    def __init__(self):
        self._windows: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_allowed(self, key: str, max_req: int, window_sec: int) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._windows[key]
            while dq and dq[0] < now - window_sec:
                dq.popleft()
            if len(dq) >= max_req:
                return False
            dq.append(now)
            return True

    def make_key(self, ip: str, user_id, endpoint: str) -> str:
        return f"{ip}:{user_id}:{endpoint}"
