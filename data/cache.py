import time
from typing import Any, Dict, Tuple

class GlobalCache:
    def __init__(self):
        # Stores (value, expiry_unix_time)
        self._store: Dict[str, Tuple[Any, float]] = {}

    def set(self, key: str, value: Any, ttl_seconds: float = 86400.0):
        """Sets a cache item with an explicit time-to-live. Defaults to 24 hours."""
        expiry = time.time() + ttl_seconds
        self._store[key] = (value, expiry)

    def get(self, key: str) -> Any:
        """Retrieves a cached item if exists and not expired."""
        if key in self._store:
            value, expiry = self._store[key]
            if time.time() < expiry:
                return value
            else:
                self.delete(key) # mechanically burn stale cache
        return None

    def delete(self, key: str):
        if key in self._store:
            del self._store[key]
            
    def clear(self):
        self._store.clear()

# Global cache instance
cache = GlobalCache()
